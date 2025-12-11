#!/usr/bin/env python3
"""Unified AI Trading System - Master Orchestrator.

This is the single entry point that coordinates all system components:
- Multi-agent RL coordination
- Unified AI orchestrator
- Flash loan execution
- CEX/DEX arbitrage
- Dashboard and monitoring
- Real-time ML inference

Production-ready 2025 implementation.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path

import structlog
from dotenv import load_dotenv

# Load environment first
load_dotenv()

from src.ai.unified_orchestrator import (
    OrchestratorConfig,
    UnifiedAIOrchestrator,
    UnifiedOpportunity,
)
from src.brokers.connection_manager import get_connection_manager
from src.brokers.price_fetcher import CEXPriceFetcher
from src.brokers.routing import OrderRouter
from src.dex.config import Chain
from src.dex.flash_loan_executor import FlashLoanExecutor
from src.dex.uniswap_connector import UniswapConnector
from src.live.ai_integrated_runner import AIIntegratedArbitrageRunner, AIIntegratedConfig
from src.live.arbitrage_runner import ArbitrageConfig

log = structlog.get_logger()


@dataclass
class UnifiedSystemConfig:
    """Master configuration for the unified system."""

    # Environment mode
    dry_run: bool = True
    enable_flash_loans: bool = True
    enable_ai_orchestration: bool = True
    enable_rl_agents: bool = False  # Enable multi-agent RL (experimental)

    # Execution settings
    enable_execution: bool = False
    enable_polygon_execution: bool = False
    auto_start_dashboard: bool = True

    # AI/ML settings
    enable_ml_slippage: bool = True
    enable_predictive_arbitrage: bool = False  # Requires trained model
    ai_confidence_threshold: float = 0.60

    # Risk management
    max_daily_loss_eth: float = 0.5
    max_position_eth: float = 10.0
    enable_circuit_breakers: bool = True

    # Performance
    poll_interval: float = 2.0
    batch_opportunities: bool = True
    batch_size: int = 10


class UnifiedTradingSystem:
    """Master coordinator for the unified AI trading system."""

    def __init__(self, config: UnifiedSystemConfig | None = None):
        """Initialize the unified system.

        Args:
            config: System configuration (uses defaults if None)
        """
        self.config = config or UnifiedSystemConfig()
        self.log = structlog.get_logger()

        # Core components (initialized in setup)
        self.orchestrator: UnifiedAIOrchestrator | None = None
        self.runner: AIIntegratedArbitrageRunner | None = None
        self.price_fetcher: CEXPriceFetcher | None = None
        self.router: OrderRouter | None = None
        self.dex: UniswapConnector | None = None
        self.flash_executor: FlashLoanExecutor | None = None

        # Runtime state
        self.running = False
        self.tasks: list[asyncio.Task] = []

        # Opportunity tracking for dashboard
        self.opportunities: list[dict] = []
        self.executions: list[dict] = []

    async def setup(self) -> None:
        """Initialize all system components."""
        self.log.info("unified_system.initializing", config=self.config)

        # 1. Initialize price fetcher
        self.price_fetcher = CEXPriceFetcher(
            binance_enabled=False,  # Geo-blocked
            kraken_enabled=True,
            alpaca_enabled=True,
        )

        # 2. Initialize CEX router
        connection_manager = await get_connection_manager()
        self.router = OrderRouter(connection_manager)

        # 3. Initialize DEX connectors
        eth_rpc = os.getenv("ETH_RPC_URL") or os.getenv("ETHEREUM_RPC_URL")
        if not eth_rpc:
            raise ValueError("ETH_RPC_URL not set")

        self.dex = UniswapConnector(
            rpc_url=eth_rpc,
            chain=Chain.ETHEREUM,
            router_address=os.getenv("UNISWAP_V3_ROUTER"),
        )

        # 4. Initialize flash loan executor (if enabled)
        if self.config.enable_flash_loans:
            try:
                self.flash_executor = FlashLoanExecutor()
                self.log.info("unified_system.flash_executor_initialized")
            except Exception as e:
                self.log.warning("unified_system.flash_executor_init_failed", error=str(e))
                self.config.enable_flash_loans = False

        # 5. Initialize Polygon connector (if enabled)
        polygon_dex = None
        polygon_rpc = os.getenv("POLYGON_RPC_URL")
        if polygon_rpc:
            try:
                polygon_dex = UniswapConnector(
                    rpc_url=polygon_rpc,
                    chain=Chain.POLYGON,
                    router_address=os.getenv("UNISWAP_V3_ROUTER_POLYGON"),
                )
                self.log.info("unified_system.polygon_connector_initialized")
            except Exception as e:
                self.log.warning("unified_system.polygon_init_failed", error=str(e))

        # 6. Build token addresses mapping
        token_addresses = self._build_token_addresses()
        polygon_token_addresses = self._build_polygon_token_addresses() if polygon_dex else None

        # 7. Initialize AI-integrated runner
        arb_config = ArbitrageConfig(
            min_edge_bps=float(os.getenv("MIN_EDGE_BPS", "25")),
            max_notional=float(os.getenv("MAX_NOTIONAL", "1000")),
            enable_execution=self.config.enable_execution,
            enable_polygon_execution=self.config.enable_polygon_execution,
            poll_interval=self.config.poll_interval,
        )

        ai_config = AIIntegratedConfig(
            arbitrage_config=arb_config,
            enable_ai_orchestration=self.config.enable_ai_orchestration,
            ai_mode="balanced",
            batch_opportunities=self.config.batch_opportunities,
            batch_size=self.config.batch_size,
        )

        self.runner = AIIntegratedArbitrageRunner(
            router=self.router,
            dex=self.dex,
            price_fetcher=self.price_fetcher.get_price,
            token_addresses=token_addresses,
            flash_executor=self.flash_executor,
            polygon_dex=polygon_dex,
            polygon_token_addresses=polygon_token_addresses,
            config=ai_config,
        )

        # 8. Initialize unified orchestrator (the brain)
        if self.config.enable_ai_orchestration:
            orchestrator_config = OrchestratorConfig(
                min_profit_eth=float(os.getenv("MIN_FLASH_PROFIT_ETH", "0.15")),
                confidence_threshold=self.config.ai_confidence_threshold,
                max_gas_gwei=float(os.getenv("MAX_GAS_PRICE_GWEI", "120")),
                enable_circuit_breakers=self.config.enable_circuit_breakers,
                enable_safety_guard=True,
                max_daily_loss_eth=self.config.max_daily_loss_eth,
            )

            self.orchestrator = UnifiedAIOrchestrator(
                router=self.router,
                flash_executor=self.flash_executor,
                config=orchestrator_config,
            )

            self.log.info("unified_system.orchestrator_initialized")

        self.log.info("unified_system.setup_complete")

    def _build_token_addresses(self) -> dict[str, str]:
        """Build Ethereum token addresses mapping."""
        return {
            "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
            "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
            "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
            "LINK": "0x514910771AF9Ca656af840dff83E8264EcF986CA",
            "UNI": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",
            "AAVE": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9",
        }

    def _build_polygon_token_addresses(self) -> dict[str, str]:
        """Build Polygon token addresses mapping."""
        return {
            "WMATIC": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
            "USDC": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
            "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
            "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
            "DAI": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
        }

    async def run(self) -> None:
        """Run the unified system."""
        self.running = True
        self.log.info("unified_system.starting")

        try:
            # Create main scanning task
            scan_task = asyncio.create_task(self._scan_loop())
            self.tasks.append(scan_task)

            # Create stats monitoring task
            stats_task = asyncio.create_task(self._stats_loop())
            self.tasks.append(stats_task)

            # Wait for tasks
            await asyncio.gather(*self.tasks)

        except asyncio.CancelledError:
            self.log.info("unified_system.cancelled")
        except Exception as e:
            self.log.exception("unified_system.error", error=str(e))
        finally:
            await self.shutdown()

    async def _scan_loop(self) -> None:
        """Main scanning loop that feeds opportunities to the orchestrator."""
        symbols = self._get_trading_symbols()

        self.log.info("unified_system.scan_loop_started", symbols=symbols)

        while self.running:
            try:
                # Use the AI-integrated runner to scan
                # The runner will automatically feed opportunities to the orchestrator
                await self.runner.scan_once(symbols)

                # Sleep before next scan
                await asyncio.sleep(self.config.poll_interval)

            except Exception as e:
                self.log.exception("unified_system.scan_error", error=str(e))
                await asyncio.sleep(5)

    async def _stats_loop(self) -> None:
        """Monitor and log system statistics."""
        while self.running:
            try:
                stats = self.get_stats()
                self.log.info("unified_system.stats", **stats)
                await asyncio.sleep(30)  # Log every 30 seconds
            except Exception as e:
                self.log.exception("unified_system.stats_error", error=str(e))
                await asyncio.sleep(30)

    def _get_trading_symbols(self) -> list[str]:
        """Get list of symbols to trade."""
        # High-liquidity pairs from CLAUDE.md
        return [
            "ETH/USDC",
            "WETH/USDC",
            "ETH/USDT",
            "BTC/USDT",
            "WBTC/USDC",
            "USDT/USDC",
            "DAI/USDC",
            "LINK/USDC",
            "LINK/ETH",
            "UNI/USDC",
            "AAVE/USDC",
        ]

    def get_stats(self) -> dict:
        """Get current system statistics."""
        stats = {
            "running": self.running,
            "dry_run": self.config.dry_run,
            "ai_orchestration": self.config.enable_ai_orchestration,
            "flash_loans": self.config.enable_flash_loans,
            "opportunities_found": len(self.opportunities),
            "executions": len(self.executions),
        }

        if self.orchestrator:
            stats["orchestrator_stats"] = self.orchestrator.get_stats()

        if self.runner:
            stats["runner_stats"] = {
                "scans": getattr(self.runner, "scan_count", 0),
                "opportunities": getattr(self.runner, "opportunities_found", 0),
            }

        return stats

    async def shutdown(self) -> None:
        """Shutdown the system gracefully."""
        self.log.info("unified_system.shutting_down")
        self.running = False

        # Cancel all tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self.log.info("unified_system.shutdown_complete")


async def main() -> None:
    """Main entry point."""
    # Configure logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ]
    )

    log = structlog.get_logger()

    # Parse command line args
    dry_run = "--live" not in sys.argv
    enable_execution = "--execute" in sys.argv
    enable_ai = "--no-ai" not in sys.argv

    log.info(
        "unified_system.starting",
        dry_run=dry_run,
        enable_execution=enable_execution,
        enable_ai=enable_ai,
    )

    # Build config from environment and args
    config = UnifiedSystemConfig(
        dry_run=dry_run,
        enable_execution=enable_execution and not dry_run,
        enable_ai_orchestration=enable_ai,
        enable_flash_loans=os.getenv("ENABLE_FLASH_LOANS", "true").lower() == "true",
        enable_circuit_breakers=os.getenv("ENABLE_CIRCUIT_BREAKERS", "true").lower() == "true",
    )

    # Create and setup system
    system = UnifiedTradingSystem(config)

    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        log.info("unified_system.signal_received", signal=sig)
        asyncio.create_task(system.shutdown())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await system.setup()
        await system.run()
    except KeyboardInterrupt:
        log.info("unified_system.keyboard_interrupt")
    except Exception as e:
        log.exception("unified_system.fatal_error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
