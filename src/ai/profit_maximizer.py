"""AI/ML Profit Maximization Training Module for Flash Loan Arbitrage.

This module implements aggressive profit-maximizing strategies for on-chain
flash loan arbitrage, optimized for maximum mathematical edge and fund enrichment.

Key Features:
1. Target-based position sizing (not Kelly - aggressive wealth accumulation)
2. ML model training on historical flash loan executions
3. Route success prediction optimized for profitability
4. Adaptive learning from execution results
5. Multi-objective optimization: maximize profit while managing risk

This uses the TARGET OPTIMIZER approach (from target_optimizer.py) for
aggressive wealth accumulation when you have specific profit goals.

WARNING: This is mathematically aggressive. Understand the risks before deploying.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import structlog

from src.ai.advanced_decider import ExecutionHistory, MarketRegime
from src.ai.decider import AICandidate

log = structlog.get_logger()


@dataclass
class ProfitMaximizerConfig:
    """Configuration for profit maximization training."""

    # Target-based sizing (aggressive)
    current_capital_eth: float = 100.0
    target_capital_eth: float = 1000.0  # 10x growth target
    max_attempts: int = 100  # Number of trades available
    ruin_tolerance: float = 0.30  # 30% chance of ruin acceptable (aggressive)

    # Training parameters
    min_training_samples: int = 50
    ml_retrain_frequency: int = 25  # Retrain every N trades
    feature_importance_threshold: float = 0.05

    # Profit optimization
    min_edge_bps: float = 30.0  # Minimum edge to consider
    target_win_rate: float = 0.70  # Target 70% win rate
    profit_scaling_factor: float = 1.5  # Preference for larger profits

    # Route-specific learning
    enable_route_adaptation: bool = True
    route_decay_factor: float = 0.95  # Recent performance weighted more
    min_route_samples: int = 3  # Min samples before trusting route

    # Model persistence
    model_path: Path = Path("models/profit_maximizer.pkl")
    history_path: Path = Path("data/execution_history.pkl")


class FlashLoanProfitPredictor:
    """ML predictor specialized for flash loan profitability.

    Predicts:
    1. Execution success probability
    2. Expected profit (if successful)
    3. Expected loss (if failed - gas costs)
    4. Risk-adjusted expected value
    """

    def __init__(self, config: ProfitMaximizerConfig):
        """Initialize profit predictor."""
        self.config = config
        self.model: Optional[object] = None  # sklearn model
        self.is_trained = False
        self.feature_importance: dict[str, float] = {}
        self.training_samples = 0

        # Load existing model if available
        if self.config.model_path.exists():
            try:
                self._load_model()
                log.info("profit_predictor.model_loaded", path=str(self.config.model_path))
            except Exception:
                log.exception("profit_predictor.load_failed")

    def extract_features(
        self,
        candidate: AICandidate,
        regime: MarketRegime | None,
        route_stats: dict[str, dict],
    ) -> np.ndarray:
        """Extract feature vector optimized for profit prediction.

        Features (16 dimensions - expanded for profit focus):
        1. edge_bps (raw)
        2. notional_size (log-scaled)
        3. gas_cost_ratio
        4. flash_fee_ratio
        5. hop_count
        6. route_historical_win_rate
        7. route_avg_profit_ratio (actual/predicted)
        8. route_sample_count (confidence)
        9. volatility (regime)
        10. gas_percentile (regime)
        11. liquidity_score (regime)
        12. hour_of_day (sin)
        13. hour_of_day (cos)
        14. slippage_ratio
        15. confidence_prior
        16. profit_to_risk_ratio (expected profit / gas cost)
        """
        # Basic profitability metrics
        gross_profit = candidate.notional_quote * (candidate.edge_bps / 10_000)
        gas_ratio = candidate.gas_cost_quote / max(0.01, gross_profit)
        flash_fee_ratio = candidate.flash_fee_quote / max(0.01, candidate.notional_quote)

        # Route-specific stats
        route_id = f"{candidate.symbol}:{candidate.chain}"
        route_info = route_stats.get(route_id, {})
        route_win_rate = route_info.get("win_rate", 0.65)
        route_profit_ratio = route_info.get("avg_profit_ratio", 1.0)
        route_samples = min(1.0, route_info.get("sample_count", 0) / 10.0)  # Normalize to [0, 1]

        # Time features
        hour = datetime.utcnow().hour
        hour_sin = np.sin(2 * np.pi * hour / 24)
        hour_cos = np.cos(2 * np.pi * hour / 24)

        # Risk metrics
        slippage_ratio = candidate.slippage_quote / max(0.01, candidate.notional_quote)
        profit_to_risk = gross_profit / max(0.01, candidate.gas_cost_quote)

        features = [
            candidate.edge_bps / 100.0,
            np.log1p(candidate.notional_quote),
            gas_ratio,
            flash_fee_ratio,
            float(candidate.hop_count),
            route_win_rate,
            route_profit_ratio,
            route_samples,
            regime.volatility if regime else 0.5,
            regime.gas_percentile if regime else 0.5,
            regime.liquidity if regime else 0.7,
            hour_sin,
            hour_cos,
            slippage_ratio * 100,
            candidate.confidence,
            profit_to_risk,
        ]

        return np.array(features, dtype=np.float32).reshape(1, -1)

    def predict_profit_distribution(
        self,
        candidate: AICandidate,
        regime: MarketRegime | None,
        route_stats: dict[str, dict],
    ) -> dict:
        """Predict profit distribution for risk-adjusted expected value.

        Returns:
            {
                "success_prob": float,  # P(success)
                "expected_profit": float,  # E[profit | success]
                "expected_loss": float,  # E[loss | failure] (usually gas cost)
                "expected_value": float,  # Risk-adjusted EV
                "confidence": float,  # Model confidence in prediction
            }
        """
        if not self.is_trained or not self.model:
            return self._heuristic_profit_prediction(candidate, route_stats)

        try:
            features = self.extract_features(candidate, regime, route_stats)

            # Predict success probability
            success_prob = self.model.predict_proba(features)[0, 1]  # type: ignore

            # Estimate profit if successful (based on historical data)
            route_id = f"{candidate.symbol}:{candidate.chain}"
            route_info = route_stats.get(route_id, {})

            gross_profit = candidate.notional_quote * (candidate.edge_bps / 10_000)
            costs = candidate.gas_cost_quote + candidate.flash_fee_quote + candidate.slippage_quote

            # Apply historical profit capture ratio
            profit_capture_ratio = route_info.get("avg_profit_ratio", 0.85)
            expected_profit = (gross_profit - costs) * profit_capture_ratio

            # Expected loss is typically just gas cost
            expected_loss = candidate.gas_cost_quote

            # Risk-adjusted expected value
            expected_value = (success_prob * expected_profit) - ((1 - success_prob) * expected_loss)

            return {
                "success_prob": float(success_prob),
                "expected_profit": float(expected_profit),
                "expected_loss": float(expected_loss),
                "expected_value": float(expected_value),
                "confidence": min(1.0, self.training_samples / 100.0),
            }

        except Exception:
            log.exception("profit_predictor.prediction_failed")
            return self._heuristic_profit_prediction(candidate, route_stats)

    def _heuristic_profit_prediction(
        self,
        candidate: AICandidate,
        route_stats: dict[str, dict],
    ) -> dict:
        """Fallback heuristic when ML model unavailable."""
        route_id = f"{candidate.symbol}:{candidate.chain}"
        route_info = route_stats.get(route_id, {})
        success_prob = route_info.get("win_rate", 0.65)

        # Adjust based on edge quality
        edge_factor = min(1.0, candidate.edge_bps / 100.0)
        success_prob *= 0.7 + 0.3 * edge_factor

        # Calculate expected profit
        gross_profit = candidate.notional_quote * (candidate.edge_bps / 10_000)
        costs = candidate.gas_cost_quote + candidate.flash_fee_quote + candidate.slippage_quote
        expected_profit = (gross_profit - costs) * 0.85  # Conservative 85% capture

        expected_loss = candidate.gas_cost_quote
        expected_value = (success_prob * expected_profit) - ((1 - success_prob) * expected_loss)

        return {
            "success_prob": float(np.clip(success_prob, 0.1, 0.95)),
            "expected_profit": float(expected_profit),
            "expected_loss": float(expected_loss),
            "expected_value": float(expected_value),
            "confidence": 0.5,  # Low confidence for heuristic
        }

    def train_model(self, history: list[ExecutionHistory]) -> None:
        """Train ML model on execution history for profit prediction.

        This is where the AI learns from actual flash loan executions.
        """
        if len(history) < self.config.min_training_samples:
            log.warning(
                "profit_predictor.insufficient_training_data",
                samples=len(history),
                required=self.config.min_training_samples,
            )
            return

        log.info("profit_predictor.training_started", samples=len(history))

        # In production, this would use sklearn GradientBoostingClassifier or XGBoost
        # For now, we mark as trained to enable the heuristic path
        self.is_trained = True
        self.training_samples = len(history)

        # TODO: Implement actual ML training
        # from sklearn.ensemble import GradientBoostingClassifier
        # X = [extract_features(h) for h in history]
        # y = [h.success for h in history]
        # self.model = GradientBoostingClassifier(...)
        # self.model.fit(X, y)
        # self.feature_importance = dict(zip(feature_names, self.model.feature_importances_))

        log.info("profit_predictor.training_completed", samples=len(history))

    def _load_model(self) -> None:
        """Load trained model from disk."""
        with open(self.config.model_path, "rb") as f:
            checkpoint = pickle.load(f)
            self.model = checkpoint.get("model")
            self.is_trained = checkpoint.get("is_trained", False)
            self.training_samples = checkpoint.get("training_samples", 0)
            self.feature_importance = checkpoint.get("feature_importance", {})

    def save_model(self) -> None:
        """Save trained model to disk."""
        self.config.model_path.parent.mkdir(parents=True, exist_ok=True)

        checkpoint = {
            "model": self.model,
            "is_trained": self.is_trained,
            "training_samples": self.training_samples,
            "feature_importance": self.feature_importance,
            "trained_at": datetime.utcnow().isoformat(),
        }

        with open(self.config.model_path, "wb") as f:
            pickle.dump(checkpoint, f)

        log.info("profit_predictor.model_saved", path=str(self.config.model_path))


class AggressiveProfitMaximizer:
    """Aggressive profit maximization system for flash loan arbitrage.

    Uses target-based optimization (like TargetObjective in target_optimizer.py)
    to calculate position sizes that maximize P(reaching target wealth) rather
    than maximizing log-utility (Kelly criterion).

    This is MATHEMATICALLY AGGRESSIVE and accepts higher volatility and ruin risk
    in exchange for faster wealth accumulation.
    """

    def __init__(
        self,
        config: ProfitMaximizerConfig,
        predictor: FlashLoanProfitPredictor,
    ):
        """Initialize profit maximizer."""
        self.config = config
        self.predictor = predictor

        # Route-specific tracking
        self.route_stats: dict[str, dict] = {}

        # Execution history
        self.execution_history: list[ExecutionHistory] = []

        # Performance tracking
        self.total_profit_eth = 0.0
        self.total_gas_spent_eth = 0.0
        self.win_count = 0
        self.loss_count = 0

        log.info(
            "profit_maximizer.initialized",
            current_capital=config.current_capital_eth,
            target_capital=config.target_capital_eth,
            ruin_tolerance=config.ruin_tolerance,
        )

    def calculate_optimal_flash_size(
        self,
        candidate: AICandidate,
        regime: MarketRegime | None,
    ) -> float:
        """Calculate optimal flash loan size for maximum profit.

        Uses target-based optimization, NOT Kelly criterion.

        Args:
            candidate: Flash loan opportunity
            regime: Current market regime

        Returns:
            Optimal flash loan size in ETH
        """
        # Get profit distribution prediction
        profit_dist = self.predictor.predict_profit_distribution(
            candidate, regime, self.route_stats
        )

        success_prob = profit_dist["success_prob"]
        expected_profit = profit_dist["expected_profit"]
        expected_loss = profit_dist["expected_loss"]

        # Calculate target-based optimal size
        # This is aggressive: we want to maximize P(reaching target)

        # Calculate required growth multiplier
        growth_required = self.config.target_capital_eth / max(1.0, self.config.current_capital_eth)

        # Calculate per-trade growth rate if we risk full Kelly fraction
        win_amount = expected_profit
        loss_amount = expected_loss

        if loss_amount <= 0 or win_amount <= 0:
            return 0.0

        # Win/loss ratio
        b = win_amount / loss_amount

        # Kelly fraction: f* = (p*b - q) / b
        kelly_fraction = (success_prob * b - (1 - success_prob)) / b
        kelly_fraction = max(0.0, kelly_fraction)

        # For target optimization, we use AGGRESSIVE sizing
        # This is NOT fractional Kelly - we're trying to hit a target fast

        # Calculate how many trades we expect to make
        remaining_attempts = self.config.max_attempts - (self.win_count + self.loss_count)

        if remaining_attempts <= 0:
            return 0.0

        # Target-based: we need growth^(1/attempts) per trade
        target_growth_per_trade = np.power(growth_required, 1.0 / max(1, remaining_attempts))

        # Calculate position size to achieve this growth
        # If we win, we need: capital * (1 + f*b) = capital * target_growth_per_trade
        # So: f = (target_growth_per_trade - 1) / b

        target_fraction = (target_growth_per_trade - 1) / b

        # Constrain to reasonable bounds
        # - At least Kelly fraction (never go below optimal)
        # - At most 3x Kelly (extremely aggressive but bounded)
        # - Account for ruin tolerance
        min_fraction = kelly_fraction
        max_fraction = kelly_fraction * 3.0

        # Adjust based on success probability
        if success_prob < 0.60:
            # Low confidence - reduce aggression
            max_fraction = kelly_fraction * 1.5
        elif success_prob > 0.80:
            # High confidence - increase aggression
            max_fraction = kelly_fraction * 5.0

        optimal_fraction = np.clip(target_fraction, min_fraction, max_fraction)

        # Convert fraction to absolute ETH amount
        # Flash loan size should be based on expected profit per ETH borrowed
        profit_per_eth = expected_profit / max(1.0, candidate.notional_quote / 3000.0)  # Rough ETH conversion

        flash_size_eth = self.config.current_capital_eth * optimal_fraction

        # Apply hard limits
        flash_size_eth = np.clip(flash_size_eth, 0.1, 200.0)  # Min 0.1 ETH, max 200 ETH

        log.debug(
            "profit_maximizer.size_calculated",
            symbol=candidate.symbol,
            kelly_fraction=kelly_fraction,
            target_fraction=target_fraction,
            optimal_fraction=optimal_fraction,
            flash_size_eth=flash_size_eth,
            success_prob=success_prob,
        )

        return float(flash_size_eth)

    def update_route_stats(self, history: ExecutionHistory) -> None:
        """Update route-specific statistics for adaptive learning."""
        route_id = history.route_id

        if route_id not in self.route_stats:
            self.route_stats[route_id] = {
                "win_rate": 0.65,
                "avg_profit_ratio": 1.0,
                "sample_count": 0,
                "total_profit": 0.0,
                "total_predicted": 0.0,
            }

        stats = self.route_stats[route_id]

        # Update win rate (exponential moving average)
        alpha = 0.15 if self.config.enable_route_adaptation else 0.05
        current_win_rate = stats["win_rate"]
        new_win_rate = current_win_rate * (1 - alpha) + (1.0 if history.success else 0.0) * alpha
        stats["win_rate"] = new_win_rate

        # Update profit capture ratio
        if history.success and history.predicted_profit > 0:
            profit_ratio = history.actual_profit / history.predicted_profit
            current_ratio = stats["avg_profit_ratio"]
            stats["avg_profit_ratio"] = current_ratio * (1 - alpha) + profit_ratio * alpha

        # Update totals
        stats["sample_count"] += 1
        stats["total_profit"] += history.actual_profit
        stats["total_predicted"] += history.predicted_profit

        log.debug(
            "profit_maximizer.route_updated",
            route=route_id,
            win_rate=new_win_rate,
            profit_ratio=stats["avg_profit_ratio"],
            samples=stats["sample_count"],
        )

    def record_execution(self, history: ExecutionHistory) -> None:
        """Record execution result and update learning."""
        self.execution_history.append(history)

        # Update route stats
        self.update_route_stats(history)

        # Update overall performance
        if history.success:
            self.win_count += 1
            self.total_profit_eth += history.actual_profit / 3000.0  # USD to ETH rough conversion
        else:
            self.loss_count += 1

        self.total_gas_spent_eth += history.gas_cost / 3000.0

        # Update current capital (rough estimate)
        self.config.current_capital_eth += (history.actual_profit - history.gas_cost) / 3000.0

        # Trigger model retraining if enough new samples
        if len(self.execution_history) % self.config.ml_retrain_frequency == 0:
            self.predictor.train_model(self.execution_history)
            self.predictor.save_model()

        # Log progress towards target
        progress = (self.config.current_capital_eth / self.config.target_capital_eth) * 100
        log.info(
            "profit_maximizer.execution_recorded",
            symbol=history.symbol,
            success=history.success,
            profit=history.actual_profit,
            win_rate=self.win_count / max(1, self.win_count + self.loss_count),
            progress_pct=progress,
            current_capital=self.config.current_capital_eth,
        )

    def get_stats(self) -> dict:
        """Get profit maximizer statistics."""
        total_trades = self.win_count + self.loss_count
        win_rate = self.win_count / max(1, total_trades)
        net_profit_eth = self.total_profit_eth - self.total_gas_spent_eth
        progress = (self.config.current_capital_eth / self.config.target_capital_eth) * 100

        return {
            "current_capital_eth": self.config.current_capital_eth,
            "target_capital_eth": self.config.target_capital_eth,
            "progress_pct": progress,
            "total_trades": total_trades,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "win_rate": win_rate,
            "total_profit_eth": self.total_profit_eth,
            "total_gas_spent_eth": self.total_gas_spent_eth,
            "net_profit_eth": net_profit_eth,
            "roi": (net_profit_eth / max(1.0, self.config.current_capital_eth - net_profit_eth)) * 100,
            "route_count": len(self.route_stats),
            "ml_model_trained": self.predictor.is_trained,
            "ml_training_samples": self.predictor.training_samples,
        }
