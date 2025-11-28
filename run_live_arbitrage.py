"""
Complete live arbitrage system combining CEX and DEX trading.

This script:
1. Fetches prices from CEX (Binance, etc.)
2. Gets quotes from DEX (Uniswap)
3. Calculates arbitrage opportunities
4. Executes profitable trades (CEX or flash loans)

SAFETY: Starts in DRY_RUN mode by default!
"""

import asyncio
import os
import sys
from decimal import Decimal

import structlog
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.brokers.binance_adapter import BinanceAdapter
from src.brokers.price_fetcher import CEXPriceFetcher
from src.brokers.routing import OrderRouter
from src.core.types import Symbol
from src.dex.config import UniswapConfig, Chain
from src.dex.uniswap_connector import UniswapConnector
from src.live.flash_arb_runner import FlashArbConfig, FlashArbitrageRunner

log = structlog.get_logger()


class ArbitrageSystem:
    """Complete arbitrage trading system."""

    def __init__(
        self,
        dry_run: bool = True,
        enable_flash_loans: bool = True,
    ):
        """Initialize arbitrage system.

        Args:
            dry_run: If True, no real trades are executed
            enable_flash_loans: Enable flash loan arbitrage
        """
        self.dry_run = dry_run
        self.enable_flash_loans = enable_flash_loans

        # Initialize components
        log.info("arbitrage_system.initializing", dry_run=dry_run)

        # 1. CEX Price Fetcher
        self.price_fetcher = CEXPriceFetcher(
            binance_enabled=True,
            alpaca_enabled=False,  # Can enable if needed
        )

        # 2. DEX Connector (Uniswap)
        self.dex = self._init_uniswap()

        # 3. CEX Order Router
        self.router = self._init_router()

        # 4. Token addresses (mainnet)
        self.token_addresses = {
            "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
            "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
            "ETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
            "BTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",  # WBTC
        }

        # 5. Configure arbitrage parameters
        self.config = FlashArbConfig(
            # Scanning settings
            min_edge_bps=25.0,  # 0.25% minimum spread
            poll_interval=5.0,  # Check every 5 seconds
            max_notional=1000.0,  # $1000 max for regular arb

            # Flash loan settings
            enable_flash_loans=enable_flash_loans,
            min_flash_profit_eth=0.1,  # 0.1 ETH minimum profit
            max_flash_borrow_eth=10.0,  # Max 10 ETH borrow
            flash_loan_threshold_bps=50.0,  # 0.5% spread needed

            # Position/risk settings
            max_position=1.0,  # Max 1 unit position
            slippage_tolerance=0.01,  # 1% slippage

            # Safety
            enable_execution=not dry_run,  # Only execute if not dry run
        )

        # Symbols to scan
        self.symbols = [
            "ETH/USDC",
            "WETH/USDC",
            "BTC/USDT",
            # Add more pairs as needed
        ]

        log.info(
            "arbitrage_system.ready",
            symbols=self.symbols,
            dry_run=dry_run,
            flash_loans=enable_flash_loans,
        )

    def _init_uniswap(self) -> UniswapConnector:
        """Initialize Uniswap connector."""
        # Get config from environment
        config = UniswapConfig(
            thegraph_api_key=os.getenv("THEGRAPH_API_KEY", ""),
            ethereum_rpc_url=os.getenv("ETH_RPC_URL", ""),
            private_key=os.getenv("PRIVATE_KEY"),
        )

        return UniswapConnector(config, chain=Chain.ETHEREUM)

    def _init_router(self) -> OrderRouter:
        """Initialize order router with available connectors."""
        # For now, create a simple router
        # You can enhance this to connect to actual CEX adapters
        connectors = {}

        # Add Binance if credentials available
        if os.getenv("BINANCE_API_KEY") and os.getenv("BINANCE_API_KEY") != "your_binance_key_here":
            try:
                binance = BinanceAdapter(
                    api_key=os.getenv("BINANCE_API_KEY", ""),
                    api_secret=os.getenv("BINANCE_API_SECRET", ""),
                    testnet=os.getenv("BINANCE_TESTNET", "true").lower() == "true",
                )
                connectors["binance"] = binance
                log.info("arbitrage_system.binance_connected")
            except Exception as e:
                log.warning("arbitrage_system.binance_failed", error=str(e))

        return OrderRouter(connectors=connectors)

    async def run(self):
        """Run the arbitrage system."""
        print("=" * 70)
        print("🤖 LIVE ARBITRAGE SYSTEM")
        print("=" * 70)
        print(f"Mode: {'🧪 DRY RUN' if self.dry_run else '💰 LIVE TRADING'}")
        print(f"Flash Loans: {'✅ Enabled' if self.enable_flash_loans else '❌ Disabled'}")
        print(f"Symbols: {', '.join(self.symbols)}")
        print(f"Min Edge: {self.config.min_edge_bps} bps")
        print("=" * 70)
        print()

        if not self.dry_run:
            print("⚠️  WARNING: LIVE TRADING ENABLED!")
            print("⚠️  Real money will be used!")
            print()
            response = input("Type 'START' to confirm: ")
            if response != "START":
                print("❌ Cancelled")
                return

        print("🔍 Starting scanner... Press Ctrl+C to stop")
        print()

        try:
            # Create price fetcher wrapper
            async def price_fetcher(symbol: Symbol):
                return await self.price_fetcher.get_price(symbol)

            # Create and run arbitrage runner
            runner = FlashArbitrageRunner(
                router=self.router,
                dex=self.dex,
                price_fetcher=price_fetcher,
                token_addresses=self.token_addresses,
                config=self.config,
            )

            await runner.run(self.symbols)

        except KeyboardInterrupt:
            print("\n\n⏹️  System stopped by user")
            stats = runner.get_stats() if 'runner' in locals() else {}
            log.info("arbitrage_system.stopped", stats=stats)
            print(f"\n📊 Final Stats: {stats}")

        except Exception as e:
            print(f"\n\n❌ System error: {e}")
            log.exception("arbitrage_system.error")
            raise


async def main():
    """Main entry point."""

    # Parse command line arguments
    dry_run = "--live" not in sys.argv
    enable_flash = "--no-flash" not in sys.argv

    if not dry_run:
        print("⚠️  LIVE MODE REQUESTED")
        print()

    # Create and run system
    system = ArbitrageSystem(
        dry_run=dry_run,
        enable_flash_loans=enable_flash,
    )

    await system.run()


if __name__ == "__main__":
    print()
    print("=" * 70)
    print("💰 ARBITRAGE SYSTEM - MAINNET")
    print("=" * 70)
    print()
    print("Usage:")
    print("  python run_live_arbitrage.py           # Dry run mode (safe)")
    print("  python run_live_arbitrage.py --live    # Live trading (⚠️  real money!)")
    print("  python run_live_arbitrage.py --no-flash # Disable flash loans")
    print()

    asyncio.run(main())
