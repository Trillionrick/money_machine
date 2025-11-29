"""Lightweight arbitrage runner using CEX router and Uniswap connector.

This is intentionally conservative: it looks for clear price edges, enforces
slippage/position/gas limits, and logs failures for monitoring.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Awaitable, Callable, Mapping, Sequence

import structlog
import httpx
from web3 import AsyncHTTPProvider, AsyncWeb3
from web3.middleware import async_geth_poa_middleware

from src.brokers.routing import OrderRouter
from src.core.execution import Order, OrderType, Side
from src.core.types import Price, Symbol
from src.dex.uniswap_connector import UniswapConnector
from src.dex.config import Chain

log = structlog.get_logger()


PriceFetcher = Callable[[Symbol], Awaitable[Price | None]]


@dataclass
class ArbitrageConfig:
    """Risk/limit configuration for arbitrage scanning."""

    min_edge_bps: float = 25.0  # minimum edge to act (bps)
    max_notional: float = 1_000.0  # quote currency notional per trade
    max_position: float = 0.25  # in base units
    slippage_tolerance: float = 0.003  # 30 bps
    gas_limit: int = 500_000
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

    w3 = AsyncWeb3(AsyncHTTPProvider(resolved_url, request_kwargs={"timeout": 8}))
    w3.middleware_onion.inject(async_geth_poa_middleware, layer=0)

    try:
        connected = w3.is_connected()
        if isinstance(connected, bool) and not connected:
            raise ConnectionError(f"Failed to connect to Polygon RPC at {resolved_url}")
    except Exception:
        log.debug("arbitrage.polygon_connection_check_skipped", rpc=resolved_url)

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

    def __post_init__(self) -> None:
        if self.config.enable_polygon and self._polygon_w3 is None:
            try:
                self._polygon_w3 = build_polygon_web3(self.config.polygon_rpc_url)
            except Exception:
                log.warning("arbitrage.polygon_rpc_unavailable")
                self.config.enable_polygon = False

    async def run(self, symbols: list[Symbol]) -> None:
        """Main loop: poll for edges and execute when thresholds are met."""
        while True:
            try:
                await asyncio.gather(*(self._scan_symbol(sym) for sym in symbols))
            except Exception:
                log.exception("arbitrage.scan_failed")
                self.failures += 1

            await asyncio.sleep(self.config.poll_interval)

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

        base_qty = float(best.expected_output)
        if base_qty > self.config.max_position and base_qty > 0:
            scale = self.config.max_position / base_qty
            base_qty = self.config.max_position
            amount_in *= Decimal(str(scale))

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

        # Use chain-specific token addresses when executing on Polygon
        exec_token_in = polygon_token_in if best.chain == "polygon" else token_in
        exec_token_out = polygon_token_out if best.chain == "polygon" else token_out
        await self._execute(symbol, exec_token_in, exec_token_out, base_qty, amount_in, dex_executor)

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
            net_edge_bps = edge_bps - fee_bps
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
                    metadata={"pool": primary_quote.get("pool_address")},
                )
            )
        except Exception:
            log.exception("arbitrage.quote_failed", symbol=symbol)
            self.failures += 1

        if not self.config.enable_polygon:
            return candidates

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
            net_edge_bps = edge_bps - fee_bps
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
                    metadata=polygon_quote["metadata"],
                )
            )

        return candidates

    def _pick_best_candidate(self, candidates: Sequence[QuoteCandidate]) -> QuoteCandidate | None:
        if not candidates:
            return None
        return max(candidates, key=lambda c: c.net_edge_bps)

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
            return 0.0

        cost_native = gas_price_gwei * 1e-9 * gas_limit
        cost_quote = cost_native * native_price
        return (cost_quote / notional_quote) * 10_000

    def _bridge_penalty_bps(self, notional_quote: float) -> float:
        if notional_quote <= 0:
            return 0.0

        cost_usd = self.config.bridge_fee_flat_usd + (notional_quote * self.config.bridge_fee_pct)
        penalty_bps = (cost_usd / notional_quote) * 10_000
        return penalty_bps + self.config.bridge_time_penalty_bps

    async def _get_gas_price_gwei(self, chain: str) -> float | None:
        try:
            if chain == "polygon" and self._polygon_w3:
                price_wei = await self._polygon_w3.eth.gas_price
                return float(price_wei) / 1e9

            if chain != "polygon" and hasattr(self.dex, "web3"):
                price_wei = await self.dex.web3.w3.eth.gas_price
                return float(price_wei) / 1e9
        except Exception:
            log.debug("arbitrage.gas_price_lookup_failed", chain=chain)

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
        """Fetch a Polygon quote via 1inch."""
        api_key = os.getenv("ONEINCH_API_KEY") or os.getenv("ONEINCH_TOKEN")
        if not api_key:
            log.debug("arbitrage.oneinch_missing_api_key")
            return None

        decimals_in = self._get_token_decimals(quote_symbol)
        amount_in_wei = int(amount_in * Decimal(10**decimals_in))

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
        except Exception:
            log.debug("arbitrage.polygon_quote_failed", symbol=symbol)
            return None

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

    async def _execute(
        self,
        symbol: Symbol,
        token_in: str,
        token_out: str,
        base_qty: float,
        amount_in_quote: Decimal,
        dex_executor: UniswapConnector | None = None,
    ) -> str | None:
        """Execute DEX buy + CEX sell."""
        executor = dex_executor or self.dex
        try:
            tx_hash = await executor.execute_market_swap(
                token_in=token_in,
                token_out=token_out,
                amount_in=amount_in_quote,
                slippage_tolerance=Decimal(str(self.config.slippage_tolerance)),
            )
            log.info("arbitrage.dex_swap_submitted", symbol=symbol, tx_hash=tx_hash)
        except Exception:
            self.failures += 1
            log.exception("arbitrage.dex_swap_failed", symbol=symbol)
            return None

        sell_order = Order(
            symbol=symbol,
            side=Side.SELL,
            quantity=base_qty,
            order_type=OrderType.MARKET,
        )

        try:
            await self.router.submit_orders([sell_order])
            self.trades_executed += 1
            log.info("arbitrage.cex_sell_submitted", symbol=symbol, quantity=base_qty)
        except Exception:
            self.failures += 1
            log.exception("arbitrage.cex_sell_failed", symbol=symbol)
            return tx_hash

        return tx_hash
