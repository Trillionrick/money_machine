"""Lightweight arbitrage runner using CEX router and Uniswap connector.

This is intentionally conservative: it looks for clear price edges, enforces
slippage/position/gas limits, and logs failures for monitoring.

2025 Update: Enhanced with RPC failover and circuit breaker patterns.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal
import math
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Sequence, Optional

import structlog
import httpx
from web3 import AsyncHTTPProvider, AsyncWeb3
from web3.middleware import ExtraDataToPOAMiddleware

from src.brokers.routing import OrderRouter
from src.core.execution import Order, OrderType, Side
from src.core.types import Price, Symbol
from src.core.rpc_failover import PolygonRPCManager
from src.dex.uniswap_connector import UniswapConnector
from src.dex.config import Chain
from src.live.gas_oracle import GasOracle

log = structlog.get_logger()


PriceFetcher = Callable[[Symbol], Awaitable[Price | None]]


@dataclass
class ArbitrageConfig:
    """Risk/limit configuration for arbitrage scanning."""

    min_edge_bps: float = 25.0  # minimum edge to act (bps)
    min_edge_bps_polygon: float | None = None  # override for Polygon
    min_edge_bps_cross_chain: float | None = None  # override for cross-chain paths
    max_notional: float = 1_000.0  # quote currency notional per trade
    max_position: float = 0.25  # in base units
    slippage_tolerance: float = 0.003  # 30 bps
    profit_floor_quote: float = 0.0  # minimum net profit per trade (quote units/USD)
    gas_limit: int = 500_000
    gas_price_cap_gwei: Mapping[str, float] | None = field(
        default_factory=lambda: {"ethereum": 60.0, "polygon": 80.0}
    )  # chain->cap
    min_margin_bps: float = 0.0  # extra net edge cushion after fees
    poll_interval: float = 2.0
    enable_execution: bool = False  # default to dry-run
    quote_token_price: float = 1.0  # assume stable-coin quote unless provided
    default_token_decimals: int = 6  # default for USDC/USDT

    # Polygon / cross-chain settings
    enable_polygon: bool = True
    enable_polygon_execution: bool = False
    polygon_chain_id: int = 137
    polygon_rpc_url: str | None = None
    polygon_quote_timeout: float = 3.0
    polygon_quote_protocols: str = "UNISWAP_V3,QUICKSWAP_V3,QUICKSWAP"
    polygon_gas_limit: int = 240_000
    bridge_fee_flat_usd: float = 0.35
    bridge_fee_pct: float = 0.0005  # 5 bps
    bridge_time_penalty_bps: float = 8.0
    fallback_eth_gas_price_gwei: float | None = None
    fallback_polygon_gas_price_gwei: float | None = 40.0
    eth_native_token_price: float | None = None
    polygon_native_token_price: float | None = None

    def __post_init__(self) -> None:
        """Strip whitespace from RPC URLs to prevent connection issues."""
        if self.polygon_rpc_url:
            self.polygon_rpc_url = self.polygon_rpc_url.strip()


@dataclass
class QuoteCandidate:
    """Represents a quote path with fee-adjusted edge."""

    chain: str
    source: str
    amount_in: Decimal
    expected_output: Decimal
    raw_edge_bps: float
    net_edge_bps: float
    fee_bps: float
    price: float
    metadata: dict[str, Any] = field(default_factory=dict)


def build_polygon_web3(rpc_url: str | None = None) -> AsyncWeb3:
    """Initialize a resilient AsyncWeb3 client for Polygon."""
    resolved_url = rpc_url or os.getenv("POLYGON_RPC_URL") or os.getenv("POLYGON_RPC")
    if not resolved_url:
        raise ValueError("Polygon RPC URL missing (POLYGON_RPC_URL)")

    # Strip any whitespace or control characters that may break HTTP connections
    resolved_url = resolved_url.strip()

    w3 = AsyncWeb3(AsyncHTTPProvider(resolved_url, request_kwargs={"timeout": 8}))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    # Note: w3.is_connected() is async and can't be called from sync context
    # Connection will be verified on first use
    log.debug("arbitrage.polygon_web3_initialized", rpc=resolved_url)

    return w3


@dataclass
class ArbitrageRunner:
    """Scan for DEX/CEX price edges and route orders."""

    router: OrderRouter
    dex: UniswapConnector
    price_fetcher: PriceFetcher
    token_addresses: Mapping[str, str]
    token_decimals: Mapping[str, int] = field(default_factory=dict)
    config: ArbitrageConfig = field(default_factory=ArbitrageConfig)
    polygon_dex: UniswapConnector | None = None
    polygon_token_addresses: Mapping[str, str] | None = None

    trades_executed: int = 0
    trades_skipped: int = 0
    failures: int = 0
    _polygon_w3: AsyncWeb3 | None = field(default=None, init=False, repr=False)
    _polygon_rpc_manager: Optional[PolygonRPCManager] = field(default=None, init=False, repr=False)
    _gas_oracle: GasOracle | None = field(default=None, init=False, repr=False)
    route_failures: dict[str, int] = field(default_factory=dict)
    blacklisted_routes: set[str] = field(default_factory=set)
    route_failure_threshold: int = 2
    pair_results: dict[str, dict[str, int]] = field(default_factory=dict)
    route_state_path: Path = field(default_factory=lambda: Path("logs/route_health.db"))
    _stop: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.config.enable_polygon and self._polygon_w3 is None:
            try:
                # Modern 2025: Initialize RPC failover manager
                polygon_rpc_urls = self._get_polygon_rpc_urls()
                oneinch_key = os.getenv("ONEINCH_API_KEY") or os.getenv("ONEINCH_TOKEN")

                if polygon_rpc_urls:
                    self._polygon_rpc_manager = PolygonRPCManager(
                        rpc_urls=polygon_rpc_urls,
                        oneinch_api_key=oneinch_key,
                        chain_id=self.config.polygon_chain_id,
                    )
                    log.info(
                        "arbitrage.polygon_rpc_failover_initialized",
                        endpoint_count=len(polygon_rpc_urls),
                    )
                else:
                    # Fallback to legacy single RPC
                    self._polygon_w3 = build_polygon_web3(self.config.polygon_rpc_url)
            except Exception as e:
                log.warning("arbitrage.polygon_rpc_unavailable", error=str(e))
                self.config.enable_polygon = False

        # Initialize gas oracle
        self._gas_oracle = GasOracle(
            ethereum_fallback_gwei=self.config.fallback_eth_gas_price_gwei or 50.0,
            polygon_fallback_gwei=self.config.fallback_polygon_gas_price_gwei or 40.0,
        )

        self._route_conn: sqlite3.Connection | None = None
        self._init_route_store()
        self._load_route_state()

    def _get_polygon_rpc_urls(self) -> list[str]:
        """Get all configured Polygon RPC URLs for failover."""
        urls = []

        # Primary RPC from config
        if self.config.polygon_rpc_url:
            urls.append(self.config.polygon_rpc_url.strip())

        # Additional RPC endpoints from environment
        extra_rpcs = os.getenv("POLYGON_RPC_FALLBACK_URLS", "")
        if extra_rpcs:
            urls.extend([url.strip() for url in extra_rpcs.split(",") if url.strip()])

        # Fallback to env var if config is empty
        if not urls:
            env_rpc = os.getenv("POLYGON_RPC_URL") or os.getenv("POLYGON_RPC")
            if env_rpc:
                urls.append(env_rpc.strip())

        return urls

    async def run(self, symbols: list[Symbol]) -> None:
        """Main loop: poll for edges and execute when thresholds are met."""
        try:
            while not self._stop.is_set():
                try:
                    await asyncio.gather(*(self._scan_symbol(sym) for sym in symbols))
                except Exception:
                    log.exception("arbitrage.scan_failed")
                    self.failures += 1

                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.config.poll_interval)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            log.info("arbitrage.run_cancelled")
        finally:
            self._persist_route_state()
            self._close_route_store()

    async def _scan_symbol(self, symbol: Symbol) -> None:
        """Scan a single symbol for edge and execute if profitable."""
        # Expect symbols like "ETH/USDC"
        if "/" not in symbol:
            self.trades_skipped += 1
            log.debug("arbitrage.skip_symbol_format", symbol=symbol)
            return

        base, quote = symbol.split("/", 1)
        token_in = self.token_addresses.get(quote)
        token_out = self.token_addresses.get(base)
        primary_chain = getattr(self.dex, "chain", None)
        primary_chain_label = (
            primary_chain.name.lower() if isinstance(primary_chain, Chain) else "primary"
        )
        polygon_token_in = (
            self.polygon_token_addresses.get(quote) if self.polygon_token_addresses else token_in
        )
        polygon_token_out = (
            self.polygon_token_addresses.get(base) if self.polygon_token_addresses else token_out
        )

        if not token_in or not token_out:
            self.trades_skipped += 1
            log.debug("arbitrage.skip_missing_token", symbol=symbol)
            return

        cex_price = await self.price_fetcher(symbol)
        if cex_price is None or cex_price <= 0:
            self.trades_skipped += 1
            log.debug("arbitrage.skip_no_cex_price", symbol=symbol)
            return

        notional_quote = min(self.config.max_notional, cex_price * self.config.max_position)
        amount_in = Decimal(str(notional_quote))

        candidates = await self._collect_quotes(
            symbol=symbol,
            base_symbol=base,
            quote_symbol=quote,
            token_in=token_in,
            token_out=token_out,
            polygon_token_in=polygon_token_in,
            polygon_token_out=polygon_token_out,
            amount_in=amount_in,
            cex_price=cex_price,
            cross_chain=True,
        )

        best = self._pick_best_candidate(candidates)
        if not best or best.net_edge_bps < self.config.min_edge_bps:
            self.trades_skipped += 1
            return

        required_edge = self.config.min_edge_bps
        if best.chain == "polygon" and self.config.min_edge_bps_polygon is not None:
            required_edge = self.config.min_edge_bps_polygon
        elif (
            best.chain != primary_chain_label
            and self.config.min_edge_bps_cross_chain is not None
        ):
            required_edge = self.config.min_edge_bps_cross_chain

        if best.net_edge_bps < required_edge:
            self.trades_skipped += 1
            log.debug("arbitrage.edge_below_threshold", chain=best.chain, edge=best.net_edge_bps)
            return
        if self.config.min_margin_bps and best.net_edge_bps < self.config.min_margin_bps:
            self.trades_skipped += 1
            log.debug(
                "arbitrage.margin_floor_block",
                chain=best.chain,
                net_edge_bps=best.net_edge_bps,
                margin_floor=self.config.min_margin_bps,
            )
            return

        base_qty = float(best.expected_output)
        if base_qty > self.config.max_position and base_qty > 0:
            scale = self.config.max_position / base_qty
            base_qty = self.config.max_position
            amount_in *= Decimal(str(scale))

        estimated_profit_quote = float(amount_in) * (best.net_edge_bps / 10_000)
        if estimated_profit_quote < self.config.profit_floor_quote:
            self.trades_skipped += 1
            log.debug(
                "arbitrage.profit_floor_block",
                profit=estimated_profit_quote,
                floor=self.config.profit_floor_quote,
                chain=best.chain,
            )
            return

        gas_limit = self.config.polygon_gas_limit if best.chain == "polygon" else self.config.gas_limit
        gas_bps = await self._network_fee_bps(
            chain=best.chain,
            notional_quote=float(amount_in) * self.config.quote_token_price,
            gas_limit=gas_limit,
        )
        if gas_bps and gas_bps > 0:
            gas_quote = float(amount_in) * (gas_bps / 10_000)
            if estimated_profit_quote < 2 * gas_quote:
                self.trades_skipped += 1
                log.debug(
                    "arbitrage.gas_margin_block",
                    chain=best.chain,
                    net_quote=estimated_profit_quote,
                    gas_quote=gas_quote,
                )
                return

        log.info(
            "arbitrage.opportunity",
            symbol=symbol,
            chain=best.chain,
            source=best.source,
            cex_price=cex_price,
            dex_price=best.price,
            edge_bps=best.raw_edge_bps,
            net_edge_bps=best.net_edge_bps,
            base_qty=base_qty,
        )

        if not self.config.enable_execution:
            return

        dex_executor = self._resolve_executor(best.chain)
        if dex_executor is None:
            log.warning("arbitrage.no_executor_for_chain", chain=best.chain)
            self.trades_skipped += 1
            return

        if not await self._gas_within_cap(best.chain):
            self.trades_skipped += 1
            log.debug("arbitrage.gas_cap_block", chain=best.chain)
            return

        # Use chain-specific token addresses when executing on Polygon
        exec_token_in = polygon_token_in if best.chain == "polygon" else token_in
        exec_token_out = polygon_token_out if best.chain == "polygon" else token_out

        # Type guard: ensure token addresses are not None
        if exec_token_in is None or exec_token_out is None:
            log.warning(
                "arbitrage.missing_token_addresses",
                symbol=symbol,
                chain=best.chain,
                token_in=exec_token_in,
                token_out=exec_token_out,
            )
            self.trades_skipped += 1
            return

        route_id = self._route_key(best)
        await self._execute(
            symbol, exec_token_in, exec_token_out, base_qty, amount_in, dex_executor, route_id
        )

    async def _collect_quotes(
        self,
        symbol: Symbol,
        base_symbol: str,
        quote_symbol: str,
        token_in: str,
        token_out: str,
        polygon_token_in: str | None,
        polygon_token_out: str | None,
        amount_in: Decimal,
        cex_price: float,
        cross_chain: bool = False,
    ) -> list[QuoteCandidate]:
        """Fetch quotes from the configured DEX plus Polygon/1inch if enabled."""
        candidates: list[QuoteCandidate] = []
        primary_chain = getattr(self.dex, "chain", None)
        primary_chain_label = (
            primary_chain.name.lower() if isinstance(primary_chain, Chain) else "primary"
        )

        if token_in.lower() == token_out.lower():
            log.debug("arbitrage.skip_self_pair", symbol=symbol, token=token_in)
            return candidates

        try:
            primary_quote = await self.dex.get_quote(
                token_in=token_in,
                token_out=token_out,
                amount_in=amount_in,
            )
            dex_price = float(primary_quote["expected_output"] / amount_in)
            edge_bps = self._calculate_edge_bps(cex_price, dex_price)
            fee_bps = await self._quote_fee_adjustment(
                chain=primary_chain_label,
                notional_quote=float(amount_in) * self.config.quote_token_price,
                gas_limit=self.config.gas_limit,
                apply_bridge=False,
            )
            if not math.isfinite(fee_bps):
                log.warning("arbitrage.primary_fee_unknown", symbol=symbol, chain=primary_chain_label)
                raise ValueError("primary_fee_unavailable")
            net_edge_bps = edge_bps - fee_bps
            route_id = f"{primary_chain_label}:{primary_quote.get('pool_address') or 'unknown_pool'}"
            candidates.append(
                QuoteCandidate(
                    chain=primary_chain_label,
                    source="uniswap_v3",
                    amount_in=amount_in,
                    expected_output=primary_quote["expected_output"],
                    raw_edge_bps=edge_bps,
                    net_edge_bps=net_edge_bps,
                    fee_bps=fee_bps,
                    price=dex_price,
                    metadata={"pool": primary_quote.get("pool_address"), "route_id": route_id},
                )
            )
        except Exception:
            log.exception("arbitrage.quote_failed", symbol=symbol)
            self.failures += 1

        if not self.config.enable_polygon:
            return candidates

        # Polygon direct DEX quote (no 1inch key needed)
        if self.polygon_dex and (polygon_token_in or token_in) and (polygon_token_out or token_out):
            try:
                poly_token_in_addr = polygon_token_in or token_in
                poly_token_out_addr = polygon_token_out or token_out

                # Skip if tokens are the same
                if poly_token_in_addr.lower() == poly_token_out_addr.lower():
                    log.debug("arbitrage.polygon_skip_self_pair", symbol=symbol)
                else:
                    poly_quote = await self.polygon_dex.get_quote(
                        token_in=poly_token_in_addr,
                        token_out=poly_token_out_addr,
                        amount_in=amount_in,
                    )
                    poly_price = float(poly_quote["expected_output"] / amount_in)
                    edge_bps = self._calculate_edge_bps(cex_price, poly_price)
                    fee_bps = await self._quote_fee_adjustment(
                        chain="polygon",
                        notional_quote=float(amount_in) * self.config.quote_token_price,
                        gas_limit=self.config.polygon_gas_limit,
                        apply_bridge=cross_chain,
                    )
                    if not math.isfinite(fee_bps):
                        log.warning("arbitrage.polygon_fee_unknown", symbol=symbol)
                        raise ValueError("polygon_fee_unavailable")
                    net_edge_bps = edge_bps - fee_bps
                    route_id = f"polygon:{poly_quote.get('pool_address') or 'uniswap_v3_polygon'}"
                    candidates.append(
                        QuoteCandidate(
                            chain="polygon",
                            source="uniswap_v3_polygon",
                            amount_in=amount_in,
                            expected_output=poly_quote["expected_output"],
                            raw_edge_bps=edge_bps,
                            net_edge_bps=net_edge_bps,
                            fee_bps=fee_bps,
                            price=poly_price,
                            metadata={"pool": poly_quote.get("pool_address"), "route_id": route_id},
                        )
                    )
            except Exception as e:
                log.debug("arbitrage.polygon_direct_quote_failed", symbol=symbol, error=str(e))

        polygon_quote = await self._maybe_fetch_polygon_quote(
            symbol=symbol,
            base_symbol=base_symbol,
            quote_symbol=quote_symbol,
            token_in=polygon_token_in or token_in,
            token_out=polygon_token_out or token_out,
            amount_in=amount_in,
        )

        if polygon_quote:
            edge_bps = self._calculate_edge_bps(cex_price, polygon_quote["price"])
            fee_bps = await self._quote_fee_adjustment(
                chain="polygon",
                notional_quote=float(amount_in) * self.config.quote_token_price,
                gas_limit=self.config.polygon_gas_limit,
                apply_bridge=cross_chain,
            )
            if not math.isfinite(fee_bps):
                log.warning("arbitrage.polygon_fee_unknown", symbol=symbol)
                raise ValueError("polygon_fee_unavailable")
            net_edge_bps = edge_bps - fee_bps
            protocols = polygon_quote["metadata"].get("protocols")
            proto_hint = "1inch"
            if protocols:
                try:
                    proto_hint = protocols[0][0].get("name") or protocols[0][0].get("id") or "1inch"
                except Exception:
                    proto_hint = "1inch"
            route_id = f"polygon:1inch:{proto_hint}"
            metadata = dict(polygon_quote["metadata"])
            metadata["route_id"] = route_id
            candidates.append(
                QuoteCandidate(
                    chain="polygon",
                    source="1inch",
                    amount_in=amount_in,
                    expected_output=polygon_quote["expected_output"],
                    raw_edge_bps=edge_bps,
                    net_edge_bps=net_edge_bps,
                    fee_bps=fee_bps,
                    price=polygon_quote["price"],
                    metadata=metadata,
                )
            )

        return candidates

    def _pick_best_candidate(self, candidates: Sequence[QuoteCandidate]) -> QuoteCandidate | None:
        if not candidates:
            return None
        viable = [c for c in candidates if not self._is_route_blacklisted(c)]
        if not viable:
            log.debug("arbitrage.all_routes_blacklisted")
            return None
        return max(viable, key=lambda c: c.net_edge_bps)

    def _resolve_executor(self, chain: str) -> UniswapConnector | None:
        if chain == "polygon":
            if not self.config.enable_polygon_execution or self.polygon_dex is None:
                return None
            return self.polygon_dex
        return self.dex

    @staticmethod
    def _calculate_edge_bps(cex_price: float, dex_price: float) -> float:
        if dex_price <= 0:
            return 0.0
        return (cex_price - dex_price) / dex_price * 10_000

    async def _quote_fee_adjustment(
        self,
        chain: str,
        notional_quote: float,
        gas_limit: int,
        apply_bridge: bool,
    ) -> float:
        """Return fee impact in bps (gas + optional bridge penalty)."""
        fee_bps = await self._network_fee_bps(chain, notional_quote, gas_limit)
        if not math.isfinite(fee_bps):
            return float("inf")
        if apply_bridge:
            fee_bps += self._bridge_penalty_bps(notional_quote)
        return fee_bps

    async def _network_fee_bps(self, chain: str, notional_quote: float, gas_limit: int) -> float:
        if notional_quote <= 0:
            return 0.0

        gas_price_gwei = await self._get_gas_price_gwei(chain)
        native_price = (
            self.config.polygon_native_token_price
            if chain == "polygon"
            else self.config.eth_native_token_price
        )

        if gas_price_gwei is None or native_price is None:
            log.warning(
                "arbitrage.gas_price_unavailable",
                chain=chain,
                gas_price_gwei=gas_price_gwei,
                native_price=native_price,
            )
            return float("inf")

        cost_native = gas_price_gwei * 1e-9 * gas_limit
        cost_quote = cost_native * native_price
        return (cost_quote / notional_quote) * 10_000

    def _bridge_penalty_bps(self, notional_quote: float) -> float:
        if notional_quote <= 0:
            return 0.0

        cost_usd = self.config.bridge_fee_flat_usd + (notional_quote * self.config.bridge_fee_pct)
        penalty_bps = (cost_usd / notional_quote) * 10_000
        return penalty_bps + self.config.bridge_time_penalty_bps

    async def _gas_within_cap(self, chain: str) -> bool:
        cap_map = self.config.gas_price_cap_gwei or {}
        if not cap_map:
            return True
        cap = cap_map.get(chain)
        if cap is None:
            return True
        gas_price = await self._get_gas_price_gwei(chain)
        if gas_price is None:
            log.warning("arbitrage.gas_cap_unknown_price", chain=chain)
            return False
        return gas_price <= cap

    async def _get_gas_price_gwei(self, chain: str) -> float | None:
        """Get current gas price using gas oracle with multiple fallbacks."""
        try:
            # Use gas oracle for accurate pricing if available
            if self._gas_oracle is None:
                # Fallback if gas oracle not initialized
                if chain == "polygon":
                    return self.config.fallback_polygon_gas_price_gwei
                return self.config.fallback_eth_gas_price_gwei

            chain_key = "polygon" if chain == "polygon" else "ethereum"
            web3_instance = (
                self._polygon_w3
                if chain == "polygon"
                else (self.dex.web3.w3 if hasattr(self.dex, "web3") else None)
            )

            gas_price = await self._gas_oracle.get_gas_price(chain_key, web3_instance)
            return gas_price.gwei

        except Exception:
            log.warning("arbitrage.gas_oracle_failed", chain=chain)
            # Final fallback
            if chain == "polygon":
                return self.config.fallback_polygon_gas_price_gwei
            return self.config.fallback_eth_gas_price_gwei

    async def _maybe_fetch_polygon_quote(
        self,
        symbol: Symbol,
        base_symbol: str,
        quote_symbol: str,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
    ) -> dict[str, Any] | None:
        """Fetch a Polygon quote via 1inch with RPC failover (2025 enhanced)."""
        # Skip if tokens are the same
        if token_in.lower() == token_out.lower():
            log.debug("arbitrage.oneinch_skip_self_pair", symbol=symbol)
            return None

        decimals_in = self._get_token_decimals(quote_symbol)
        amount_in_wei = int(amount_in * Decimal(10**decimals_in))

        # Ensure addresses are checksummed
        try:
            from eth_utils.address import to_checksum_address
            token_in = to_checksum_address(token_in)
            token_out = to_checksum_address(token_out)
        except Exception:
            pass  # Use as-is if checksumming fails

        # Use RPC failover manager if available (modern 2025 approach)
        if self._polygon_rpc_manager:
            try:
                data = await self._polygon_rpc_manager.get_quote(
                    token_in=token_in,
                    token_out=token_out,
                    amount_in=amount_in_wei,
                    protocols=self.config.polygon_quote_protocols,
                )
            except Exception as e:
                log.debug(
                    "arbitrage.polygon_quote_failover_exhausted",
                    symbol=symbol,
                    error=str(e)[:200],
                )
                return None
        else:
            # Legacy single-endpoint approach
            api_key = os.getenv("ONEINCH_API_KEY") or os.getenv("ONEINCH_TOKEN")
            if not api_key:
                log.debug("arbitrage.oneinch_missing_api_key")
                return None

            params = {
                "src": token_in,
                "dst": token_out,
                "amount": str(amount_in_wei),
                "includeTokensInfo": "true",
                "includeProtocols": "true",
                "protocols": self.config.polygon_quote_protocols,
            }

            headers = {
                "accept": "application/json",
                "Authorization": f"Bearer {api_key}",
            }

            url = f"https://api.1inch.dev/swap/v6.0/{self.config.polygon_chain_id}/quote"

            try:
                async with httpx.AsyncClient(timeout=self.config.polygon_quote_timeout) as client:
                    response = await client.get(url, params=params, headers=headers)
                    response.raise_for_status()
                    data = response.json()
            except httpx.HTTPStatusError as e:
                log.debug(
                    "arbitrage.polygon_quote_http_error",
                    symbol=symbol,
                    status=e.response.status_code,
                    detail=e.response.text[:200],
                )
                return None
            except httpx.TimeoutException:
                log.debug("arbitrage.polygon_quote_timeout", symbol=symbol)
                return None
            except Exception as e:
                log.debug("arbitrage.polygon_quote_failed", symbol=symbol, error=str(e))
                return None

        # Parse response
        dst_amount_raw = data.get("dstAmount") or data.get("toTokenAmount")
        dst_token = data.get("dstToken") or data.get("toToken") or {}
        dst_decimals = int(dst_token.get("decimals") or self._get_token_decimals(base_symbol))

        if not dst_amount_raw:
            return None

        expected_output = Decimal(dst_amount_raw) / Decimal(10**dst_decimals)
        dex_price = float(expected_output / amount_in) if amount_in > 0 else 0.0

        return {
            "expected_output": expected_output,
            "price": dex_price,
            "metadata": {
                "dst_token": dst_token,
                "src_decimals": decimals_in,
                "dst_decimals": dst_decimals,
                "estimated_gas": data.get("gas") or data.get("estimatedGas"),
                "protocols": data.get("protocols"),
            },
        }

    def _get_token_decimals(self, token_symbol: str) -> int:
        return int(self.token_decimals.get(token_symbol, self.config.default_token_decimals))

    def _route_key(self, candidate: QuoteCandidate) -> str:
        meta = candidate.metadata or {}
        return str(meta.get("route_id") or meta.get("pool") or f"{candidate.chain}:{candidate.source}")

    def _is_route_blacklisted(self, candidate: QuoteCandidate) -> bool:
        return self._route_key(candidate) in self.blacklisted_routes

    def _record_route_failure(self, route_id: str, reason: str | None = None) -> None:
        if not route_id:
            return
        self.route_failures[route_id] = self.route_failures.get(route_id, 0) + 1
        if self.route_failures[route_id] >= self.route_failure_threshold:
            self.blacklisted_routes.add(route_id)
            log.warning(
                "arbitrage.route_blacklisted",
                route=route_id,
                failures=self.route_failures[route_id],
                reason=reason,
            )
        self._persist_route_state()

    def _reset_route_failure(self, route_id: str) -> None:
        if not route_id:
            return
        if route_id in self.route_failures:
            self.route_failures[route_id] = 0
        if route_id in self.blacklisted_routes:
            self.blacklisted_routes.discard(route_id)
        self._persist_route_state()

    @staticmethod
    def _extract_revert_reason(exc: Exception) -> str:
        message = str(exc)
        if "execution reverted" in message:
            return message
        return message.splitlines()[0] if message else "unknown_error"

    def _init_route_store(self) -> None:
        """Initialize sqlite store for route health."""
        try:
            self.route_state_path.parent.mkdir(parents=True, exist_ok=True)
            self._route_conn = sqlite3.connect(self.route_state_path)
            cur = self._route_conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS route_failures (
                    route_id TEXT PRIMARY KEY,
                    failures INTEGER NOT NULL,
                    blacklisted INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS pair_results (
                    symbol TEXT PRIMARY KEY,
                    wins INTEGER NOT NULL,
                    trades INTEGER NOT NULL
                )
                """
            )
            self._route_conn.commit()
        except Exception:
            log.debug("arbitrage.route_store_init_failed")
            self._route_conn = None

    def _record_pair_result(self, symbol: str, success: bool) -> None:
        stats = self.pair_results.get(symbol, {"wins": 0, "trades": 0})
        stats["trades"] += 1
        if success:
            stats["wins"] += 1
        self.pair_results[symbol] = stats
        self._persist_route_state()

    def _load_route_state(self) -> None:
        if not self._route_conn:
            return
        try:
            cur = self._route_conn.cursor()
            cur.execute("SELECT route_id, failures, blacklisted FROM route_failures")
            for route_id, failures, blacklisted in cur.fetchall():
                self.route_failures[route_id] = failures
                if blacklisted:
                    self.blacklisted_routes.add(route_id)
            cur.execute("SELECT symbol, wins, trades FROM pair_results")
            for symbol, wins, trades in cur.fetchall():
                self.pair_results[symbol] = {"wins": wins, "trades": trades}
        except Exception:
            log.debug("arbitrage.route_state_load_failed")

    def _persist_route_state(self) -> None:
        if not self._route_conn:
            return
        try:
            cur = self._route_conn.cursor()
            for route_id, failures in self.route_failures.items():
                cur.execute(
                    """
                    INSERT INTO route_failures(route_id, failures, blacklisted)
                    VALUES (?, ?, ?)
                    ON CONFLICT(route_id) DO UPDATE SET failures=excluded.failures, blacklisted=excluded.blacklisted
                    """,
                    (route_id, failures, 1 if route_id in self.blacklisted_routes else 0),
                )
            for symbol, stats in self.pair_results.items():
                cur.execute(
                    """
                    INSERT INTO pair_results(symbol, wins, trades)
                    VALUES (?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET wins=excluded.wins, trades=excluded.trades
                    """,
                    (symbol, int(stats.get("wins", 0)), int(stats.get("trades", 0))),
                )
            self._route_conn.commit()
        except Exception:
            log.debug("arbitrage.route_state_persist_failed")
        finally:
            if self._route_conn:
                try:
                    self._route_conn.commit()
                except Exception:
                    log.debug("arbitrage.route_state_commit_failed")

    def _close_route_store(self) -> None:
        if self._route_conn:
            try:
                self._route_conn.close()
            except Exception:
                log.debug("arbitrage.route_store_close_failed")
            self._route_conn = None

    def stop(self) -> None:
        """Request a graceful shutdown."""
        self._stop.set()

    async def _execute(
        self,
        symbol: Symbol,
        token_in: str,
        token_out: str,
        base_qty: float,
        amount_in_quote: Decimal,
        dex_executor: UniswapConnector | None = None,
        route_id: str | None = None,
    ) -> str | None:
        """Execute DEX buy + CEX sell with stop-loss protection."""
        executor = dex_executor or self.dex
        try:
            tx_hash = await executor.execute_market_swap(
                token_in=token_in,
                token_out=token_out,
                amount_in=amount_in_quote,
                slippage_tolerance=Decimal(str(self.config.slippage_tolerance)),
            )
            log.info("arbitrage.dex_swap_submitted", symbol=symbol, tx_hash=tx_hash)
            if route_id:
                self._reset_route_failure(route_id)
        except Exception as exc:
            self.failures += 1
            reason = self._extract_revert_reason(exc)
            log.exception("arbitrage.dex_swap_failed", symbol=symbol, route=route_id, reason=reason)
            if route_id:
                self._record_route_failure(route_id, reason)
            self._record_pair_result(symbol, False)
            return None

        sell_order = Order(
            symbol=symbol,
            side=Side.SELL,
            quantity=base_qty,
            order_type=OrderType.MARKET,
        )

        # Try CEX sell with retries
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self.router.submit_orders([sell_order])
                self.trades_executed += 1
                log.info(
                    "arbitrage.cex_sell_submitted",
                    symbol=symbol,
                    quantity=base_qty,
                    attempt=attempt + 1,
                )
                self._record_pair_result(symbol, True)
                return tx_hash
            except Exception as e:
                log.warning(
                    "arbitrage.cex_sell_attempt_failed",
                    symbol=symbol,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(e),
                )

                if attempt < max_retries - 1:
                    # Wait before retry (exponential backoff)
                    await asyncio.sleep(2**attempt)
                else:
                    # All retries exhausted - log critical alert
                    self.failures += 1
                    log.critical(
                        "arbitrage.cex_sell_failed_all_retries",
                        symbol=symbol,
                        quantity=base_qty,
                        dex_tx=tx_hash,
                        unhedged_position=True,
                        action_required="MANUAL_INTERVENTION",
                    )
                    self._record_pair_result(symbol, False)
                    # TODO: Send alert (email/SMS/webhook) for manual intervention
                    # TODO: Consider implementing emergency sell on DEX to close position
                    return tx_hash

        return tx_hash
