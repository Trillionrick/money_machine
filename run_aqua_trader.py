"""Run the AI-powered Aqua opportunity detector.

This script monitors Aqua Protocol events across Ethereum and Polygon,
identifies profitable opportunities, and executes trades automatically.

SAFETY: Starts in DRY RUN mode by default!
Set ENABLE_AQUA_EXECUTION=true in .env to enable real trading.
"""

import asyncio
import os
from datetime import datetime

import structlog
from dotenv import load_dotenv
from web3 import AsyncHTTPProvider, AsyncWeb3
from pydantic import SecretStr

from src.ai.aqua_opportunity_detector import AquaOpportunityConfig, AquaOpportunityDetector
from src.ai.decider import AIConfig, AIDecider
from src.brokers.binance_adapter import BinanceAdapter
from src.brokers.price_fetcher import CEXPriceFetcher
from src.dex.aqua_client import AquaClient, AQUA_CONTRACT_ADDRESSES
from src.dex.config import Chain, UniswapConfig
from src.dex.flash_loan_executor import FlashLoanExecutor
from src.dex.uniswap_connector import UniswapConnector

# Load environment
load_dotenv()

log = structlog.get_logger()


class AquaTraderSystem:
    """Complete AI-powered Aqua trading system."""

    def __init__(self, dry_run: bool = True):
        """Initialize Aqua trader.

        Args:
            dry_run: If True, only log opportunities without executing trades
        """
        self.dry_run = dry_run

        # Initialize Web3 connections
        eth_rpc = os.getenv("ETH_RPC_URL") or os.getenv("ETHEREUM_RPC_URL")
        polygon_rpc = os.getenv("POLYGON_RPC_URL")

        if not eth_rpc:
            raise ValueError("ETH_RPC_URL not set in .env")

        self.w3_eth = AsyncWeb3(AsyncHTTPProvider(eth_rpc.strip()))
        self.w3_polygon = AsyncWeb3(AsyncHTTPProvider(polygon_rpc.strip())) if polygon_rpc else None

        # Initialize components
        self.ai_config = AIConfig(
            min_profit_eth=float(os.getenv("AI_MIN_PROFIT_ETH", "0.05")),
            confidence_threshold=float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.7")),
            max_gas_gwei=float(os.getenv("AI_MAX_GAS_GWEI", "120")),
        )
        self.ai_decider = AIDecider(config=self.ai_config)

        # Price fetcher (CEXPriceFetcher handles Binance internally)
        self.price_fetcher = CEXPriceFetcher(
            binance_enabled=True,
            kraken_enabled=True,
            alpaca_enabled=False,
            coingecko_enabled=True,
        )

        # Uniswap connector
        graph_key = os.getenv("THEGRAPH_API_KEY")
        if not graph_key:
            raise ValueError("THEGRAPH_API_KEY not set in .env (required for Uniswap subgraph)")

        uniswap_config = UniswapConfig(
            THEGRAPH_API_KEY=SecretStr(graph_key),
            ETHEREUM_RPC_URL=SecretStr(eth_rpc),
        )
        self.uniswap = UniswapConnector(config=uniswap_config, chain=Chain.ETHEREUM)

        # Flash loan executor (optional)
        self.flash_executor = None
        if os.getenv("ENABLE_FLASH_LOANS", "false").lower() == "true":
            try:
                self.flash_executor = FlashLoanExecutor()
                log.info("flash_executor_initialized")
            except Exception as e:
                log.warning("flash_executor_init_failed", error=str(e))

        # Aqua opportunity detector config
        self.aqua_config = AquaOpportunityConfig(
            min_pushed_amount_usd=float(os.getenv("AQUA_MIN_PUSH_USD", "10000")),
            min_profit_usd=float(os.getenv("AQUA_MIN_PROFIT_USD", "100")),
            min_confidence=float(os.getenv("AQUA_MIN_CONFIDENCE", "0.7")),
            enable_copy_trading=os.getenv("AQUA_ENABLE_COPY_TRADING", "false").lower() == "true",
            enable_counter_trading=os.getenv("AQUA_ENABLE_COUNTER_TRADING", "true").lower() == "true",
            max_position_size_usd=float(os.getenv("AQUA_MAX_POSITION_USD", "5000")),
        )

        # Create detector
        if not self.w3_polygon:
            raise ValueError("POLYGON_RPC_URL required for Aqua monitoring")

        self.detector = AquaOpportunityDetector(
            w3_ethereum=self.w3_eth,
            w3_polygon=self.w3_polygon,
            config=self.aqua_config,
            ai_decider=self.ai_decider,
            uniswap_connector=self.uniswap,
            price_fetcher=self.price_fetcher,
            flash_executor=self.flash_executor,
        )

        # Aqua clients
        self.aqua_eth = AquaClient(self.w3_eth, chain_id=1)
        self.aqua_polygon = AquaClient(self.w3_polygon, chain_id=137)

        self.running = False

    async def watch_events(self, aqua_client: AquaClient, chain_name: str) -> None:
        """Watch Aqua events on a specific chain."""
        log.info("aqua.watcher_started", chain=chain_name)

        # Get event filter
        contract_address = aqua_client.address
        event_signatures = aqua_client.get_event_signatures()

        # Get the current block number
        eth = aqua_client.w3.eth
        last_block = int(await eth.block_number)  # type: ignore[misc]

        while self.running:
            try:
                # Get current block number
                current_block = int(await eth.block_number)  # type: ignore[misc]

                if current_block > last_block:
                    # Get logs for new blocks
                    logs = await eth.get_logs({  # type: ignore[misc]
                        "fromBlock": last_block + 1,
                        "toBlock": current_block,
                        "address": contract_address,
                        "topics": [event_signatures],
                    })

                    for log_entry in logs:
                        event = aqua_client.parse_event(dict(log_entry))
                        if event:
                            log.info(
                                "aqua.event_detected",
                                chain=chain_name,
                                event_type=event.name,
                                maker=event.maker[:10] + "...",
                                token=event.token[:10] + "..." if event.token else None,
                                amount=event.amount,
                            )

                            # Process with detector
                            await self.detector.process_event(event)

                    last_block = current_block

                # Poll every 3 seconds
                await asyncio.sleep(3)

            except Exception as e:
                log.exception("aqua.watcher_error", chain=chain_name, error=str(e))
                await asyncio.sleep(5)

    async def run(self) -> None:
        """Start the Aqua trader system."""
        log.info(
            "aqua_trader.starting",
            dry_run=self.dry_run,
            copy_trading=self.aqua_config.enable_copy_trading,
            counter_trading=self.aqua_config.enable_counter_trading,
        )

        self.running = True

        # Start watchers for both chains
        tasks = [
            asyncio.create_task(self.watch_events(self.aqua_eth, "Ethereum")),
            asyncio.create_task(self.watch_events(self.aqua_polygon, "Polygon")),
            asyncio.create_task(self.print_stats()),
        ]

        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            log.info("aqua_trader.stopping")
            self.running = False
            for task in tasks:
                task.cancel()

    async def print_stats(self) -> None:
        """Print statistics every 60 seconds."""
        while self.running:
            await asyncio.sleep(60)

            stats = self.detector.get_stats()
            log.info("aqua_trader.stats", **stats)


