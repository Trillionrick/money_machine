"""Run AI-Integrated Arbitrage System.

This script starts the complete AI/ML-powered arbitrage system with:
- On-chain flash loan arbitrage
- Off-chain CEX arbitrage
- AI decision-making and opportunity scoring
- Profit maximization optimization
- Adaptive learning from execution results

SAFETY: Starts in DRY RUN mode by default. Set ENABLE_EXECUTION=true to trade live.
"""

import asyncio
import os
from pathlib import Path

import structlog
from dotenv import load_dotenv
from web3 import AsyncHTTPProvider, AsyncWeb3

from src.ai.advanced_decider import AdvancedAIConfig
from src.ai.profit_maximizer import ProfitMaximizerConfig
from src.ai.unified_orchestrator import OrchestratorConfig
from src.brokers.kraken_adapter import KrakenAdapter
from src.brokers.price_fetcher import CEXPriceFetcher
from src.brokers.routing import OrderRouter
from src.core.types import Symbol
from src.dex.config import Chain, UniswapConfig
from src.dex.flash_loan_executor import FlashLoanExecutor, FlashLoanSettings
from src.dex.uniswap_connector import UniswapConnector
from src.live.ai_integrated_runner import AIIntegratedArbitrageRunner, AIIntegratedConfig
from src.live.arbitrage_runner import ArbitrageConfig

# Load environment
load_dotenv()

log = structlog.get_logger()

# Trading pairs focused on high liquidity and flash loan opportunities
TRADING_SYMBOLS: list[Symbol] = [
    "ETH/USDC",
    "WETH/USDC",
    "ETH/USDT",
    "WBTC/USDC",
    "BTC/USDT",
    "USDT/USDC",
    "DAI/USDC",
]

# Token addresses (Ethereum mainnet)
TOKEN_ADDRESSES = {
    "ETH": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
    "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
    "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
    "BTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",  # Same as WBTC
}


