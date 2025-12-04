"""AI-enhanced flash arbitrage runner with intelligent opportunity selection.

Extends FlashArbitrageRunner with:
- Advanced AI decision-making (multi-factor scoring)
- ML-based route success prediction
- Adaptive learning from execution results
- Risk-adjusted position sizing
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import cast

import structlog
from web3 import Web3

from src.ai.advanced_decider import (
    AdvancedAIConfig,
    AdvancedAIDecider,
    ExecutionHistory,
    MarketRegime,
)
from src.ai.decider import AICandidate, AIDecision
from src.core.types import Symbol
from src.live.flash_arb_runner import FlashArbConfig, FlashArbitrageRunner

log = structlog.get_logger()


@dataclass
class AIFlashArbConfig(FlashArbConfig):
    """Extended config with AI decision-making parameters."""

    # AI-specific settings
    enable_ai_scoring: bool = True  # Use AI for opportunity scoring
    ai_min_confidence: float = 0.70  # Minimum AI confidence for execution
    ai_confidence_boost_threshold: float = 0.85  # Increase size for high-confidence ops

    # Position sizing
    ai_position_sizing: bool = True  # Use AI-calculated Kelly sizing
    portfolio_value_eth: float = 100.0  # Current portfolio value for sizing

    # Learning and adaptation
    enable_ai_learning: bool = True  # Record results for model improvement
    record_execution_results: bool = True  # Track all executions

    # Market regime awareness
    enable_regime_detection: bool = True  # Use market regime in decisions
    high_vol_threshold: float = 0.40  # Annual vol threshold for high-vol regime
    low_liquidity_threshold: float = 0.30  # Liquidity threshold


class AIFlashArbitrageRunner(FlashArbitrageRunner):
    """Flash arbitrage runner with advanced AI decision-making.

    Integrates AdvancedAIDecider for:
    - Multi-factor opportunity scoring
    - ML-based execution success prediction
    - Risk-adjusted position sizing
    - Adaptive learning from results
    """

    def __init__(self, *args, ai_config: AdvancedAIConfig | None = None, **kwargs):
        """Initialize AI-enhanced flash arbitrage runner."""
        super().__init__(*args, **kwargs)

        # Initialize AI components
        self.ai_config = ai_config or AdvancedAIConfig()
        self.ai_decider = AdvancedAIDecider(self.ai_config)

        # Market regime tracking
        self.current_regime: MarketRegime | None = None
        self.last_regime_update = datetime.now(timezone.utc)

        # Performance tracking
        self.ai_decisions_made = 0
        self.ai_decisions_executed = 0
        self.ai_execution_results: list[ExecutionHistory] = []

        log.info(
            "ai_flash_arb.initialized",
            ai_enabled=self.ai_flash_config.enable_ai_scoring,
            ml_enabled=self.ai_config.enable_ml_scoring,
        )

    @property
    def ai_flash_config(self) -> AIFlashArbConfig:
        """Get config as AIFlashArbConfig with proper typing."""
        if isinstance(self.config, AIFlashArbConfig):
            return self.config
        # Fallback to base FlashArbConfig
        return cast(AIFlashArbConfig, self.config)

    async def _scan_symbol(self, symbol: Symbol) -> None:
        """AI-enhanced symbol scanning with intelligent opportunity selection.

        Flow:
        1. Collect price data (CEX + DEX)
        2. Build AI candidate opportunities
        3. Score with AdvancedAIDecider (multi-factor + ML)
        4. Execute best opportunity if confidence threshold met
        5. Record results for adaptive learning
        """
        if "/" not in symbol:
            self.trades_skipped += 1
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
            return

        # Update market regime periodically
        if self.ai_flash_config.enable_regime_detection:
            await self._update_market_regime()

        # Get CEX price
        cex_price = await self.price_fetcher(symbol)
        if cex_price is None or cex_price <= 0:
            self.trades_skipped += 1
            return

        # Collect DEX quotes from multiple sources
        test_amount = Decimal("1.0")
        candidates = await self._collect_quotes(
            symbol=symbol,
            base_symbol=base,
            quote_symbol=quote,
            token_in=token_in,
            token_out=token_out,
            polygon_token_in=polygon_token_in,
            polygon_token_out=polygon_token_out,
            amount_in=test_amount,
            cex_price=cex_price,
            cross_chain=True,
        )

        if not candidates:
            self.trades_skipped += 1
            return

        # Build AI candidates for scoring
        ai_candidates = await self._build_ai_candidates(
            candidates=candidates, symbol=symbol, cex_price=cex_price
        )

        if not ai_candidates:
            self.trades_skipped += 1
            return

        # AI decision-making
        if self.ai_flash_config.enable_ai_scoring:
            decision = await self._ai_decide_and_execute(ai_candidates, symbol)
            if decision:
                return  # Successfully executed via AI path

        # Fallback to rule-based logic if AI disabled or no decision
        await super()._scan_symbol(symbol)

    async def _build_ai_candidates(
        self,
        candidates: list,
        symbol: str,
        cex_price: float,
    ) -> list[AICandidate]:
        """Convert route candidates to AI candidate format with cost estimation."""
        ai_candidates = []

        for cand in candidates:
            # Estimate costs
            gas_cost_eth = await self._estimate_gas_cost_eth(cand.chain)
            gas_cost_quote = gas_cost_eth * cex_price  # Convert to quote currency

            # Estimate flash loan fee (Aave V3: 0.05%)
            notional_quote = float(cand.amount_out) * cex_price
            flash_fee_quote = notional_quote * 0.0005

            # Estimate slippage
            slippage_bps = self.flash_config.slippage_buffer_bps
            slippage_quote = notional_quote * (slippage_bps / 10_000)

            # Calculate edge
            dex_price = cand.price
            edge_bps = cand.net_edge_bps

            # Build AI candidate
            ai_cand = AICandidate(
                symbol=symbol,
                edge_bps=edge_bps,
                notional_quote=notional_quote,
                gas_cost_quote=gas_cost_quote,
                flash_fee_quote=flash_fee_quote,
                slippage_quote=slippage_quote,
                hop_count=getattr(cand, "hop_count", 1),
                cex_price=cex_price,
                dex_price=dex_price,
                chain=cand.chain,
                confidence=0.65,  # base confidence from route health
            )

            ai_candidates.append(ai_cand)

        return ai_candidates

    async def _ai_decide_and_execute(
        self,
        candidates: list[AICandidate],
        symbol: str,
    ) -> AIDecision | None:
        """Use AI to select and execute best opportunity.

        Returns:
            AIDecision if executed, None otherwise
        """
        # AI scoring with multi-factor analysis
        portfolio_value = self.ai_flash_config.portfolio_value_eth
        decision = self.ai_decider.pick_best(candidates, portfolio_value)

        if not decision:
            log.debug("ai.no_viable_decision", symbol=symbol)
            self.trades_skipped += 1
            return None

        self.ai_decisions_made += 1

        # Check AI confidence threshold
        if decision.confidence < self.ai_flash_config.ai_min_confidence:
            log.info(
                "ai.confidence_too_low",
                symbol=symbol,
                confidence=decision.confidence,
                threshold=self.ai_flash_config.ai_min_confidence,
            )
            self.trades_skipped += 1
            return None

        log.info(
            "ai.decision_approved",
            symbol=decision.symbol,
            edge_bps=decision.edge_bps,
            net_quote=decision.net_quote,
            confidence=decision.confidence,
        )

        # Emit opportunity event
        await self._emit_opportunity(
            {
                "symbol": decision.symbol,
                "edge_bps": decision.edge_bps,
                "cex_price": decision.cex_price,
                "dex_price": decision.dex_price,
                "execution_path": "ai_flash_loan",
                "confidence": decision.confidence,
                "net_profit_quote": decision.net_quote,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Execute with AI-approved parameters
        success = await self._execute_ai_flash_opportunity(decision)

        if success:
            self.ai_decisions_executed += 1

        return decision if success else None

    async def _execute_ai_flash_opportunity(self, decision: AIDecision) -> bool:
        """Execute AI-approved flash loan opportunity with result tracking."""
        if not self.flash_executor:
            return False

        base_symbol, quote_symbol = decision.symbol.split("/", 1)
        token_out = self.token_addresses.get(base_symbol)
        token_in = self.token_addresses.get(quote_symbol)

        if not token_in or not token_out:
            return False

        # Calculate borrow amount
        # If AI position sizing enabled, use AI-calculated size
        if self.ai_flash_config.ai_position_sizing:
            # AI decider tracks optimal Kelly size in trace
            borrow_amount_eth = min(
                self.flash_config.max_flash_borrow_eth,
                max(
                    self.flash_config.min_flash_borrow_eth,
                    decision.net_quote / (decision.dex_price or 1.0) if decision.dex_price else 10.0,
                ),
            )
        else:
            # Use rule-based sizing
            edge_ratio = decision.edge_bps / self.flash_config.target_roi_bps
            size_multiplier = max(
                self.flash_config.min_size_multiplier,
                min(self.flash_config.max_size_multiplier, edge_ratio),
            )
            borrow_amount_eth = self.flash_config.max_flash_borrow_eth * size_multiplier

        # High confidence boost
        if decision.confidence >= self.ai_flash_config.ai_confidence_boost_threshold:
            borrow_amount_eth *= 1.2  # 20% size increase for high-confidence trades
            log.info(
                "ai.high_confidence_boost",
                symbol=decision.symbol,
                confidence=decision.confidence,
                boosted_size=borrow_amount_eth,
            )

        # Execute through parent class flash arb method
        execution_start = datetime.now(timezone.utc)

        try:
            await self._execute_flash_arb(
                symbol=decision.symbol,
                token_in=token_in,
                token_out=token_out,
                cex_price=decision.cex_price or 0.0,
                dex_price=decision.dex_price or 0.0,
                edge_bps=decision.edge_bps,
            )

            # Record successful execution for learning
            if self.ai_flash_config.enable_ai_learning:
                await self._record_ai_execution(
                    decision=decision,
                    actual_profit=decision.net_quote,  # Simplified - would get from tx
                    success=True,
                    gas_cost=decision.gas_cost_quote,
                )

            return True

        except Exception as e:
            log.exception(
                "ai.execution_failed",
                symbol=decision.symbol,
                error=str(e),
            )

            # Record failed execution for learning
            if self.ai_flash_config.enable_ai_learning:
                await self._record_ai_execution(
                    decision=decision,
                    actual_profit=-decision.gas_cost_quote,  # Lost gas cost
                    success=False,
                    gas_cost=decision.gas_cost_quote,
                )

            return False

    async def _record_ai_execution(
        self,
        decision: AIDecision,
        actual_profit: float,
        success: bool,
        gas_cost: float,
    ) -> None:
        """Record execution result for AI learning."""
        history = ExecutionHistory(
            timestamp=datetime.now(timezone.utc),
            symbol=decision.symbol,
            edge_bps=decision.edge_bps,
            predicted_profit=decision.net_quote,
            actual_profit=actual_profit,
            success=success,
            gas_cost=gas_cost,
            slippage_bps=decision.slippage_quote / decision.notional_quote * 10_000
            if decision.notional_quote > 0
            else 0.0,
            route_id=f"{decision.symbol}:{decision.chain}",
            chain=decision.chain,
        )

        self.ai_execution_results.append(history)
        self.ai_decider.record_execution(history)

        log.info(
            "ai.execution_recorded",
            symbol=decision.symbol,
            success=success,
            actual_profit=actual_profit,
            predicted_profit=decision.net_quote,
        )

    async def _update_market_regime(self) -> None:
        """Update market regime indicators for AI decision-making."""
        # Update regime every 5 minutes
        now = datetime.now(timezone.utc)
        if (now - self.last_regime_update).total_seconds() < 300:
            return

        self.last_regime_update = now

        # Simplified regime detection - production would use actual volatility calculation
        # For now, use heuristics based on gas prices and time of day

        try:
            # Get current gas price (would query gas oracle)
            # Placeholder: assume mid-range
            gas_percentile = 0.5

            # Estimate volatility (would calculate from recent price history)
            volatility = 0.25  # Default moderate volatility

            # Estimate liquidity (would query DEX liquidity depth)
            liquidity = 0.7  # Default good liquidity

            # Determine regime label
            regime_label = "stable"
            if volatility > self.ai_flash_config.high_vol_threshold:
                regime_label = "high_vol"
            elif liquidity < self.ai_flash_config.low_liquidity_threshold:
                regime_label = "low_liquidity"
            elif gas_percentile > 0.8:
                regime_label = "high_gas"

            self.current_regime = MarketRegime(
                volatility=volatility,
                trend=0.0,  # Neutral trend
                liquidity=liquidity,
                gas_percentile=gas_percentile,
                regime_label=regime_label,
            )

            self.ai_decider.update_regime(self.current_regime)

            log.debug(
                "ai.regime_updated",
                regime=regime_label,
                volatility=volatility,
                gas_percentile=gas_percentile,
            )

        except Exception:
            log.exception("ai.regime_update_failed")

    async def _estimate_gas_cost_eth(self, chain: str) -> float:
        """Estimate gas cost in ETH for a flash loan transaction."""
        # Simplified estimation - production would query gas oracle
        base_gas_units = 300_000  # Flash loan + swap execution
        gas_price_gwei = 30.0  # Default gas price

        # Chain-specific adjustments
        if chain == "polygon":
            gas_price_gwei = 50.0  # Polygon typically lower gas
            base_gas_units = 250_000

        gas_cost_wei = int(base_gas_units * gas_price_gwei * 1e9)
        gas_cost_result = Web3.from_wei(gas_cost_wei, "ether")
        return float(gas_cost_result)

    def get_ai_stats(self) -> dict[str, object]:
        """Get AI-specific performance statistics."""
        base_stats = self.get_stats()
        ai_decider_stats = self.ai_decider.get_stats()

        return {
            **base_stats,
            "ai_decisions_made": self.ai_decisions_made,
            "ai_decisions_executed": self.ai_decisions_executed,
            "ai_execution_rate": (
                self.ai_decisions_executed / self.ai_decisions_made
                if self.ai_decisions_made > 0
                else 0.0
            ),
            "ai_decider_stats": ai_decider_stats,
            "current_regime": self.current_regime.regime_label if self.current_regime else None,
            "ml_model_trained": self.ai_decider.route_predictor.is_trained,
        }
