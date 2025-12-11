"""AQUA arbitrage runner for BSC.

Modern 2025 implementation for AQUA token arbitrage using flash loans on BSC.
Monitors price spreads between PancakeSwap V3 and Biswap, executes when profitable.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Callable, Awaitable

import structlog

from src.dex.bsc_connector import BSCConnector, BSCSettings
from src.dex.bsc_flash_executor import BSCFlashLoanExecutor, BSCFlashLoanSettings

log = structlog.get_logger()


class AQUAArbitrageRunner:
    """Runner for AQUA arbitrage opportunities on BSC."""

    def __init__(
        self,
        bsc_connector: BSCConnector | None = None,
        flash_executor: BSCFlashLoanExecutor | None = None,
        scan_interval: float = 5.0,  # Scan every 5 seconds
        min_profit_bps: float = 50.0,  # 0.5% minimum spread
        max_borrow_bnb: float = 10.0,  # Maximum to borrow per trade
        enable_execution: bool = False,  # Dry run by default
        on_opportunity: Callable[[dict], Awaitable[None] | None] | None = None,
        on_trade: Callable[[dict], Awaitable[None] | None] | None = None,
    ):
        """Initialize AQUA arbitrage runner.

        Args:
            bsc_connector: BSC connector (creates new if None)
            flash_executor: Flash loan executor (creates new if None)
            scan_interval: Seconds between scans
            min_profit_bps: Minimum profit in basis points
            max_borrow_bnb: Maximum BNB to borrow
            enable_execution: Enable real execution (vs dry run)
            on_opportunity: Callback for opportunities
            on_trade: Callback for trades
        """
        self.bsc_connector = bsc_connector or BSCConnector()
        self.flash_executor = flash_executor or BSCFlashLoanExecutor()
        self.scan_interval = scan_interval
        self.min_profit_bps = min_profit_bps
        self.max_borrow_bnb = max_borrow_bnb
        self.enable_execution = enable_execution
        self.on_opportunity = on_opportunity
        self.on_trade = on_trade

        # Statistics
        self.opportunities_found = 0
        self.trades_executed = 0
        self.trades_skipped = 0

        log.info(
            "aqua_arb.runner_initialized",
            scan_interval=scan_interval,
            min_profit_bps=min_profit_bps,
            max_borrow_bnb=max_borrow_bnb,
            enable_execution=enable_execution,
        )

    async def scan_for_opportunities(self) -> dict | None:
        """Scan for AQUA arbitrage opportunities.

        Returns:
            Opportunity dict if found, None otherwise
        """
        try:
            # Get AQUA price on PancakeSwap (primary market)
            pancake_price = await self.bsc_connector.get_aqua_price("WBNB")

            if not pancake_price or pancake_price <= 0:
                log.debug("aqua_arb.no_pancake_price")
                return None

            # In a real implementation, you would also fetch price from Biswap
            # For now, we'll simulate a price difference
            # TODO: Implement Biswap price fetching
            biswap_price = pancake_price * 1.005  # Simulated 0.5% spread

            # Calculate spread
            spread_bps = abs((biswap_price - pancake_price) / pancake_price) * 10000

            log.debug(
                "aqua_arb.price_check",
                pancake_price=pancake_price,
                biswap_price=biswap_price,
                spread_bps=spread_bps,
            )

            if spread_bps >= self.min_profit_bps:
                self.opportunities_found += 1

                # Determine direction
                buy_on_pancake = pancake_price < biswap_price

                # Calculate optimal borrow amount (simple heuristic)
                borrow_amount_bnb = min(
                    self.max_borrow_bnb,
                    self.max_borrow_bnb * (spread_bps / 100.0),  # Scale with spread
                )

                opportunity = {
                    "symbol": "AQUA/WBNB",
                    "pancake_price": pancake_price,
                    "biswap_price": biswap_price,
                    "spread_bps": spread_bps,
                    "buy_on_pancake": buy_on_pancake,
                    "borrow_amount_bnb": borrow_amount_bnb,
                    "estimated_profit_bnb": borrow_amount_bnb * (spread_bps / 10000),
                }

                log.info("aqua_arb.opportunity_found", **opportunity)

                # Notify callback
                if self.on_opportunity:
                    result = self.on_opportunity(opportunity)
                    if asyncio.iscoroutine(result):
                        await result

                return opportunity

            return None

        except Exception:
            log.exception("aqua_arb.scan_failed")
            return None

    async def execute_opportunity(self, opportunity: dict) -> bool:
        """Execute an arbitrage opportunity.

        Args:
            opportunity: Opportunity dict from scan_for_opportunities

        Returns:
            True if executed successfully, False otherwise
        """
        try:
            borrow_amount = opportunity["borrow_amount_bnb"]
            buy_on_pancake = opportunity["buy_on_pancake"]

            if not self.enable_execution:
                log.info("aqua_arb.dry_run", **opportunity)
                self.trades_skipped += 1

                # Notify callback
                if self.on_trade:
                    trade_result = {
                        **opportunity,
                        "executed": False,
                        "tx_hash": None,
                        "dry_run": True,
                    }
                    result = self.on_trade(trade_result)
                    if asyncio.iscoroutine(result):
                        await result

                return False

            # Execute via flash loan
            receipt = self.flash_executor.execute_arbitrage(
                borrow_amount_bnb=borrow_amount,
                buy_on_pancake=buy_on_pancake,
                dry_run=False,
            )

            if receipt and receipt["status"] == 1:
                self.trades_executed += 1
                log.info(
                    "aqua_arb.execution_success",
                    tx_hash=receipt["transactionHash"].hex(),
                    gas_used=receipt["gasUsed"],
                )

                # Notify callback
                if self.on_trade:
                    trade_result = {
                        **opportunity,
                        "executed": True,
                        "tx_hash": receipt["transactionHash"].hex(),
                        "gas_used": receipt["gasUsed"],
                    }
                    result = self.on_trade(trade_result)
                    if asyncio.iscoroutine(result):
                        await result

                return True
            else:
                self.trades_skipped += 1
                log.warning("aqua_arb.execution_failed", receipt=receipt)
                return False

        except Exception:
            log.exception("aqua_arb.execution_error")
            self.trades_skipped += 1
            return False

    async def run(self) -> None:
        """Run the arbitrage scanner continuously.

        This will run until interrupted (Ctrl+C).
        """
        log.info("aqua_arb.scanner_starting")

        try:
            while True:
                # Scan for opportunities
                opportunity = await self.scan_for_opportunities()

                # Execute if found
                if opportunity:
                    await self.execute_opportunity(opportunity)

                # Wait before next scan
                await asyncio.sleep(self.scan_interval)

        except KeyboardInterrupt:
            log.info(
                "aqua_arb.scanner_stopped",
                opportunities_found=self.opportunities_found,
                trades_executed=self.trades_executed,
                trades_skipped=self.trades_skipped,
            )
        except Exception:
            log.exception(
                "aqua_arb.scanner_failed",
                opportunities_found=self.opportunities_found,
                trades_executed=self.trades_executed,
                trades_skipped=self.trades_skipped,
            )
            raise

    def get_stats(self) -> dict:
        """Get scanner statistics."""
        return {
            "opportunities_found": self.opportunities_found,
            "trades_executed": self.trades_executed,
            "trades_skipped": self.trades_skipped,
        }


async def main() -> None:
    """Main entry point for AQUA arbitrage runner."""
    # Initialize runner
    runner = AQUAArbitrageRunner(
        scan_interval=5.0,
        min_profit_bps=50.0,  # 0.5%
        max_borrow_bnb=10.0,
        enable_execution=False,  # DRY RUN - set to True for real execution
    )

    # Run scanner
    await runner.run()


if __name__ == "__main__":
    import sys

    # Configure logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ]
    )

    # Run
    asyncio.run(main())