class AIIntegratedArbitrageSystem:
    """Complete AI-integrated arbitrage system."""

    def __init__(self, dry_run: bool = True):
        """Initialize the system.

        Args:
            dry_run: If True, simulate trades without real execution
        """
        self.dry_run = dry_run

        # Load configuration from environment
        self._load_config()

        # Initialize components
        self._init_web3()
        self._init_price_fetcher()
        self._init_dex_connectors()
        self._init_flash_executor()
        self._init_order_router()
        self._init_ai_runner()

        log.info(
            "ai_integrated_system.initialized",
            dry_run=self.dry_run,
            ai_mode=self.ai_mode,
            enable_flash_loans=self.enable_flash_loans,
            enable_cex_execution=self.enable_cex_execution,
        )

    def _load_config(self) -> None:
        """Load configuration from environment variables."""
        # Mode configuration
        self.ai_mode = os.getenv("AI_MODE", "conservative")  # conservative, balanced, aggressive
        self.dry_run = os.getenv("ENABLE_EXECUTION", "false").lower() != "true"

        # Execution controls
        self.enable_flash_loans = os.getenv("ENABLE_FLASH_LOANS", "true").lower() == "true"
        self.enable_cex_execution = os.getenv("ENABLE_CEX_EXECUTION", "true").lower() == "true"
        self.enable_profit_maximization = os.getenv("ENABLE_PROFIT_MAXIMIZATION", "true").lower() == "true"

        # Capital and targets
        self.current_capital_eth = float(os.getenv("CURRENT_CAPITAL_ETH", "100.0"))
        self.target_capital_eth = float(os.getenv("TARGET_CAPITAL_ETH", "1000.0"))

        # Risk management
        self.ai_min_confidence = float(os.getenv("AI_MIN_CONFIDENCE", "0.70"))
        self.flash_loan_min_profit = float(os.getenv("FLASH_LOAN_MIN_PROFIT_ETH", "0.15"))
        self.cex_min_profit = float(os.getenv("CEX_MIN_PROFIT_USD", "50.0"))

        # Network configuration
        self.eth_rpc_url = os.getenv("ETH_RPC_URL") or os.getenv("ETHEREUM_RPC_URL")
        self.polygon_rpc_url = os.getenv("POLYGON_RPC_URL")

        if not self.eth_rpc_url:
            raise ValueError("ETH_RPC_URL not set in environment")

    def _init_web3(self) -> None:
        """Initialize Web3 connections."""
        self.w3_eth = AsyncWeb3(AsyncHTTPProvider(self.eth_rpc_url.strip()))
        self.w3_polygon = (
            AsyncWeb3(AsyncHTTPProvider(self.polygon_rpc_url.strip()))
            if self.polygon_rpc_url
            else None
        )

        log.info("web3.initialized", ethereum=bool(self.w3_eth), polygon=bool(self.w3_polygon))

    def _init_price_fetcher(self) -> None:
        """Initialize CEX price fetcher with multiple brokers."""
        self.price_fetcher = CEXPriceFetcher()

        # Add Kraken (primary)
        try:
            kraken = KrakenAdapter(
                api_key=os.getenv("KRAKEN_API_KEY", ""),
                api_secret=os.getenv("KRAKEN_API_SECRET", ""),
            )
            self.price_fetcher.add_broker(kraken)
            log.info("price_fetcher.kraken_added")
        except Exception as e:
            log.warning("price_fetcher.kraken_failed", error=str(e))

        # Could add more brokers (Binance, Coinbase, etc.) here

    def _init_dex_connectors(self) -> None:
        """Initialize DEX connectors for quotes."""
        # Ethereum Uniswap V3
        eth_config = UniswapConfig(chain=Chain.ETHEREUM)
        self.dex_eth = UniswapConnector(config=eth_config, web3_client=self.w3_eth)

        # Polygon Uniswap/QuickSwap V3 (if available)
        self.dex_polygon = None
        if self.w3_polygon:
            polygon_config = UniswapConfig(chain=Chain.POLYGON)
            self.dex_polygon = UniswapConnector(config=polygon_config, web3_client=self.w3_polygon)

        log.info("dex.initialized", ethereum=True, polygon=bool(self.dex_polygon))

    def _init_flash_executor(self) -> None:
        """Initialize flash loan executor."""
        self.flash_executor = None

        if not self.enable_flash_loans:
            log.info("flash_executor.disabled")
            return

        try:
            # Check if flash loan contract is configured
            arb_contract = os.getenv("ARB_CONTRACT_ADDRESS")
            if not arb_contract:
                log.warning("flash_executor.no_contract_address")
                return

            flash_settings = FlashLoanSettings(
                arb_contract_address=arb_contract,
                eth_rpc_url=self.eth_rpc_url,
                private_key=os.getenv("PRIVATE_KEY", ""),
            )

            self.flash_executor = FlashLoanExecutor(settings=flash_settings)
            log.info("flash_executor.initialized")

        except Exception as e:
            log.warning("flash_executor.init_failed", error=str(e))

    def _init_order_router(self) -> None:
        """Initialize order router for CEX execution."""
        self.order_router = OrderRouter()

        # Add Kraken as execution venue
        try:
            kraken = KrakenAdapter(
                api_key=os.getenv("KRAKEN_API_KEY", ""),
                api_secret=os.getenv("KRAKEN_API_SECRET", ""),
            )
            connectors["kraken"] = kraken
            log.info("order_router.kraken_added")
        except Exception as e:
            log.warning("order_router.kraken_failed", error=str(e))

    def _init_ai_runner(self) -> None:
        """Initialize AI-integrated arbitrage runner."""
        # Build configurations based on AI mode
        arbitrage_config = ArbitrageConfig(
            min_edge_bps=30.0 if self.ai_mode == "aggressive" else 40.0,
            max_notional=2000.0 if self.ai_mode == "aggressive" else 1000.0,
            enable_execution=not self.dry_run,
            poll_interval=2.0,
        )

        ai_config = AdvancedAIConfig(
            confidence_threshold=self.ai_min_confidence,
            enable_ml_scoring=True,
            kelly_fraction=0.35 if self.ai_mode == "aggressive" else 0.25,
            max_leverage=5.0 if self.ai_mode == "aggressive" else 3.0,
        )

        orchestrator_config = OrchestratorConfig(
            enable_ai_scoring=True,
            ai_min_confidence=self.ai_min_confidence,
            enable_flash_loans=self.enable_flash_loans,
            enable_cex_execution=self.enable_cex_execution,
            flash_loan_min_profit=self.flash_loan_min_profit,
            cex_arb_min_profit=self.cex_min_profit,
            portfolio_value_eth=self.current_capital_eth,
            dry_run=self.dry_run,
        )

        profit_config = ProfitMaximizerConfig(
            current_capital_eth=self.current_capital_eth,
            target_capital_eth=self.target_capital_eth,
            ruin_tolerance=0.30 if self.ai_mode == "aggressive" else 0.15,
        )

        integrated_config = AIIntegratedConfig(
            arbitrage_config=arbitrage_config,
            ai_config=ai_config,
            orchestrator_config=orchestrator_config,
            profit_config=profit_config,
            ai_mode=self.ai_mode,
            enable_ai_orchestration=True,
            enable_profit_maximization=self.enable_profit_maximization,
        )

        self.runner = AIIntegratedArbitrageRunner(
            router=self.order_router,
            dex=self.dex_eth,
            price_fetcher=self.price_fetcher.fetch_price,
            token_addresses=TOKEN_ADDRESSES,
            flash_executor=self.flash_executor,
            polygon_dex=self.dex_polygon,
            polygon_token_addresses=TOKEN_ADDRESSES,  # Same for now
            config=integrated_config,
        )

        log.info("ai_runner.initialized", mode=self.ai_mode, dry_run=self.dry_run)

    async def run(self) -> None:
        """Start the AI-integrated arbitrage system."""
        log.info("ai_integrated_system.starting")

        try:
            await self.runner.run(symbols=TRADING_SYMBOLS)
        except KeyboardInterrupt:
            log.info("ai_integrated_system.interrupted")
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Shutdown the system gracefully."""
        log.info("ai_integrated_system.shutting_down")
        await self.runner.stop()

        # Print final statistics
        stats = self.runner.get_stats()
        log.info("ai_integrated_system.final_stats", **stats)

    def get_stats(self) -> dict:
        """Get system statistics."""
        return self.runner.get_stats()


async def main():
    """Main entry point."""
    print("\n" + "=" * 80)
    print("🤖 AI-INTEGRATED ARBITRAGE SYSTEM")
    print("=" * 80)

    # Check execution mode
    dry_run = os.getenv("ENABLE_EXECUTION", "false").lower() != "true"

    if not dry_run:
        print("⚠️  WARNING: LIVE TRADING MODE ENABLED")
        print("=" * 80)
        print("This system will execute REAL trades with REAL money.")
        print("AI/ML will make autonomous trading decisions.")
        print("Press Ctrl+C within 10 seconds to cancel...")
        print("=" * 80 + "\n")
        await asyncio.sleep(10)

    # Display configuration
    ai_mode = os.getenv("AI_MODE", "conservative")
    current_capital = float(os.getenv("CURRENT_CAPITAL_ETH", "100.0"))
    target_capital = float(os.getenv("TARGET_CAPITAL_ETH", "1000.0"))

    print("\n📊 CONFIGURATION")
    print("=" * 80)
    print(f"Mode: {'DRY RUN (simulation only)' if dry_run else 'LIVE TRADING'}")
    print(f"AI Mode: {ai_mode.upper()}")
    print(f"Current Capital: {current_capital} ETH")
    print(f"Target Capital: {target_capital} ETH")
    print(f"Target Growth: {(target_capital / current_capital):.1f}x")
    print(f"Flash Loans: {os.getenv('ENABLE_FLASH_LOANS', 'true')}")
    print(f"CEX Execution: {os.getenv('ENABLE_CEX_EXECUTION', 'true')}")
    print(f"Profit Maximization: {os.getenv('ENABLE_PROFIT_MAXIMIZATION', 'true')}")
    print(f"Trading Pairs: {', '.join(TRADING_SYMBOLS)}")
    print("=" * 80 + "\n")

    print("🚀 Starting AI-integrated arbitrage system...")
    print("   - Monitoring on-chain and off-chain opportunities")
    print("   - AI scoring and decision-making active")
    print("   - Adaptive learning enabled")
    print("   - Press Ctrl+C to stop\n")

    # Initialize and run system
    system = AIIntegratedArbitrageSystem(dry_run=dry_run)
    await system.run()


if __name__ == "__main__":
    asyncio.run(main())
