"""Enhanced arbitrage runner with flash loan execution.

Combines the existing CEX/DEX arbitrage scanner with flash loan capabilities
for executing larger, capital-free arbitrage trades.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Awaitable, Callable, Optional

import structlog
from web3 import Web3

from src.dex.flash_loan_executor import FlashLoanExecutor, FlashLoanSettings, ProfitabilityCheck
from src.live.arbitrage_runner import ArbitrageConfig, ArbitrageRunner, PriceFetcher
from src.brokers.routing import OrderRouter
from src.core.types import Price, Symbol
from src.dex.uniswap_connector import UniswapConnector

log = structlog.get_logger()


@dataclass
class FlashArbConfig(ArbitrageConfig):
    """Extended config for flash loan arbitrage."""

    # Flash loan specific
    min_flash_profit_eth: float = 0.5  # Minimum profit for flash loan arb
    max_flash_borrow_eth: float = 100.0  # Maximum to borrow per trade
    enable_flash_loans: bool = False  # Enable flash loan execution
    flash_loan_threshold_bps: float = 100.0  # Min spread to consider flash loans (1%)

    # Use smaller amounts for regular CEX/DEX arb
    max_notional: float = 100.0  # Smaller for non-flash trades


@dataclass
class FlashArbitrageRunner(ArbitrageRunner):
    """Arbitrage runner with flash loan execution capabilities."""

    flash_executor: Optional[FlashLoanExecutor] = None
    config: FlashArbConfig = field(default_factory=FlashArbConfig)
    on_opportunity: Optional[Callable[[dict], Awaitable[None] | None]] = None
    on_trade: Optional[Callable[[dict], Awaitable[None] | None]] = None

    flash_executions: int = 0
    flash_failures: int = 0

    def __post_init__(self) -> None:
        """Initialize flash loan executor if enabled."""
        if self.config.enable_flash_loans and self.flash_executor is None:
            try:
                self.flash_executor = FlashLoanExecutor()
                log.info("flash_arb.executor_initialized")
            except Exception:
                log.exception("flash_arb.executor_init_failed")
                self.config.enable_flash_loans = False

    async def _scan_symbol(self, symbol: Symbol) -> None:
        """Scan symbol and choose between regular or flash loan arbitrage."""
        if "/" not in symbol:
            self.trades_skipped += 1
            return

        base, quote = symbol.split("/", 1)
        token_in = self.token_addresses.get(quote)
        token_out = self.token_addresses.get(base)

        if not token_in or not token_out:
            self.trades_skipped += 1
            return

        # Get CEX price
        cex_price = await self.price_fetcher(symbol)
        if cex_price is None or cex_price <= 0:
            self.trades_skipped += 1
            return

        # Get DEX quote for small amount first
        test_amount = Decimal("1.0")  # 1 unit for price discovery
        try:
            quote_data = await self.dex.get_quote(
                token_in=token_in,
                token_out=token_out,
                amount_in=test_amount,
            )
        except Exception:
            log.exception("flash_arb.quote_failed", symbol=symbol)
            self.failures += 1
            return

        dex_price = float(quote_data["expected_output"] / test_amount)
        edge_bps = (cex_price - dex_price) / dex_price * 10_000

        log.debug(
            "flash_arb.price_check",
            symbol=symbol,
            cex_price=cex_price,
            dex_price=dex_price,
            edge_bps=edge_bps,
        )

        # Decide execution method based on spread
        if (
            self.config.enable_flash_loans
            and self.flash_executor
            and edge_bps >= self.config.flash_loan_threshold_bps
        ):
            await self._emit_opportunity(
                {
                    "symbol": symbol,
                    "edge_bps": edge_bps,
                    "cex_price": cex_price,
                    "dex_price": dex_price,
                    "execution_path": "flash_loan",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
            # Large spread - use flash loan for bigger size
            await self._execute_flash_arb(symbol, token_in, token_out, cex_price, dex_price, edge_bps)
        elif edge_bps >= self.config.min_edge_bps:
            await self._emit_opportunity(
                {
                    "symbol": symbol,
                    "edge_bps": edge_bps,
                    "cex_price": cex_price,
                    "dex_price": dex_price,
                    "execution_path": "regular",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
            # Small spread - use regular CEX/DEX arb
            await self._execute_regular_arb(symbol, token_in, token_out, cex_price, dex_price)
        else:
            # No opportunity
            self.trades_skipped += 1

    async def _execute_flash_arb(
        self,
        symbol: Symbol,
        token_in: str,
        token_out: str,
        cex_price: float,
        dex_price: float,
        edge_bps: float,
    ) -> None:
        """Execute arbitrage using flash loan for larger capital."""
        if not self.flash_executor:
            return

        # Calculate optimal borrow amount (conservative)
        # Use max borrow but cap based on risk
        borrow_amount_eth = min(
            self.config.max_flash_borrow_eth,
            self.config.max_flash_borrow_eth * (edge_bps / self.config.flash_loan_threshold_bps),
        )

        # Estimate profit (simple calculation - actual will vary with slippage)
        estimated_profit_eth = borrow_amount_eth * (edge_bps / 10_000)

        log.info(
            "flash_arb.opportunity_detected",
            symbol=symbol,
            edge_bps=edge_bps,
            borrow_amount_eth=borrow_amount_eth,
            estimated_profit_eth=estimated_profit_eth,
        )

        try:
            # Build arbitrage plan
            arb_plan = self.flash_executor.build_weth_usdc_arb_plan(
                borrow_amount_eth=borrow_amount_eth,
                expected_profit_eth=estimated_profit_eth,
                min_profit_eth=self.config.min_flash_profit_eth,
            )

            # Calculate profitability
            borrow_wei = Web3.to_wei(borrow_amount_eth, "ether")
            profit_wei = Web3.to_wei(estimated_profit_eth, "ether")

            profitability: ProfitabilityCheck = self.flash_executor.calculate_profitability(
                borrow_amount=borrow_wei,
                expected_profit=profit_wei,
            )

            if not profitability.is_profitable:
                log.info(
                    "flash_arb.not_profitable_after_fees",
                    symbol=symbol,
                    net_profit=profitability.net_profit,
                )
                self.trades_skipped += 1
                return

            log.info(
                "flash_arb.profitability_check_passed",
                symbol=symbol,
                net_profit_eth=Web3.from_wei(profitability.net_profit, "ether"),
                roi_bps=profitability.roi_bps,
            )

            if not self.config.enable_execution:
                log.info("flash_arb.dry_run", symbol=symbol)
                await self._emit_trade(
                    {
                        "symbol": symbol,
                        "mode": "flash_loan",
                        "borrow_amount_eth": borrow_amount_eth,
                        "estimated_profit_eth": estimated_profit_eth,
                        "executed": False,
                        "tx_hash": None,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )
                return

            # Execute the flash loan
            weth_address = self.flash_executor.settings.weth_address
            receipt = self.flash_executor.execute_flash_loan(
                loan_asset=weth_address,
                loan_amount=borrow_wei,
                arb_plan=arb_plan,
                dry_run=False,
            )

            if receipt and receipt["status"] == 1:
                self.flash_executions += 1
                log.info(
                    "flash_arb.execution_success",
                    symbol=symbol,
                    tx_hash=receipt["transactionHash"].hex(),
                    gas_used=receipt["gasUsed"],
                )
                await self._emit_trade(
                    {
                        "symbol": symbol,
                        "mode": "flash_loan",
                        "borrow_amount_eth": borrow_amount_eth,
                        "estimated_profit_eth": estimated_profit_eth,
                        "executed": True,
                        "tx_hash": receipt["transactionHash"].hex(),
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )
            else:
                self.flash_failures += 1
                log.error("flash_arb.execution_failed", symbol=symbol, receipt=receipt)

        except Exception:
            self.flash_failures += 1
            log.exception("flash_arb.execution_error", symbol=symbol)

    async def _execute_regular_arb(
        self,
        symbol: Symbol,
        token_in: str,
        token_out: str,
        cex_price: float,
        dex_price: float,
    ) -> None:
        """Execute regular CEX/DEX arbitrage (small size, from parent class)."""
        # Use parent class logic for regular arbitrage
        notional_quote = min(self.config.max_notional, cex_price * self.config.max_position)
        amount_in = Decimal(str(notional_quote))

        try:
            quote_data = await self.dex.get_quote(
                token_in=token_in,
                token_out=token_out,
                amount_in=amount_in,
            )
        except Exception:
            log.exception("flash_arb.regular_quote_failed", symbol=symbol)
            self.failures += 1
            return

        base_qty = float(quote_data["expected_output"])
        if base_qty > self.config.max_position:
            base_qty = self.config.max_position

        edge_bps = (cex_price - dex_price) / dex_price * 10_000

        log.info(
            "flash_arb.regular_opportunity",
            symbol=symbol,
            edge_bps=edge_bps,
            base_qty=base_qty,
        )

        if not self.config.enable_execution:
            await self._emit_trade(
                {
                    "symbol": symbol,
                    "mode": "regular",
                    "base_qty": base_qty,
                    "edge_bps": edge_bps,
                    "executed": False,
                    "tx_hash": None,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
            return

        # Execute via parent class method
        tx_hash = await self._execute(symbol, token_in, token_out, base_qty, amount_in)
        await self._emit_trade(
            {
                "symbol": symbol,
                "mode": "regular",
                "base_qty": base_qty,
                "edge_bps": edge_bps,
                "executed": True,
                "tx_hash": tx_hash,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def get_stats(self) -> dict:
        """Get execution statistics."""
        return {
            "regular_trades": self.trades_executed,
            "flash_trades": self.flash_executions,
            "total_trades": self.trades_executed + self.flash_executions,
            "skipped": self.trades_skipped,
            "regular_failures": self.failures,
            "flash_failures": self.flash_failures,
            "total_failures": self.failures + self.flash_failures,
        }

    async def _emit_opportunity(self, payload: dict) -> None:
        """Notify dashboard/listeners about an opportunity if hook is provided."""
        if not self.on_opportunity:
            return

        result = self.on_opportunity(payload)
        if asyncio.iscoroutine(result):
            await result

    async def _emit_trade(self, payload: dict) -> None:
        """Notify dashboard/listeners about executed or simulated trades."""
        if not self.on_trade:
            return

        result = self.on_trade(payload)
        if asyncio.iscoroutine(result):
            await result


async def run_flash_arbitrage_scanner(
    symbols: list[Symbol],
    router: OrderRouter,
    dex: UniswapConnector,
    price_fetcher: PriceFetcher,
    token_addresses: dict[str, str],
    config: Optional[FlashArbConfig] = None,
) -> None:
    """Main entry point for running flash arbitrage scanner.

    Args:
        symbols: List of symbols to scan (e.g., ["ETH/USDC", "BTC/USDT"])
        router: Order router for CEX execution
        dex: Uniswap connector for DEX execution
        price_fetcher: Function to fetch CEX prices
        token_addresses: Mapping of symbols to token addresses
        config: Configuration (uses defaults if None)
    """
    cfg = config or FlashArbConfig()

    runner = FlashArbitrageRunner(
        router=router,
        dex=dex,
        price_fetcher=price_fetcher,
        token_addresses=token_addresses,
        config=cfg,
    )

    log.info(
        "flash_arb.scanner_starting",
        symbols=symbols,
        enable_flash=cfg.enable_flash_loans,
        enable_execution=cfg.enable_execution,
    )

    try:
        await runner.run(symbols)
    except KeyboardInterrupt:
        stats = runner.get_stats()
        log.info("flash_arb.scanner_stopped", stats=stats)
    except Exception:
        stats = runner.get_stats()
        log.exception("flash_arb.scanner_failed", stats=stats)
        raise
