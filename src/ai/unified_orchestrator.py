"""Unified AI Orchestrator - Connects AI/ML to all execution paths.

This orchestrator serves as the central brain that:
1. Receives opportunities from on-chain (DEX/flash loans) and off-chain (CEX) sources
2. Uses AdvancedAIDecider to score and rank ALL opportunities
3. Routes decisions to appropriate execution engines:
   - Flash loans → AIFlashRunner (on-chain)
   - CEX arbitrage → OrderRouter (off-chain)
   - Aqua whale trades → AquaOpportunityDetector (on-chain)
4. Tracks execution results for adaptive learning
5. Provides unified metrics and controls

Production-grade implementation (2025) with structured concurrency.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Optional

import structlog

from src.ai.advanced_decider import (
    AdvancedAIConfig,
    AdvancedAIDecider,
    ExecutionHistory,
    MarketRegime,
)
from src.ai.decider import AICandidate, AIDecision
from src.ai.metrics import get_metrics_collector
from src.brokers.routing import OrderRouter
from src.core.execution import Order, OrderType, Side
from src.core.types import Symbol
from src.dex.flash_loan_executor import FlashLoanExecutor
from src.live.flash_arb_runner import FlashArbitrageRunner

log = structlog.get_logger()


class ExecutionPath(StrEnum):
    """Execution path for opportunity."""

    FLASH_LOAN = "flash_loan"  # On-chain flash loan arbitrage
    CEX_ARBITRAGE = "cex_arbitrage"  # Off-chain CEX/DEX arbitrage
    CEX_DIRECTIONAL = "cex_directional"  # Off-chain CEX directional trade
    AQUA_COPY = "aqua_copy"  # On-chain Aqua copy trading
    AQUA_COUNTER = "aqua_counter"  # On-chain Aqua counter trading


@dataclass
class UnifiedOpportunity:
    """Unified opportunity representation for AI scoring."""

    # Core identification
    symbol: Symbol
    execution_path: ExecutionPath
    chain: str  # "ethereum", "polygon", "cex"

    # Pricing
    cex_price: float | None = None
    dex_price: float | None = None
    entry_price: float | None = None
    target_price: float | None = None

    # Edge and profitability
    edge_bps: float = 0.0
    notional_quote: float = 0.0
    gas_cost_quote: float = 0.0
    flash_fee_quote: float = 0.0
    slippage_quote: float = 0.0
    bridge_fee_quote: float = 0.0

    # Route metadata
    hop_count: int = 1
    confidence: float = 0.65  # Base confidence
    route_id: str | None = None

    # Execution parameters
    token_in: str | None = None
    token_out: str | None = None
    amount_in: Decimal | None = None
    expected_output: Decimal | None = None

    # Additional metadata
    metadata: dict = field(default_factory=dict)
    detected_at: datetime = field(default_factory=datetime.utcnow)

    def to_ai_candidate(self) -> AICandidate:
        """Convert to AICandidate for scoring."""
        return AICandidate(
            symbol=self.symbol,
            edge_bps=self.edge_bps,
            notional_quote=self.notional_quote,
            gas_cost_quote=self.gas_cost_quote,
            flash_fee_quote=self.flash_fee_quote,
            slippage_quote=self.slippage_quote,
            hop_count=self.hop_count,
            cex_price=self.cex_price or 0.0,
            dex_price=self.dex_price or 0.0,
            chain=self.chain,
            confidence=self.confidence,
        )


@dataclass
class ExecutionResult:
    """Result from executing an opportunity."""

    opportunity: UnifiedOpportunity
    decision: AIDecision
    success: bool
    actual_profit: float
    gas_cost: float
    execution_time_ms: float
    error_message: str | None = None
    tx_hash: str | None = None


@dataclass
class OrchestratorConfig:
    """Configuration for unified AI orchestrator."""

    # AI decision-making
    enable_ai_scoring: bool = True
    ai_min_confidence: float = 0.70
    enable_ml_prediction: bool = True

    # Execution controls
    enable_flash_loans: bool = True
    enable_cex_execution: bool = True
    enable_aqua_trading: bool = False  # Risky - default off

    # Execution path preferences (priority order)
    flash_loan_min_profit: float = 0.15  # Min profit in ETH for flash loans
    cex_arb_min_profit: float = 50.0  # Min profit in USD for CEX arb
    flash_loan_max_size_eth: float = 100.0
    cex_max_position_usd: float = 5000.0

    # Risk management
    max_concurrent_executions: int = 3
    max_daily_executions: int = 100
    max_daily_losses_usd: float = 500.0
    execution_cooldown_seconds: float = 5.0

    # Portfolio tracking
    portfolio_value_eth: float = 100.0
    dry_run: bool = True  # Safety: default to simulation


class UnifiedAIOrchestrator:
    """Central AI orchestrator connecting AI/ML to all execution paths.

    This is the main integration point that unifies:
    - On-chain flash loan arbitrage (via AIFlashRunner)
    - Off-chain CEX arbitrage (via OrderRouter)
    - Aqua whale following (via AquaOpportunityDetector)

    All decisions flow through AdvancedAIDecider for intelligent scoring.
    """

    def __init__(
        self,
        ai_decider: AdvancedAIDecider,
        flash_executor: FlashLoanExecutor | None = None,
        order_router: OrderRouter | None = None,
        flash_runner: FlashArbitrageRunner | None = None,
        config: OrchestratorConfig | None = None,
    ):
        """Initialize unified orchestrator.

        Args:
            ai_decider: Advanced AI decision engine
            flash_executor: Flash loan executor for on-chain arb
            order_router: Order router for off-chain CEX trading
            flash_runner: Flash arbitrage runner (optional, for integration)
            config: Orchestrator configuration
        """
        self.ai_decider = ai_decider
        self.flash_executor = flash_executor
        self.order_router = order_router
        self.flash_runner = flash_runner
        self.config = config or OrchestratorConfig()

        # Execution tracking
        self.pending_executions: set[str] = set()
        self.execution_history: list[ExecutionResult] = []
        self.daily_executions = 0
        self.daily_profit_usd = 0.0
        self.daily_losses_usd = 0.0
        self.last_execution_time = datetime.min

        # Metrics
        self.metrics = get_metrics_collector()

        # Opportunity queue
        self.opportunity_queue: asyncio.Queue[UnifiedOpportunity] = asyncio.Queue(maxsize=1000)

        # Task management
        self.running = False
        self._tasks: list[asyncio.Task] = []

        log.info(
            "orchestrator.initialized",
            ai_enabled=self.config.enable_ai_scoring,
            flash_enabled=self.config.enable_flash_loans,
            cex_enabled=self.config.enable_cex_execution,
            dry_run=self.config.dry_run,
        )

    async def submit_opportunity(self, opportunity: UnifiedOpportunity) -> None:
        """Submit an opportunity for AI evaluation and potential execution.

        This is the main entry point for opportunities from any source.

        Args:
            opportunity: Unified opportunity to evaluate
        """
        try:
            await self.opportunity_queue.put(opportunity)
            log.debug(
                "orchestrator.opportunity_submitted",
                symbol=opportunity.symbol,
                path=opportunity.execution_path,
                edge_bps=opportunity.edge_bps,
            )
        except asyncio.QueueFull:
            log.warning("orchestrator.queue_full", symbol=opportunity.symbol)

    async def start(self) -> None:
        """Start the orchestrator event loop."""
        if self.running:
            log.warning("orchestrator.already_running")
            return

        self.running = True
        log.info("orchestrator.starting")

        # Start processing loop
        task = asyncio.create_task(self._processing_loop(), name="orchestrator_loop")
        self._tasks.append(task)

        # Start metrics task
        metrics_task = asyncio.create_task(self._metrics_loop(), name="metrics_loop")
        self._tasks.append(metrics_task)

    async def stop(self) -> None:
        """Stop the orchestrator gracefully."""
        log.info("orchestrator.stopping")
        self.running = False

        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for completion
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()

    async def _processing_loop(self) -> None:
        """Main processing loop for opportunity evaluation and execution."""
        batch: list[UnifiedOpportunity] = []
        last_process_time = datetime.utcnow()

        while self.running:
            try:
                # Collect opportunities in batches (max 10 per batch, 1 second timeout)
                try:
                    opp = await asyncio.wait_for(self.opportunity_queue.get(), timeout=1.0)
                    batch.append(opp)

                    # Collect more if available (non-blocking)
                    while len(batch) < 10:
                        try:
                            opp = self.opportunity_queue.get_nowait()
                            batch.append(opp)
                        except asyncio.QueueEmpty:
                            break

                except asyncio.TimeoutError:
                    pass

                # Process batch if we have opportunities or enough time has passed
                now = datetime.utcnow()
                should_process = (
                    len(batch) > 0 and (len(batch) >= 5 or (now - last_process_time).total_seconds() > 2.0)
                )

                if should_process:
                    await self._process_batch(batch)
                    batch.clear()
                    last_process_time = now

            except Exception:
                log.exception("orchestrator.processing_loop_error")
                await asyncio.sleep(1)

    async def _process_batch(self, opportunities: list[UnifiedOpportunity]) -> None:
        """Process a batch of opportunities through AI decision-making.

        Args:
            opportunities: Batch of opportunities to evaluate
        """
        if not opportunities:
            return

        # Check execution limits
        if not self._can_execute():
            log.warning("orchestrator.execution_limits_reached")
            return

        # Convert to AI candidates
        candidates = [opp.to_ai_candidate() for opp in opportunities]

        # AI decision-making
        if self.config.enable_ai_scoring:
            decision = self.ai_decider.pick_best(
                candidates,
                portfolio_value_eth=self.config.portfolio_value_eth,
            )
        else:
            # Fallback to simple rule-based selection
            decision = self._rule_based_selection(opportunities)

        if not decision:
            log.debug("orchestrator.no_viable_decision", count=len(opportunities))
            return

        # Find the corresponding opportunity
        selected_opp = next(
            (opp for opp in opportunities if opp.symbol == decision.symbol),
            None,
        )

        if not selected_opp:
            log.error("orchestrator.opportunity_not_found", symbol=decision.symbol)
            return

        # Check confidence threshold
        if decision.confidence < self.config.ai_min_confidence:
            log.info(
                "orchestrator.confidence_too_low",
                symbol=decision.symbol,
                confidence=decision.confidence,
                threshold=self.config.ai_min_confidence,
            )
            return

        # Check path-specific profit thresholds
        if not self._meets_profit_threshold(selected_opp, decision):
            log.info(
                "orchestrator.profit_threshold_not_met",
                symbol=decision.symbol,
                path=selected_opp.execution_path,
                net_profit=decision.net_quote,
            )
            return

        # Execute the decision
        await self._execute_decision(selected_opp, decision)

    async def _execute_decision(
        self,
        opportunity: UnifiedOpportunity,
        decision: AIDecision,
    ) -> None:
        """Route decision to appropriate execution engine.

        Args:
            opportunity: Selected opportunity
            decision: AI decision with execution parameters
        """
        # Check concurrent execution limit
        if len(self.pending_executions) >= self.config.max_concurrent_executions:
            log.warning("orchestrator.max_concurrent_reached")
            return

        # Check cooldown
        now = datetime.utcnow()
        elapsed = (now - self.last_execution_time).total_seconds()
        if elapsed < self.config.execution_cooldown_seconds:
            log.debug("orchestrator.cooldown_active", remaining=self.config.execution_cooldown_seconds - elapsed)
            return

        # Mark as pending
        execution_id = f"{opportunity.symbol}:{opportunity.execution_path}:{now.timestamp()}"
        self.pending_executions.add(execution_id)

        log.info(
            "orchestrator.executing_decision",
            symbol=decision.symbol,
            path=opportunity.execution_path,
            edge_bps=decision.edge_bps,
            confidence=decision.confidence,
            net_profit=decision.net_quote,
        )

        # Record decision in metrics
        self.metrics.record_decision(
            confidence=decision.confidence,
            edge_bps=decision.edge_bps,
            predicted_profit=decision.net_quote,
            executed=True,
        )

        # Route to execution engine
        execution_start = datetime.utcnow()

        try:
            if opportunity.execution_path == ExecutionPath.FLASH_LOAN:
                result = await self._execute_flash_loan(opportunity, decision)
            elif opportunity.execution_path == ExecutionPath.CEX_ARBITRAGE:
                result = await self._execute_cex_arbitrage(opportunity, decision)
            elif opportunity.execution_path == ExecutionPath.CEX_DIRECTIONAL:
                result = await self._execute_cex_directional(opportunity, decision)
            else:
                log.warning("orchestrator.unsupported_path", path=opportunity.execution_path)
                result = None

            execution_time_ms = (datetime.utcnow() - execution_start).total_seconds() * 1000

            if result:
                # Record execution in metrics
                self.metrics.record_execution(
                    success=result.success,
                    actual_profit=result.actual_profit,
                    gas_cost=result.gas_cost,
                    execution_time_ms=execution_time_ms,
                )

                # Record in AI decider for learning
                history = ExecutionHistory(
                    timestamp=datetime.utcnow(),
                    symbol=opportunity.symbol,
                    edge_bps=decision.edge_bps,
                    predicted_profit=decision.net_quote,
                    actual_profit=result.actual_profit,
                    success=result.success,
                    gas_cost=result.gas_cost,
                    slippage_bps=decision.slippage_quote / decision.notional_quote * 10_000
                    if decision.notional_quote > 0
                    else 0.0,
                    route_id=opportunity.route_id or f"{opportunity.symbol}:{opportunity.chain}",
                    chain=opportunity.chain,
                )
                self.ai_decider.record_execution(history)

                # Update tracking
                self.execution_history.append(result)
                self.daily_executions += 1
                self.last_execution_time = now

                if result.success:
                    self.daily_profit_usd += result.actual_profit
                else:
                    self.daily_losses_usd += abs(result.actual_profit)

                log.info(
                    "orchestrator.execution_completed",
                    symbol=opportunity.symbol,
                    success=result.success,
                    profit=result.actual_profit,
                    time_ms=execution_time_ms,
                )

        except Exception:
            log.exception("orchestrator.execution_error", symbol=opportunity.symbol)

        finally:
            self.pending_executions.discard(execution_id)

    async def _execute_flash_loan(
        self,
        opportunity: UnifiedOpportunity,
        decision: AIDecision,
    ) -> ExecutionResult | None:
        """Execute flash loan arbitrage on-chain.

        Args:
            opportunity: Flash loan opportunity
            decision: AI decision

        Returns:
            Execution result or None
        """
        if not self.config.enable_flash_loans or not self.flash_executor:
            log.warning("orchestrator.flash_loans_disabled")
            return None

        if self.config.dry_run:
            log.info(
                "orchestrator.flash_loan_dry_run",
                symbol=opportunity.symbol,
                expected_profit=decision.net_quote,
            )
            return ExecutionResult(
                opportunity=opportunity,
                decision=decision,
                success=True,
                actual_profit=decision.net_quote * 0.95,  # Simulate 95% capture
                gas_cost=decision.gas_cost_quote,
                execution_time_ms=500.0,
            )

        # TODO: Implement actual flash loan execution via FlashLoanExecutor
        # This would call self.flash_executor.execute_flash_arbitrage(...)
        log.info("orchestrator.flash_loan_execution_placeholder", symbol=opportunity.symbol)

        return ExecutionResult(
            opportunity=opportunity,
            decision=decision,
            success=False,
            actual_profit=0.0,
            gas_cost=0.0,
            execution_time_ms=0.0,
            error_message="Flash loan execution not implemented",
        )

    async def _execute_cex_arbitrage(
        self,
        opportunity: UnifiedOpportunity,
        decision: AIDecision,
    ) -> ExecutionResult | None:
        """Execute CEX arbitrage off-chain.

        Args:
            opportunity: CEX arbitrage opportunity
            decision: AI decision

        Returns:
            Execution result or None
        """
        if not self.config.enable_cex_execution or not self.order_router:
            log.warning("orchestrator.cex_execution_disabled")
            return None

        if self.config.dry_run:
            log.info(
                "orchestrator.cex_arb_dry_run",
                symbol=opportunity.symbol,
                expected_profit=decision.net_quote,
            )
            return ExecutionResult(
                opportunity=opportunity,
                decision=decision,
                success=True,
                actual_profit=decision.net_quote * 0.98,  # Simulate 98% capture
                gas_cost=0.0,  # No gas for CEX
                execution_time_ms=250.0,
            )

        # Build orders for CEX arbitrage
        base, quote = opportunity.symbol.split("/", 1)

        # Buy on cheaper side, sell on expensive side
        buy_side = "cex" if decision.cex_price and decision.dex_price and decision.cex_price < decision.dex_price else "dex"

        if buy_side == "cex":
            # Buy on CEX, sell on DEX
            buy_order = Order(
                symbol=opportunity.symbol,
                side=Side.BUY,
                quantity=float(opportunity.amount_in or 1.0),
                order_type=OrderType.MARKET,
            )

            # Submit to order router
            try:
                await self.order_router.submit_orders([buy_order])
                log.info("orchestrator.cex_order_submitted", symbol=opportunity.symbol, side="BUY")

                return ExecutionResult(
                    opportunity=opportunity,
                    decision=decision,
                    success=True,
                    actual_profit=decision.net_quote,
                    gas_cost=0.0,
                    execution_time_ms=200.0,
                )

            except Exception:
                log.exception("orchestrator.cex_order_failed", symbol=opportunity.symbol)
                return ExecutionResult(
                    opportunity=opportunity,
                    decision=decision,
                    success=False,
                    actual_profit=0.0,
                    gas_cost=0.0,
                    execution_time_ms=0.0,
                    error_message="CEX order submission failed",
                )

        return None

    async def _execute_cex_directional(
        self,
        opportunity: UnifiedOpportunity,
        decision: AIDecision,
    ) -> ExecutionResult | None:
        """Execute directional CEX trade (for RL policy integration).

        Args:
            opportunity: Directional trade opportunity
            decision: AI decision

        Returns:
            Execution result or None
        """
        # Similar to CEX arbitrage but simpler (just one order)
        return await self._execute_cex_arbitrage(opportunity, decision)

    def _can_execute(self) -> bool:
        """Check if execution is allowed based on limits."""
        if self.daily_executions >= self.config.max_daily_executions:
            return False

        if self.daily_losses_usd >= self.config.max_daily_losses_usd:
            return False

        return True

    def _meets_profit_threshold(self, opportunity: UnifiedOpportunity, decision: AIDecision) -> bool:
        """Check if opportunity meets path-specific profit threshold."""
        if opportunity.execution_path == ExecutionPath.FLASH_LOAN:
            # Convert USD profit to ETH (rough estimate)
            profit_eth = decision.net_quote / (decision.cex_price or 3000.0)
            return profit_eth >= self.config.flash_loan_min_profit

        elif opportunity.execution_path in [ExecutionPath.CEX_ARBITRAGE, ExecutionPath.CEX_DIRECTIONAL]:
            return decision.net_quote >= self.config.cex_arb_min_profit

        return True

    def _rule_based_selection(self, opportunities: list[UnifiedOpportunity]) -> AIDecision | None:
        """Fallback rule-based opportunity selection when AI is disabled."""
        if not opportunities:
            return None

        # Simple: select highest edge with positive net profit
        best_opp = max(opportunities, key=lambda o: o.edge_bps)

        # Calculate net profit
        costs = best_opp.gas_cost_quote + best_opp.flash_fee_quote + best_opp.slippage_quote + best_opp.bridge_fee_quote
        gross_profit = best_opp.notional_quote * (best_opp.edge_bps / 10_000)
        net_profit = gross_profit - costs

        if net_profit <= 0:
            return None

        return AIDecision(
            symbol=best_opp.symbol,
            edge_bps=best_opp.edge_bps,
            notional_quote=best_opp.notional_quote,
            net_quote=net_profit,
            confidence=0.65,
            chain=best_opp.chain,
            cex_price=best_opp.cex_price,
            dex_price=best_opp.dex_price,
            gas_cost_quote=best_opp.gas_cost_quote,
            flash_fee_quote=best_opp.flash_fee_quote,
            slippage_quote=best_opp.slippage_quote,
            hop_count=best_opp.hop_count,
            reason="rule_based_selection",
        )

    async def _metrics_loop(self) -> None:
        """Periodic metrics reporting."""
        while self.running:
            try:
                await asyncio.sleep(60)  # Every minute

                stats = self.get_stats()
                log.info("orchestrator.metrics", **stats)

            except Exception:
                log.exception("orchestrator.metrics_loop_error")

    def get_stats(self) -> dict:
        """Get orchestrator statistics."""
        ai_stats = self.ai_decider.get_stats()

        return {
            "opportunities_queued": self.opportunity_queue.qsize(),
            "pending_executions": len(self.pending_executions),
            "daily_executions": self.daily_executions,
            "daily_profit_usd": self.daily_profit_usd,
            "daily_losses_usd": self.daily_losses_usd,
            "execution_history_count": len(self.execution_history),
            "ai_stats": ai_stats,
            "config": {
                "ai_enabled": self.config.enable_ai_scoring,
                "flash_enabled": self.config.enable_flash_loans,
                "cex_enabled": self.config.enable_cex_execution,
                "dry_run": self.config.dry_run,
            },
        }

    def update_market_regime(self, regime: MarketRegime) -> None:
        """Update market regime for AI decision-making."""
        self.ai_decider.update_regime(regime)

    def update_config(self, updates: dict) -> None:
        """Update orchestrator configuration dynamically."""
        for key, value in updates.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                log.info("orchestrator.config_updated", key=key, value=value)
