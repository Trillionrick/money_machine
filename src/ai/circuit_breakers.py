"""Circuit breakers for risk management and system protection.

Implements multiple safety mechanisms:
- Win rate monitoring
- Drawdown protection
- Gas cost limits
- Consecutive failure tracking
- Volatility spike detection
- Anomalous behavior detection

Circuit breakers automatically disable trading when risk thresholds are exceeded.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from decimal import Decimal

log = structlog.get_logger()


class CircuitBreakerType(Enum):
    """Types of circuit breakers."""

    WIN_RATE = "win_rate"
    DRAWDOWN = "drawdown"
    GAS_COST = "gas_cost"
    CONSECUTIVE_FAILURES = "consecutive_failures"
    VOLATILITY_SPIKE = "volatility_spike"
    EXECUTION_FAILURES = "execution_failures"
    ANOMALOUS_SLIPPAGE = "anomalous_slippage"


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Trading disabled
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""

    # Thresholds
    min_win_rate: float = 0.40  # 40% minimum win rate
    max_drawdown_pct: float = 0.15  # 15% max drawdown
    max_gas_cost_ratio: float = 0.40  # Gas can't exceed 40% of profit
    max_consecutive_failures: int = 5  # Max 5 failures in a row
    max_volatility_spike: float = 3.0  # 3x normal volatility triggers
    max_slippage_deviation: float = 2.5  # 2.5 std devs from expected

    # Lookback windows
    win_rate_window: int = 20  # Last 20 trades
    drawdown_window_hours: int = 24  # 24-hour rolling window
    volatility_window_hours: int = 1  # Compare to 1-hour average

    # Recovery settings
    recovery_test_trades: int = 3  # Number of test trades in half-open state
    recovery_min_success_rate: float = 0.67  # 2/3 must succeed to close breaker
    auto_reset_hours: int = 4  # Auto attempt recovery after 4 hours


@dataclass
class CircuitBreakerStatus:
    """Status of a circuit breaker."""

    breaker_type: CircuitBreakerType
    state: CircuitBreakerState
    triggered_at: datetime | None = None
    trigger_reason: str | None = None
    trigger_value: float | None = None
    threshold_value: float | None = None
    recovery_attempts: int = 0
    last_reset_attempt: datetime | None = None


@dataclass
class TradeRecord:
    """Record of a trade for circuit breaker analysis."""

    timestamp: datetime
    success: bool
    profit: float
    gas_cost: float
    slippage_bps: float
    expected_slippage_bps: float
    symbol: str


class CircuitBreakerManager:
    """Manages all circuit breakers for the trading system.

    Features:
    - Multiple independent circuit breakers
    - Automatic recovery testing (half-open state)
    - Detailed alerting and logging
    - Historical breach tracking
    """

    def __init__(self, config: CircuitBreakerConfig | None = None):
        """Initialize circuit breaker manager.

        Args:
            config: Circuit breaker configuration
        """
        self.config = config or CircuitBreakerConfig()

        # Circuit breaker states
        self.breakers: dict[CircuitBreakerType, CircuitBreakerStatus] = {
            breaker_type: CircuitBreakerStatus(
                breaker_type=breaker_type,
                state=CircuitBreakerState.CLOSED,
            )
            for breaker_type in CircuitBreakerType
        }

        # Trade history for analysis
        self.trade_history: deque[TradeRecord] = deque(maxlen=1000)

        # Profit tracking for drawdown
        self.profit_history: deque[tuple[datetime, float]] = deque(maxlen=10000)
        self.peak_balance: float = 0.0
        self.current_balance: float = 0.0

        # Consecutive failure tracking
        self.consecutive_failures: int = 0

        # Recovery testing
        self.recovery_test_trades: deque[bool] = deque(maxlen=self.config.recovery_test_trades)

        log.info("circuit_breakers.initialized", config=self.config)

    def record_trade(
        self,
        success: bool,
        profit: float,
        gas_cost: float,
        slippage_bps: float,
        expected_slippage_bps: float,
        symbol: str,
    ) -> None:
        """Record a trade and check all circuit breakers.

        Args:
            success: Whether trade was successful
            profit: Profit in USD
            gas_cost: Gas cost in USD
            slippage_bps: Actual slippage in basis points
            expected_slippage_bps: Expected slippage
            symbol: Trading symbol
        """
        timestamp = datetime.utcnow()

        # Create trade record
        trade = TradeRecord(
            timestamp=timestamp,
            success=success,
            profit=profit,
            gas_cost=gas_cost,
            slippage_bps=slippage_bps,
            expected_slippage_bps=expected_slippage_bps,
            symbol=symbol,
        )

        self.trade_history.append(trade)

        # Update balance tracking
        net_profit = profit - gas_cost
        self.current_balance += net_profit
        self.profit_history.append((timestamp, self.current_balance))

        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance

        # Update consecutive failures
        if success:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1

        # Check all circuit breakers
        self._check_win_rate_breaker()
        self._check_drawdown_breaker()
        self._check_gas_cost_breaker()
        self._check_consecutive_failure_breaker()
        self._check_slippage_breaker(slippage_bps, expected_slippage_bps)

        # If in half-open state, track recovery
        if any(b.state == CircuitBreakerState.HALF_OPEN for b in self.breakers.values()):
            self.recovery_test_trades.append(success)
            self._check_recovery()

        log.debug(
            "circuit_breakers.trade_recorded",
            success=success,
            profit=profit,
            consecutive_failures=self.consecutive_failures,
        )

    def record_volatility_spike(self, symbol: str, current_vol: float, normal_vol: float) -> None:
        """Record volatility spike detection.

        Args:
            symbol: Trading symbol
            current_vol: Current volatility
            normal_vol: Normal/average volatility
        """
        ratio = current_vol / normal_vol if normal_vol > 0 else 0

        if ratio > self.config.max_volatility_spike:
            self._trigger_breaker(
                CircuitBreakerType.VOLATILITY_SPIKE,
                reason=f"Volatility spike for {symbol}: {ratio:.2f}x normal",
                value=ratio,
                threshold=self.config.max_volatility_spike,
            )

    def record_execution_failure(self, error_type: str, symbol: str) -> None:
        """Record an execution failure.

        Args:
            error_type: Type of error encountered
            symbol: Trading symbol
        """
        # Check recent execution failures
        recent_window = timedelta(minutes=15)
        cutoff = datetime.utcnow() - recent_window

        recent_trades = [t for t in self.trade_history if t.timestamp >= cutoff]
        if not recent_trades:
            return

        failure_rate = sum(1 for t in recent_trades if not t.success) / len(recent_trades)

        if failure_rate > 0.8:  # 80% failure rate
            self._trigger_breaker(
                CircuitBreakerType.EXECUTION_FAILURES,
                reason=f"High execution failure rate: {failure_rate:.1%} in last 15min",
                value=failure_rate,
                threshold=0.8,
            )

    def is_trading_allowed(self) -> tuple[bool, str | None]:
        """Check if trading is currently allowed.

        Returns:
            Tuple of (allowed: bool, reason: str | None)
        """
        # Check all breakers
        for breaker_type, status in self.breakers.items():
            if status.state == CircuitBreakerState.OPEN:
                reason = (
                    f"{breaker_type.value} circuit breaker is OPEN: {status.trigger_reason}"
                )
                return False, reason

        return True, None

    def get_open_breaker(self) -> CircuitBreakerStatus | None:
        """Return details for the first open circuit breaker, if any."""
        for status in self.breakers.values():
            if status.state == CircuitBreakerState.OPEN:
                return status
        return None

    def get_status_snapshot(self) -> list[dict[str, object]]:
        """Return a serializable snapshot of all circuit breaker states."""
        snapshot = []
        for breaker_type, status in self.breakers.items():
            snapshot.append(
                {
                    "breaker_type": breaker_type.value,
                    "state": status.state.value,
                    "triggered_at": status.triggered_at.isoformat() if status.triggered_at else None,
                    "trigger_reason": status.trigger_reason,
                    "trigger_value": status.trigger_value,
                    "threshold_value": status.threshold_value,
                    "recovery_attempts": status.recovery_attempts,
                    "last_reset_attempt": status.last_reset_attempt.isoformat()
                    if status.last_reset_attempt
                    else None,
                }
            )
        return snapshot

    def _check_win_rate_breaker(self) -> None:
        """Check win rate circuit breaker."""
        if len(self.trade_history) < self.config.win_rate_window:
            return  # Not enough data yet

        recent_trades = list(self.trade_history)[-self.config.win_rate_window :]
        wins = sum(1 for t in recent_trades if t.success)
        win_rate = wins / len(recent_trades)

        if win_rate < self.config.min_win_rate:
            self._trigger_breaker(
                CircuitBreakerType.WIN_RATE,
                reason=f"Win rate dropped to {win_rate:.1%} (min: {self.config.min_win_rate:.1%})",
                value=win_rate,
                threshold=self.config.min_win_rate,
            )

    def _check_drawdown_breaker(self) -> None:
        """Check drawdown circuit breaker."""
        if self.peak_balance <= 0:
            return  # No profit history yet

        drawdown = (self.peak_balance - self.current_balance) / self.peak_balance

        if drawdown > self.config.max_drawdown_pct:
            self._trigger_breaker(
                CircuitBreakerType.DRAWDOWN,
                reason=f"Drawdown of {drawdown:.1%} exceeded max {self.config.max_drawdown_pct:.1%}",
                value=drawdown,
                threshold=self.config.max_drawdown_pct,
            )

    def _check_gas_cost_breaker(self) -> None:
        """Check gas cost circuit breaker."""
        if len(self.trade_history) < 5:
            return

        recent_trades = list(self.trade_history)[-10:]  # Last 10 trades
        successful_trades = [t for t in recent_trades if t.success and t.profit > 0]

        if not successful_trades:
            return

        # Calculate gas cost as % of profit
        total_profit = sum(t.profit for t in successful_trades)
        total_gas = sum(t.gas_cost for t in successful_trades)

        if total_profit <= 0:
            return

        gas_ratio = total_gas / total_profit

        if gas_ratio > self.config.max_gas_cost_ratio:
            self._trigger_breaker(
                CircuitBreakerType.GAS_COST,
                reason=f"Gas costs are {gas_ratio:.1%} of profits (max: {self.config.max_gas_cost_ratio:.1%})",
                value=gas_ratio,
                threshold=self.config.max_gas_cost_ratio,
            )

    def _check_consecutive_failure_breaker(self) -> None:
        """Check consecutive failure circuit breaker."""
        if self.consecutive_failures >= self.config.max_consecutive_failures:
            self._trigger_breaker(
                CircuitBreakerType.CONSECUTIVE_FAILURES,
                reason=f"{self.consecutive_failures} consecutive failures",
                value=float(self.consecutive_failures),
                threshold=float(self.config.max_consecutive_failures),
            )

    def _check_slippage_breaker(self, actual: float, expected: float) -> None:
        """Check slippage anomaly circuit breaker."""
        if len(self.trade_history) < 20:
            return

        # Calculate historical slippage deviation
        recent_trades = list(self.trade_history)[-50:]
        slippage_diffs = [
            t.slippage_bps - t.expected_slippage_bps
            for t in recent_trades
            if t.expected_slippage_bps > 0
        ]

        if not slippage_diffs:
            return

        import numpy as np

        mean_diff = np.mean(slippage_diffs)
        std_diff = np.std(slippage_diffs)

        if std_diff == 0:
            return

        # Check if current slippage is anomalous
        current_diff = actual - expected
        z_score = abs((current_diff - mean_diff) / std_diff)

        if z_score > self.config.max_slippage_deviation:
            self._trigger_breaker(
                CircuitBreakerType.ANOMALOUS_SLIPPAGE,
                reason=f"Anomalous slippage: {z_score:.2f} std devs from expected",
                value=float(z_score),
                threshold=self.config.max_slippage_deviation,
            )

    def _trigger_breaker(
        self,
        breaker_type: CircuitBreakerType,
        reason: str,
        value: float,
        threshold: float,
    ) -> None:
        """Trigger a circuit breaker.

        Args:
            breaker_type: Type of breaker to trigger
            reason: Reason for triggering
            value: Current value that triggered
            threshold: Threshold that was exceeded
        """
        status = self.breakers[breaker_type]

        # Don't retrigger if already open
        if status.state == CircuitBreakerState.OPEN:
            return

        status.state = CircuitBreakerState.OPEN
        status.triggered_at = datetime.utcnow()
        status.trigger_reason = reason
        status.trigger_value = value
        status.threshold_value = threshold

        log.error(
            "circuit_breaker.TRIGGERED",
            breaker=breaker_type.value,
            reason=reason,
            value=value,
            threshold=threshold,
        )

    def attempt_recovery(self, breaker_type: CircuitBreakerType) -> bool:
        """Manually attempt to recover a circuit breaker.

        Args:
            breaker_type: Type of breaker to recover

        Returns:
            True if recovery initiated, False if not allowed yet
        """
        status = self.breakers[breaker_type]

        if status.state != CircuitBreakerState.OPEN:
            return False

        # Check if enough time has passed
        if status.triggered_at:
            time_since_trigger = datetime.utcnow() - status.triggered_at
            min_wait = timedelta(hours=self.config.auto_reset_hours)

            if time_since_trigger < min_wait:
                log.warning(
                    "circuit_breaker.recovery_too_soon",
                    breaker=breaker_type.value,
                    time_since_trigger=time_since_trigger.total_seconds(),
                    min_wait=min_wait.total_seconds(),
                )
                return False

        # Enter half-open state for testing
        status.state = CircuitBreakerState.HALF_OPEN
        status.last_reset_attempt = datetime.utcnow()
        status.recovery_attempts += 1
        self.recovery_test_trades.clear()

        log.warning(
            "circuit_breaker.recovery_started",
            breaker=breaker_type.value,
            attempt=status.recovery_attempts,
        )

        return True

    def _check_recovery(self) -> None:
        """Check if recovery test trades are successful."""
        if len(self.recovery_test_trades) < self.config.recovery_test_trades:
            return  # Not enough test trades yet

        success_rate = (
            sum(self.recovery_test_trades) / len(self.recovery_test_trades)
        )

        # Find half-open breakers
        for breaker_type, status in self.breakers.items():
            if status.state != CircuitBreakerState.HALF_OPEN:
                continue

            if success_rate >= self.config.recovery_min_success_rate:
                # Recovery successful
                status.state = CircuitBreakerState.CLOSED
                status.triggered_at = None
                status.trigger_reason = None

                log.info(
                    "circuit_breaker.recovered",
                    breaker=breaker_type.value,
                    test_success_rate=success_rate,
                )
            else:
                # Recovery failed, return to open
                status.state = CircuitBreakerState.OPEN

                log.warning(
                    "circuit_breaker.recovery_failed",
                    breaker=breaker_type.value,
                    test_success_rate=success_rate,
                    required=self.config.recovery_min_success_rate,
                )

            self.recovery_test_trades.clear()

    def get_status(self) -> dict[str, dict]:
        """Get status of all circuit breakers.

        Returns:
            Dict mapping breaker type to status info
        """
        return {
            breaker_type.value: {
                "state": status.state.value,
                "triggered_at": status.triggered_at.isoformat() if status.triggered_at else None,
                "trigger_reason": status.trigger_reason,
                "trigger_value": status.trigger_value,
                "threshold_value": status.threshold_value,
                "recovery_attempts": status.recovery_attempts,
            }
            for breaker_type, status in self.breakers.items()
        }

    def reset_all(self) -> None:
        """Reset all circuit breakers (use with caution)."""
        for breaker_type, status in self.breakers.items():
            status.state = CircuitBreakerState.CLOSED
            status.triggered_at = None
            status.trigger_reason = None
            status.recovery_attempts = 0

        self.consecutive_failures = 0
        self.recovery_test_trades.clear()

        log.warning("circuit_breaker.all_reset")


# Global singleton
_manager: CircuitBreakerManager | None = None


def get_circuit_breaker_manager() -> CircuitBreakerManager:
    """Get global CircuitBreakerManager instance."""
    global _manager
    if _manager is None:
        _manager = CircuitBreakerManager()
    return _manager
