"""Lightweight arbitrage runner using CEX router and Uniswap connector.

This is intentionally conservative: it looks for clear price edges, enforces
slippage/position/gas limits, and logs failures for monitoring.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Awaitable, Callable, Mapping

import structlog

from src.brokers.routing import OrderRouter
from src.core.execution import Order, OrderType, Side
from src.core.types import Price, Symbol
from src.dex.uniswap_connector import UniswapConnector

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


@dataclass
class ArbitrageRunner:
    """Scan for DEX/CEX price edges and route orders."""

    router: OrderRouter
    dex: UniswapConnector
    price_fetcher: PriceFetcher
    token_addresses: Mapping[str, str]
    config: ArbitrageConfig = field(default_factory=ArbitrageConfig)

    trades_executed: int = 0
    trades_skipped: int = 0
    failures: int = 0

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

        try:
            quote_data = await self.dex.get_quote(
                token_in=token_in,
                token_out=token_out,
                amount_in=amount_in,
            )
        except Exception:
            log.exception("arbitrage.quote_failed", symbol=symbol)
            self.failures += 1
            return

        dex_price = float(quote_data["expected_output"] / amount_in)
        edge_bps = (cex_price - dex_price) / dex_price * 10_000

        if edge_bps < self.config.min_edge_bps:
            self.trades_skipped += 1
            return

        base_qty = float(quote_data["expected_output"])
        if base_qty > self.config.max_position:
            base_qty = self.config.max_position

        log.info(
            "arbitrage.opportunity",
            symbol=symbol,
            cex_price=cex_price,
            dex_price=dex_price,
            edge_bps=edge_bps,
            base_qty=base_qty,
        )

        if not self.config.enable_execution:
            return

        await self._execute(symbol, token_in, token_out, base_qty, amount_in)

    async def _execute(
        self,
        symbol: Symbol,
        token_in: str,
        token_out: str,
        base_qty: float,
        amount_in_quote: Decimal,
    ) -> str | None:
        """Execute DEX buy + CEX sell."""
        try:
            tx_hash = await self.dex.execute_market_swap(
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
