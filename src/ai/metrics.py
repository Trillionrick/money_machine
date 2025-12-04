"""Comprehensive AI metrics and monitoring system.

Tracks performance across all AI components:
- Advanced AI Decider decisions and outcomes
- RL Policy learning progress
- Aqua Detector opportunities
- Flash Runner AI execution results
- Model performance metrics
- System health indicators
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

import structlog

log = structlog.get_logger()


@dataclass
class DecisionMetrics:
    """Metrics for AI decision-making."""

    total_decisions: int = 0
    decisions_executed: int = 0
    avg_confidence: float = 0.0
    avg_edge_bps: float = 0.0
    total_predicted_profit: float = 0.0
    total_actual_profit: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0


@dataclass
class ExecutionMetrics:
    """Metrics for trade execution."""

    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    total_profit_usd: float = 0.0
    total_gas_cost_usd: float = 0.0
    avg_execution_time_ms: float = 0.0
    success_rate: float = 0.0


@dataclass
class ModelMetrics:
    """Metrics for ML models."""

    model_name: str
    is_trained: bool = False
    training_samples: int = 0
    last_training_time: Optional[datetime] = None
    prediction_accuracy: float = 0.0
    avg_prediction_confidence: float = 0.0


@dataclass
class OpportunityMetrics:
    """Metrics for opportunity detection."""

    opportunities_detected: int = 0
    opportunities_executed: int = 0
    avg_opportunity_quality: float = 0.0
    total_estimated_profit: float = 0.0
    conversion_rate: float = 0.0


class AIMetricsCollector:
    """Centralized metrics collector for all AI components.

    Aggregates metrics from:
    - AdvancedAIDecider
    - RLArbitragePolicy
    - AquaOpportunityDetector
    - AIFlashArbitrageRunner

    Provides:
    - Real-time metrics API
    - Historical trend tracking
    - Alert thresholds
    - Dashboard integration
    """

    def __init__(self, history_size: int = 1000):
        """Initialize metrics collector.

        Args:
            history_size: Number of historical records to keep
        """
        self.history_size = history_size

        # Component metrics
        self.decider_metrics = DecisionMetrics()
        self.execution_metrics = ExecutionMetrics()
        self.opportunity_metrics = OpportunityMetrics()

        # Model tracking
        self.model_metrics: dict[str, ModelMetrics] = {}

        # Historical data (time-series)
        self.profit_history: deque[tuple[datetime, float]] = deque(maxlen=history_size)
        self.decision_history: deque[tuple[datetime, dict]] = deque(maxlen=history_size)
        self.execution_history: deque[tuple[datetime, dict]] = deque(maxlen=history_size)

        # Performance tracking
        self.start_time = datetime.utcnow()
        self.last_update = datetime.utcnow()

        # Alert thresholds
        self.alert_thresholds = {
            "min_win_rate": 0.45,  # Alert if win rate drops below 45%
            "max_gas_cost_pct": 0.30,  # Alert if gas cost exceeds 30% of profit
            "min_success_rate": 0.70,  # Alert if execution success rate < 70%
            "max_drawdown_pct": 0.20,  # Alert if drawdown exceeds 20%
        }

        log.info("ai_metrics.initialized", history_size=history_size)

    def record_decision(
        self,
        confidence: float,
        edge_bps: float,
        predicted_profit: float,
        executed: bool,
    ) -> None:
        """Record an AI decision."""
        self.decider_metrics.total_decisions += 1
        if executed:
            self.decider_metrics.decisions_executed += 1

        # Update rolling averages
        n = self.decider_metrics.total_decisions
        self.decider_metrics.avg_confidence = (
            self.decider_metrics.avg_confidence * (n - 1) + confidence
        ) / n
        self.decider_metrics.avg_edge_bps = (
            self.decider_metrics.avg_edge_bps * (n - 1) + edge_bps
        ) / n
        self.decider_metrics.total_predicted_profit += predicted_profit

        # Record to history
        self.decision_history.append(
            (
                datetime.utcnow(),
                {
                    "confidence": confidence,
                    "edge_bps": edge_bps,
                    "predicted_profit": predicted_profit,
                    "executed": executed,
                },
            )
        )

        self.last_update = datetime.utcnow()

    def record_execution(
        self,
        success: bool,
        actual_profit: float,
        gas_cost: float,
        execution_time_ms: float,
    ) -> None:
        """Record an execution result."""
        self.execution_metrics.total_executions += 1

        if success:
            self.execution_metrics.successful_executions += 1
            self.decider_metrics.total_actual_profit += actual_profit
        else:
            self.execution_metrics.failed_executions += 1

        self.execution_metrics.total_profit_usd += actual_profit
        self.execution_metrics.total_gas_cost_usd += gas_cost

        # Update rolling average execution time
        n = self.execution_metrics.total_executions
        self.execution_metrics.avg_execution_time_ms = (
            self.execution_metrics.avg_execution_time_ms * (n - 1) + execution_time_ms
        ) / n

        # Calculate success rate
        self.execution_metrics.success_rate = (
            self.execution_metrics.successful_executions / self.execution_metrics.total_executions
            if self.execution_metrics.total_executions > 0
            else 0.0
        )

        # Record to history
        self.profit_history.append((datetime.utcnow(), actual_profit))
        self.execution_history.append(
            (
                datetime.utcnow(),
                {
                    "success": success,
                    "profit": actual_profit,
                    "gas_cost": gas_cost,
                    "execution_time_ms": execution_time_ms,
                },
            )
        )

        # Update win rate
        successes = sum(1 for _, data in self.execution_history if data["success"])
        self.decider_metrics.win_rate = (
            successes / len(self.execution_history) if self.execution_history else 0.0
        )

        # Calculate Sharpe ratio (simplified)
        if len(self.profit_history) > 10:
            profits = [p for _, p in self.profit_history]
            avg_profit = sum(profits) / len(profits)
            std_profit = (sum((p - avg_profit) ** 2 for p in profits) / len(profits)) ** 0.5
            self.decider_metrics.sharpe_ratio = avg_profit / std_profit if std_profit > 0 else 0.0

        self.last_update = datetime.utcnow()
        self._check_alerts()

    def record_opportunity(
        self,
        detected: bool = True,
        executed: bool = False,
        quality_score: float = 0.0,
        estimated_profit: float = 0.0,
    ) -> None:
        """Record an opportunity detection."""
        if detected:
            self.opportunity_metrics.opportunities_detected += 1
            self.opportunity_metrics.total_estimated_profit += estimated_profit

        if executed:
            self.opportunity_metrics.opportunities_executed += 1

        # Update quality score average
        if detected:
            n = self.opportunity_metrics.opportunities_detected
            self.opportunity_metrics.avg_opportunity_quality = (
                self.opportunity_metrics.avg_opportunity_quality * (n - 1) + quality_score
            ) / n

        # Calculate conversion rate
        self.opportunity_metrics.conversion_rate = (
            self.opportunity_metrics.opportunities_executed
            / self.opportunity_metrics.opportunities_detected
            if self.opportunity_metrics.opportunities_detected > 0
            else 0.0
        )

        self.last_update = datetime.utcnow()

    def register_model(
        self,
        model_name: str,
        is_trained: bool = False,
        training_samples: int = 0,
    ) -> None:
        """Register a model for tracking."""
        self.model_metrics[model_name] = ModelMetrics(
            model_name=model_name,
            is_trained=is_trained,
            training_samples=training_samples,
            last_training_time=datetime.utcnow() if is_trained else None,
        )

        log.info(
            "ai_metrics.model_registered",
            model=model_name,
            trained=is_trained,
            samples=training_samples,
        )

    def update_model_metrics(
        self,
        model_name: str,
        accuracy: float,
        confidence: float,
    ) -> None:
        """Update model performance metrics."""
        if model_name in self.model_metrics:
            self.model_metrics[model_name].prediction_accuracy = accuracy
            self.model_metrics[model_name].avg_prediction_confidence = confidence
            self.last_update = datetime.utcnow()

    def get_summary(self) -> dict[str, Any]:
        """Get comprehensive metrics summary."""
        uptime = (datetime.utcnow() - self.start_time).total_seconds()

        return {
            "system": {
                "uptime_seconds": uptime,
                "last_update": self.last_update.isoformat(),
            },
            "decisions": {
                "total": self.decider_metrics.total_decisions,
                "executed": self.decider_metrics.decisions_executed,
                "execution_rate": (
                    self.decider_metrics.decisions_executed / self.decider_metrics.total_decisions
                    if self.decider_metrics.total_decisions > 0
                    else 0.0
                ),
                "avg_confidence": round(self.decider_metrics.avg_confidence, 3),
                "avg_edge_bps": round(self.decider_metrics.avg_edge_bps, 2),
                "win_rate": round(self.decider_metrics.win_rate, 3),
                "sharpe_ratio": round(self.decider_metrics.sharpe_ratio, 2),
            },
            "execution": {
                "total": self.execution_metrics.total_executions,
                "successful": self.execution_metrics.successful_executions,
                "failed": self.execution_metrics.failed_executions,
                "success_rate": round(self.execution_metrics.success_rate, 3),
                "total_profit_usd": round(self.execution_metrics.total_profit_usd, 2),
                "total_gas_cost_usd": round(self.execution_metrics.total_gas_cost_usd, 2),
                "net_profit_usd": round(
                    self.execution_metrics.total_profit_usd
                    - self.execution_metrics.total_gas_cost_usd,
                    2,
                ),
                "avg_execution_time_ms": round(self.execution_metrics.avg_execution_time_ms, 1),
            },
            "opportunities": {
                "detected": self.opportunity_metrics.opportunities_detected,
                "executed": self.opportunity_metrics.opportunities_executed,
                "conversion_rate": round(self.opportunity_metrics.conversion_rate, 3),
                "avg_quality": round(self.opportunity_metrics.avg_opportunity_quality, 3),
                "total_estimated_profit": round(
                    self.opportunity_metrics.total_estimated_profit, 2
                ),
            },
            "profitability": {
                "predicted_profit": round(self.decider_metrics.total_predicted_profit, 2),
                "actual_profit": round(self.decider_metrics.total_actual_profit, 2),
                "prediction_accuracy": (
                    round(
                        self.decider_metrics.total_actual_profit
                        / self.decider_metrics.total_predicted_profit,
                        3,
                    )
                    if self.decider_metrics.total_predicted_profit > 0
                    else 0.0
                ),
            },
            "models": {
                name: {
                    "trained": metrics.is_trained,
                    "samples": metrics.training_samples,
                    "accuracy": round(metrics.prediction_accuracy, 3),
                    "confidence": round(metrics.avg_prediction_confidence, 3),
                    "last_training": (
                        metrics.last_training_time.isoformat()
                        if metrics.last_training_time
                        else None
                    ),
                }
                for name, metrics in self.model_metrics.items()
            },
        }

    def get_recent_performance(self, window_minutes: int = 60) -> dict[str, Any]:
        """Get performance metrics for recent time window."""
        cutoff_time = datetime.utcnow() - timedelta(minutes=window_minutes)

        recent_profits = [
            profit for timestamp, profit in self.profit_history if timestamp >= cutoff_time
        ]

        recent_executions = [
            data for timestamp, data in self.execution_history if timestamp >= cutoff_time
        ]

        recent_decisions = [
            data for timestamp, data in self.decision_history if timestamp >= cutoff_time
        ]

        return {
            "window_minutes": window_minutes,
            "total_profit": round(sum(recent_profits), 2) if recent_profits else 0.0,
            "avg_profit_per_trade": (
                round(sum(recent_profits) / len(recent_profits), 2) if recent_profits else 0.0
            ),
            "num_executions": len(recent_executions),
            "success_rate": (
                round(sum(1 for e in recent_executions if e["success"]) / len(recent_executions), 3)
                if recent_executions
                else 0.0
            ),
            "num_decisions": len(recent_decisions),
            "execution_rate": (
                round(
                    sum(1 for d in recent_decisions if d["executed"]) / len(recent_decisions), 3
                )
                if recent_decisions
                else 0.0
            ),
        }

    def _check_alerts(self) -> None:
        """Check if any alert thresholds are breached."""
        alerts = []

        # Win rate alert
        if self.decider_metrics.win_rate < self.alert_thresholds["min_win_rate"]:
            alerts.append(
                {
                    "type": "low_win_rate",
                    "value": self.decider_metrics.win_rate,
                    "threshold": self.alert_thresholds["min_win_rate"],
                }
            )

        # Gas cost alert
        if self.execution_metrics.total_profit_usd > 0:
            gas_cost_pct = (
                self.execution_metrics.total_gas_cost_usd / self.execution_metrics.total_profit_usd
            )
            if gas_cost_pct > self.alert_thresholds["max_gas_cost_pct"]:
                alerts.append(
                    {
                        "type": "high_gas_cost",
                        "value": gas_cost_pct,
                        "threshold": self.alert_thresholds["max_gas_cost_pct"],
                    }
                )

        # Success rate alert
        if self.execution_metrics.success_rate < self.alert_thresholds["min_success_rate"]:
            alerts.append(
                {
                    "type": "low_success_rate",
                    "value": self.execution_metrics.success_rate,
                    "threshold": self.alert_thresholds["min_success_rate"],
                }
            )

        # Log alerts
        for alert in alerts:
            log.warning("ai_metrics.alert", **alert)

    async def start_periodic_logging(self, interval_seconds: int = 60) -> None:
        """Start periodic metrics logging.

        Args:
            interval_seconds: Logging interval in seconds
        """
        log.info("ai_metrics.periodic_logging_started", interval=interval_seconds)

        while True:
            await asyncio.sleep(interval_seconds)

            summary = self.get_summary()
            recent = self.get_recent_performance(window_minutes=10)

            log.info(
                "ai_metrics.periodic_update",
                summary=summary,
                recent_10min=recent,
            )


# Global metrics collector instance
_metrics_collector: Optional[AIMetricsCollector] = None


def get_metrics_collector() -> AIMetricsCollector:
    """Get global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = AIMetricsCollector()
    return _metrics_collector


def reset_metrics() -> None:
    """Reset all metrics."""
    global _metrics_collector
    _metrics_collector = AIMetricsCollector()
    log.info("ai_metrics.reset")