async def main():
    """Main entry point."""
    # Check if execution is enabled
    dry_run = os.getenv("ENABLE_AQUA_EXECUTION", "false").lower() != "true"

    if not dry_run:
        print("\n" + "=" * 70)
        print("⚠️  WARNING: LIVE TRADING MODE ENABLED")
        print("=" * 70)
        print("The Aqua trader will execute real trades based on detected opportunities.")
        print("Press Ctrl+C within 10 seconds to cancel...")
        print("=" * 70 + "\n")

        await asyncio.sleep(10)

    print("\n" + "=" * 70)
    print("🌊 AI-POWERED AQUA OPPORTUNITY DETECTOR")
    print("=" * 70)
    print(f"Mode: {'DRY RUN (simulation only)' if dry_run else 'LIVE TRADING'}")
    print(f"Chains: Ethereum + Polygon")
    print(f"Min deposit to track: ${float(os.getenv('AQUA_MIN_PUSH_USD', '10000')):,.0f}")
    print(f"Min profit target: ${float(os.getenv('AQUA_MIN_PROFIT_USD', '100')):,.0f}")
    print(f"Copy trading: {os.getenv('AQUA_ENABLE_COPY_TRADING', 'false')}")
    print(f"Counter trading: {os.getenv('AQUA_ENABLE_COUNTER_TRADING', 'true')}")
    print("=" * 70 + "\n")

    system = AquaTraderSystem(dry_run=dry_run)
    await system.run()


if __name__ == "__main__":
    asyncio.run(main())
