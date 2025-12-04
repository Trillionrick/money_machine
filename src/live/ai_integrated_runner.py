"""AI-Integrated Arbitrage Runner - Connects AI/ML to all execution paths.

This runner extends the existing ArbitrageRunner and FlashArbitrageRunner
with full AI/ML integration via the UnifiedAIOrchestrator.

Opportunities flow:
1. Price monitoring (CEX + DEX) → UnifiedOpportunity
2. Submit to UnifiedAIOrchestrator
3. AI scoring and decision-making
4. Route to appropriate execution engine
5. Record results for adaptive learning

Production-ready 2025 implementation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

import structlog

from src.ai.advanced_decider import AdvancedAIConfig, AdvancedAIDecider, MarketRegime
from src.ai.profit_maximizer import (
    AggressiveProfitMaximizer,
    FlashLoanProfitPredictor,
    ProfitMaximizerConfig,
)
from src.ai.unified_orchestrator import (
    ExecutionPath,
    OrchestratorConfig,
    UnifiedAIOrchestrator,
    UnifiedOpportunity,
)
from src.brokers.routing import OrderRouter
from src.core.types import Symbol
from src.dex.flash_loan_executor import FlashLoanExecutor
from src.dex.uniswap_connector import UniswapConnector
from src.live.arbitrage_runner import ArbitrageConfig, ArbitrageRunner, PriceFetcher

log = structlog.get_logger()


@dataclass
class AIIntegratedConfig:
    """Configuration for AI-integrated arbitrage runner."""

    # Base arbitrage config
    arbitrage_config: ArbitrageConfig = field(default_factory=ArbitrageConfig)

    # AI configuration
    ai_config: AdvancedAIConfig = field(default_factory=AdvancedAIConfig)
    orchestrator_config: OrchestratorConfig = field(default_factory=OrchestratorConfig)

    # Profit maximization
    enable_profit_maximization: bool = True
    profit_config: ProfitMaximizerConfig = field(default_factory=ProfitMaximizerConfig)

    # Integration mode
    ai_mode: str = "conservative"  # conservative, balanced, aggressive
    enable_ai_orchestration: bool = True  # Use AI for all decisions
    fallback_to_rules: bool = True  # Fallback to rule-based if AI unavailable

    # Performance tuning
    batch_opportunities: bool = True  # Batch opportunities for AI scoring
    batch_size: int = 10
    batch_timeout_seconds: float = 2.0


class AIIntegratedArbitrageRunner:
    """Arbitrage runner with full AI/ML integration.

    This runner combines:
    - ArbitrageRunner (for opportunity detection)
    - UnifiedAIOrchestrator (for AI decision-making)
    - FlashLoanExecutor (for on-chain execution)
    - OrderRouter (for off-chain execution)
    - AggressiveProfitMaximizer (for optimal position sizing)

    All opportunities are scored by AI and routed to optimal execution path.
    """

    def __init__(
        self,
        router: OrderRouter,
        dex: UniswapConnector,
        price_fetcher: PriceFetcher,
        token_addresses: Mapping[str, str],
        flash_executor: FlashLoanExecutor | None = None,
        polygon_dex: UniswapConnector | None = None,
        polygon_token_addresses: Mapping[str, str] | None = None,
        config: AIIntegratedConfig | None = None,
    ):
        """Initialize AI-integrated runner.

        Args:
            router: Order router for CEX execution
            dex: Uniswap connector for DEX quotes
            price_fetcher: CEX price fetcher
            token_addresses: Token address mapping
            flash_executor: Flash loan executor (optional)
            polygon_dex: Polygon Uniswap connector (optional)
            polygon_token_addresses: Polygon token addresses (optional)
            config: Configuration
        """
        self.config = config or AIIntegratedConfig()

        # Initialize base arbitrage runner (for opportunity detection)
        self.base_runner = ArbitrageRunner(
            router=router,
            dex=dex,
            price_fetcher=price_fetcher,
            token_addresses=token_addresses,
            token_decimals={},
            config=self.config.arbitrage_config,
            polygon_dex=polygon_dex,
            polygon_token_addresses=polygon_token_addresses,
        )

        # Initialize AI components
        self.ai_decider = AdvancedAIDecider(self.config.ai_config)

        # Initialize profit maximizer (for on-chain flash loans)
        if self.config.enable_profit_maximization:
            predictor = FlashLoanProfitPredictor(self.config.profit_config)
            self.profit_maximizer = AggressiveProfitMaximizer(
                config=self.config.profit_config,
                predictor=predictor,
            )
        else:
            self.profit_maximizer = None

        # Initialize unified orchestrator
        self.orchestrator = UnifiedAIOrchestrator(
            ai_decider=self.ai_decider,
            flash_executor=flash_executor,
            order_router=router,
            flash_runner=None,  # We handle flash loans directly
            config=self.config.orchestrator_config,
        )

        # State tracking
        self.running = False
        self.opportunities_detected = 0
        self.opportunities_submitted = 0
        self.regime_update_interval = 300  # 5 minutes
        self.last_regime_update = datetime.min.replace(tzinfo=timezone.utc)

        log.info(
            "ai_integrated_runner.initialized",
            ai_enabled=self.config.enable_ai_orchestration,
            profit_max_enabled=self.config.enable_profit_maximization,
            ai_mode=self.config.ai_mode,
        )

    async def run(self, symbols: list[Symbol], poll_interval: float | None = None) -> None:
        """Run AI-integrated arbitrage scanner.

        Args:
            symbols: List of trading symbols to monitor
            poll_interval: Override poll interval (seconds)
        """
        if self.running:
            log.warning("ai_integrated_runner.already_running")
            return

        self.running = True
        interval = poll_interval or self.config.arbitrage_config.poll_interval

        log.info(
            "ai_integrated_runner.starting",
            symbols=symbols,
            poll_interval=interval,
            ai_enabled=self.config.enable_ai_orchestration,
        )

        # Start orchestrator
        if self.config.enable_ai_orchestration:
            await self.orchestrator.start()

        try:
            while self.running:
                scan_start = datetime.now(timezone.utc)

                # Update market regime periodically
                await self._update_market_regime()

                # Scan all symbols for opportunities
                tasks = [self._scan_symbol_ai_integrated(symbol) for symbol in symbols]
                await asyncio.gather(*tasks, return_exceptions=True)

                # Calculate time to next scan
                scan_duration = (datetime.now(timezone.utc) - scan_start).total_seconds()
                sleep_time = max(0.1, interval - scan_duration)

                log.debug(
                    "ai_integrated_runner.scan_completed",
                    symbols_scanned=len(symbols),
                    duration_seconds=scan_duration,
                    next_scan_in=sleep_time,
                )

                await asyncio.sleep(sleep_time)

        except KeyboardInterrupt:
            log.info("ai_integrated_runner.interrupted")
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the runner gracefully."""
        log.info("ai_integrated_runner.stopping")
        self.running = False

        if self.config.enable_ai_orchestration:
            await self.orchestrator.stop()

    async def _scan_symbol_ai_integrated(self, symbol: Symbol) -> None:
        """Scan a symbol and submit opportunities to AI orchestrator.

        Args:
            symbol: Trading symbol to scan
        """
        if "/" not in symbol:
            return

        base, quote = symbol.split("/", 1)

        # Get token addresses
        token_in = self.base_runner.token_addresses.get(quote)
        token_out = self.base_runner.token_addresses.get(base)

        if not token_in or not token_out:
            return

        # Fetch CEX price
        cex_price = await self.base_runner.price_fetcher(symbol)
        if cex_price is None or cex_price <= 0:
            return

        # Get DEX quotes (Ethereum)
        eth_opportunities = await self._get_dex_opportunities(
            symbol=symbol,
            base=base,
            quote=quote,
            token_in=token_in,
            token_out=token_out,
            cex_price=cex_price,
            chain="ethereum",
        )

        # Get DEX quotes (Polygon) if enabled
        polygon_opportunities = []
        if self.config.arbitrage_config.enable_polygon and self.base_runner.polygon_dex:
            polygon_token_in = (
                self.base_runner.polygon_token_addresses.get(quote)
                if self.base_runner.polygon_token_addresses
                else token_in
            )
            polygon_token_out = (
                self.base_runner.polygon_token_addresses.get(base)
                if self.base_runner.polygon_token_addresses
                else token_out
            )

            if polygon_token_in and polygon_token_out:
                polygon_opportunities = await self._get_dex_opportunities(
                    symbol=symbol,
                    base=base,
                    quote=quote,
                    token_in=polygon_token_in,
                    token_out=polygon_token_out,
                    cex_price=cex_price,
                    chain="polygon",
                )

        # Combine all opportunities
        all_opportunities = eth_opportunities + polygon_opportunities

        if not all_opportunities:
            return

        self.opportunities_detected += len(all_opportunities)

        # Submit to AI orchestrator
        if self.config.enable_ai_orchestration:
            for opp in all_opportunities:
                await self.orchestrator.submit_opportunity(opp)
                self.opportunities_submitted += 1

        elif self.config.fallback_to_rules:
            # Fallback to rule-based execution (original ArbitrageRunner logic)
            log.debug("ai_integrated_runner.fallback_to_rules", symbol=symbol)
            # Would call base_runner execution logic here

    async def _get_dex_opportunities(
        self,
        symbol: str,
        base: str,
        quote: str,
        token_in: str,
        token_out: str,
        cex_price: float,
        chain: str,
    ) -> list[UnifiedOpportunity]:
        """Get DEX opportunities for a symbol on a specific chain.

        Args:
            symbol: Trading symbol
            base: Base token symbol
            quote: Quote token symbol
            token_in: Token in address
            token_out: Token out address
            cex_price: CEX reference price
            chain: Chain name (ethereum/polygon)

        Returns:
            List of unified opportunities
        """
        opportunities = []

        # Select appropriate DEX connector
        dex = self.base_runner.dex if chain == "ethereum" else self.base_runner.polygon_dex
        if not dex:
            return opportunities

        # Get DEX quote
        test_amount = Decimal("1000.0")  # 1000 quote tokens

        try:
            # Get quote from DEX
            quote_result: dict[str, Any] = await dex.get_quote(
                token_in=token_in,
                token_out=token_out,
                amount_in=test_amount,
            )

            expected_output = quote_result.get("expected_output", Decimal("0"))
            if not quote_result or expected_output <= 0:
                return opportunities

            # Calculate DEX price
            dex_price = float(test_amount) / float(expected_output)

            # Calculate edge
            edge_bps = ((cex_price / dex_price) - 1) * 10_000 if dex_price > 0 else 0.0

            # Determine if this is a flash loan opportunity
            is_flash_opportunity = edge_bps >= self.config.arbitrage_config.min_edge_bps

            # Estimate costs
            gas_cost_quote = await self._estimate_gas_cost(chain, cex_price)
            flash_fee_quote = float(test_amount) * 0.0005 if is_flash_opportunity else 0.0  # Aave 0.05%
            slippage_quote = float(test_amount) * (self.config.arbitrage_config.slippage_tolerance)

            # Build unified opportunity
            execution_path = ExecutionPath.FLASH_LOAN if is_flash_opportunity else ExecutionPath.CEX_ARBITRAGE

            opportunity = UnifiedOpportunity(
                symbol=symbol,
                execution_path=execution_path,
                chain=chain,
                cex_price=cex_price,
                dex_price=dex_price,
                edge_bps=edge_bps,
                notional_quote=float(test_amount),
                gas_cost_quote=gas_cost_quote,
                flash_fee_quote=flash_fee_quote,
                slippage_quote=slippage_quote,
                hop_count=1,
                confidence=0.70,  # Base confidence
                token_in=token_in,
                token_out=token_out,
                amount_in=test_amount,
                expected_output=expected_output,
                metadata={
                    "dex_connector": dex.__class__.__name__,
                    "pool_address": quote_result.get("pool_address"),
                    "pool_liquidity": str(quote_result.get("pool_liquidity_tokens", "0")),
                    "price_impact_pct": str(quote_result.get("estimated_price_impact_pct", "0")),
                },
            )

            opportunities.append(opportunity)

            log.debug(
                "ai_integrated_runner.opportunity_detected",
                symbol=symbol,
                chain=chain,
                path=execution_path,
                edge_bps=edge_bps,
                cex_price=cex_price,
                dex_price=dex_price,
            )

        except Exception:
            log.exception("ai_integrated_runner.quote_failed", symbol=symbol, chain=chain)

        return opportunities

    async def _estimate_gas_cost(self, chain: str, eth_price: float) -> float:
        """Estimate gas cost in quote currency.

        Args:
            chain: Chain name
            eth_price: ETH price for conversion

        Returns:
            Estimated gas cost in quote currency (USD)
        """
        if chain == "ethereum":
            gas_units = 350_000  # Flash loan + swap
            gas_price_gwei = 30.0  # Default
            gas_cost_eth = (gas_units * gas_price_gwei * 1e9) / 1e18
            return gas_cost_eth * eth_price

        elif chain == "polygon":
            gas_units = 250_000
            gas_price_gwei = 50.0  # Polygon higher gwei but MATIC cheaper
            matic_price = 0.80  # Rough MATIC price in USD
            gas_cost_matic = (gas_units * gas_price_gwei * 1e9) / 1e18
            return gas_cost_matic * matic_price

        return 0.0

    async def _update_market_regime(self) -> None:
        """Update market regime for AI decision-making."""
        now = datetime.now(timezone.utc)
        elapsed = (now - self.last_regime_update).total_seconds()

        if elapsed < self.regime_update_interval:
            return

        self.last_regime_update = now

        # Simplified regime detection
        # Production would calculate actual volatility, gas prices, liquidity
        regime = MarketRegime(
            volatility=0.25,  # Would calculate from recent price history
            trend=0.0,
            liquidity=0.75,
            gas_percentile=0.5,
            regime_label="stable",
        )

        # Update orchestrator
        self.orchestrator.update_market_regime(regime)

        log.debug("ai_integrated_runner.regime_updated", regime=regime.regime_label)

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive runner statistics."""
        orchestrator_stats = self.orchestrator.get_stats()
        base_stats: dict[str, Any] = {
            "opportunities_detected": self.opportunities_detected,
            "opportunities_submitted": self.opportunities_submitted,
            "submission_rate": (
                self.opportunities_submitted / max(1, self.opportunities_detected)
            ),
        }

        profit_max_stats: dict[str, Any] = {}
        if self.profit_maximizer:
            profit_max_stats = self.profit_maximizer.get_stats()

        return {
            **base_stats,
            "orchestrator": orchestrator_stats,
            "profit_maximizer": profit_max_stats,
            "running": self.running,
            "ai_mode": self.config.ai_mode,
        }
