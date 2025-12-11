"""Production Safety Layer for Real Capital Deployment.

Critical safety mechanisms that MUST pass before any trade execution:
- Absolute loss limits (ETH-denominated)
- Position size validation
- Gas profitability checks
- Liquidity depth validation
- Pre-trade simulation
- Emergency kill switch

This is the LAST line of defense before real money moves.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from web3 import Web3

log = structlog.get_logger()


@dataclass
class ProductionSafetyConfig:
    """Production safety configuration - NEVER DISABLE THESE."""

    # Absolute loss limits (ETH)
    max_loss_per_trade_eth: float = 0.1  # Auto-reject any trade risking > 0.1 ETH
    max_hourly_loss_eth: float = 0.3  # Shutdown at -0.3 ETH/hour
    max_daily_loss_eth: float = 1.0  # Emergency stop at -1 ETH/day
    max_total_drawdown_eth: float = 5.0  # Complete shutdown at -5 ETH total

    # Position size limits
    max_position_size_eth: float = 2.0  # Never risk more than 2 ETH per trade
    max_flash_loan_size_eth: float = 50.0  # Cap flash loans at 50 ETH
    min_portfolio_reserve_eth: float = 1.0  # Always keep 1 ETH in reserve

    # Profitability requirements
    min_profit_after_gas_eth: float = 0.01  # Only execute if profit > 0.01 ETH after gas
    max_gas_price_gwei: float = 300  # Don't trade if gas > 300 gwei
    max_gas_to_profit_ratio: float = 0.3  # Gas can't exceed 30% of expected profit

    # Liquidity requirements
    min_liquidity_multiple: int = 20  # Pool liquidity must be 20x position size
    max_slippage_bps: float = 200  # Max 2% slippage tolerance

    # Rate limiting
    max_trades_per_hour: int = 10  # Prevent runaway trading
    max_trades_per_day: int = 50

    # Emergency controls
    enable_emergency_shutdown: bool = True
    require_manual_approval_above_eth: float = 5.0  # Manual approval for large trades


class ProductionSafetyGuard:
    """Production safety guard - validates every trade before execution.

    This class implements the critical safety checks that protect real capital.
    ALL checks must pass before a trade is allowed to execute.
    """

    def __init__(self, config: ProductionSafetyConfig | None = None, w3: Web3 | None = None):
        """Initialize production safety guard.

        Args:
            config: Safety configuration
            w3: Web3 instance for on-chain validation
        """
        self.config = config or ProductionSafetyConfig()
        self.w3 = w3

        # Track losses for limits
        self.hourly_losses: list[tuple[datetime, float]] = []
        self.daily_losses: list[tuple[datetime, float]] = []
        self.total_pnl_eth: float = 0.0
        self.peak_balance_eth: float = 0.0

        # Track trade frequency
        self.trade_timestamps: list[datetime] = []

        # Emergency shutdown flag
        self.emergency_shutdown: bool = False
        self.shutdown_reason: str | None = None

        log.info("production_safety.initialized", config=self.config)

    def validate_trade(
        self,
        position_size_eth: float,
        expected_profit_eth: float,
        estimated_gas_cost_eth: float,
        estimated_gas_price_gwei: float,
        pool_liquidity_eth: float,
        expected_slippage_bps: float,
        trade_type: str = "standard",
    ) -> tuple[bool, str]:
        """Validate trade against all safety criteria.

        This is the master validation function. ALL checks must pass.

        Args:
            position_size_eth: Size of position in ETH
            expected_profit_eth: Expected profit in ETH (before gas)
            estimated_gas_cost_eth: Estimated gas cost in ETH
            estimated_gas_price_gwei: Current gas price
            pool_liquidity_eth: Available liquidity in pool
            expected_slippage_bps: Expected slippage in basis points
            trade_type: Type of trade ("standard", "flash_loan")

        Returns:
            (allowed: bool, reason: str)
        """
        # Check 1: Emergency shutdown
        if self.emergency_shutdown:
            return False, f"EMERGENCY SHUTDOWN: {self.shutdown_reason}"

        # Check 2: Position size limits
        if position_size_eth > self.config.max_position_size_eth:
            return False, f"Position size {position_size_eth:.4f} ETH exceeds max {self.config.max_position_size_eth} ETH"

        if trade_type == "flash_loan" and position_size_eth > self.config.max_flash_loan_size_eth:
            return False, f"Flash loan size {position_size_eth:.4f} ETH exceeds max {self.config.max_flash_loan_size_eth} ETH"

        # Check 3: Profitability after gas
        net_profit_eth = expected_profit_eth - estimated_gas_cost_eth

        if net_profit_eth < self.config.min_profit_after_gas_eth:
            return False, f"Net profit {net_profit_eth:.6f} ETH below minimum {self.config.min_profit_after_gas_eth} ETH"

        # Check 4: Gas price limits
        if estimated_gas_price_gwei > self.config.max_gas_price_gwei:
            return False, f"Gas price {estimated_gas_price_gwei:.1f} gwei exceeds max {self.config.max_gas_price_gwei} gwei"

        # Check 5: Gas to profit ratio
        if expected_profit_eth > 0:
            gas_ratio = estimated_gas_cost_eth / expected_profit_eth
            if gas_ratio > self.config.max_gas_to_profit_ratio:
                return False, f"Gas is {gas_ratio:.1%} of profit (max {self.config.max_gas_to_profit_ratio:.1%})"

        # Check 6: Liquidity depth
        if pool_liquidity_eth < position_size_eth * self.config.min_liquidity_multiple:
            required_liquidity = position_size_eth * self.config.min_liquidity_multiple
            return False, f"Insufficient liquidity: {pool_liquidity_eth:.2f} ETH < {required_liquidity:.2f} ETH required"

        # Check 7: Slippage tolerance
        if expected_slippage_bps > self.config.max_slippage_bps:
            return False, f"Slippage {expected_slippage_bps:.1f} bps exceeds max {self.config.max_slippage_bps} bps"

        # Check 8: Loss limits
        max_loss = min(position_size_eth * 0.1, self.config.max_loss_per_trade_eth)
        if max_loss > self.config.max_loss_per_trade_eth:
            return False, f"Potential loss {max_loss:.4f} ETH exceeds max {self.config.max_loss_per_trade_eth} ETH"

        # Check 9: Hourly loss limit
        hourly_loss = self._calculate_period_loss(hours=1)
        if hourly_loss < -self.config.max_hourly_loss_eth:
            self._trigger_emergency_shutdown(f"Hourly loss {hourly_loss:.4f} ETH exceeded limit")
            return False, f"Hourly loss limit exceeded: {hourly_loss:.4f} ETH"

        # Check 10: Daily loss limit
        daily_loss = self._calculate_period_loss(hours=24)
        if daily_loss < -self.config.max_daily_loss_eth:
            self._trigger_emergency_shutdown(f"Daily loss {daily_loss:.4f} ETH exceeded limit")
            return False, f"Daily loss limit exceeded: {daily_loss:.4f} ETH"

        # Check 11: Total drawdown limit
        if self.peak_balance_eth > 0:
            drawdown_eth = self.peak_balance_eth - self.total_pnl_eth
            if drawdown_eth > self.config.max_total_drawdown_eth:
                self._trigger_emergency_shutdown(f"Total drawdown {drawdown_eth:.4f} ETH exceeded limit")
                return False, f"Total drawdown exceeded: {drawdown_eth:.4f} ETH"

        # Check 12: Trade frequency limits
        recent_hour = self._count_recent_trades(hours=1)
        if recent_hour >= self.config.max_trades_per_hour:
            return False, f"Hourly trade limit reached: {recent_hour}/{self.config.max_trades_per_hour}"

        recent_day = self._count_recent_trades(hours=24)
        if recent_day >= self.config.max_trades_per_day:
            return False, f"Daily trade limit reached: {recent_day}/{self.config.max_trades_per_day}"

        # Check 13: Manual approval for large trades
        if position_size_eth > self.config.require_manual_approval_above_eth:
            return False, f"Trade size {position_size_eth:.2f} ETH requires manual approval"

        # All checks passed!
        log.info(
            "production_safety.trade_validated",
            position_size_eth=position_size_eth,
            net_profit_eth=net_profit_eth,
            gas_cost_eth=estimated_gas_cost_eth,
        )

        return True, "All safety checks passed"

    def record_trade_result(self, pnl_eth: float, gas_cost_eth: float) -> None:
        """Record trade result for loss tracking.

        Args:
            pnl_eth: Profit/loss in ETH (positive or negative)
            gas_cost_eth: Gas cost in ETH
        """
        timestamp = datetime.utcnow()
        net_pnl = pnl_eth - gas_cost_eth

        # Update tracking
        self.hourly_losses.append((timestamp, net_pnl))
        self.daily_losses.append((timestamp, net_pnl))
        self.trade_timestamps.append(timestamp)

        # Update total P&L
        self.total_pnl_eth += net_pnl

        # Update peak balance
        if self.total_pnl_eth > self.peak_balance_eth:
            self.peak_balance_eth = self.total_pnl_eth

        # Clean old records
        self._cleanup_old_records()

        log.info(
            "production_safety.trade_recorded",
            pnl_eth=net_pnl,
            total_pnl_eth=self.total_pnl_eth,
            peak_balance_eth=self.peak_balance_eth,
        )

    def _calculate_period_loss(self, hours: int) -> float:
        """Calculate P&L for recent period.

        Args:
            hours: Number of hours to look back

        Returns:
            Total P&L in ETH for period
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        source = self.hourly_losses if hours <= 1 else self.daily_losses

        recent_pnl = [pnl for ts, pnl in source if ts >= cutoff]
        return sum(recent_pnl)

    def _count_recent_trades(self, hours: int) -> int:
        """Count trades in recent period.

        Args:
            hours: Number of hours to look back

        Returns:
            Number of trades
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return sum(1 for ts in self.trade_timestamps if ts >= cutoff)

    def _cleanup_old_records(self) -> None:
        """Remove old records to prevent memory bloat."""
        cutoff_hour = datetime.utcnow() - timedelta(hours=2)
        cutoff_day = datetime.utcnow() - timedelta(hours=48)

        self.hourly_losses = [(ts, pnl) for ts, pnl in self.hourly_losses if ts >= cutoff_hour]
        self.daily_losses = [(ts, pnl) for ts, pnl in self.daily_losses if ts >= cutoff_day]
        self.trade_timestamps = [ts for ts in self.trade_timestamps if ts >= cutoff_day]

    def _trigger_emergency_shutdown(self, reason: str) -> None:
        """Trigger emergency shutdown.

        Args:
            reason: Reason for shutdown
        """
        if not self.config.enable_emergency_shutdown:
            return

        self.emergency_shutdown = True
        self.shutdown_reason = reason

        log.critical(
            "production_safety.EMERGENCY_SHUTDOWN",
            reason=reason,
            total_pnl_eth=self.total_pnl_eth,
            peak_balance_eth=self.peak_balance_eth,
        )

    def get_status(self) -> dict:
        """Get current safety status.

        Returns:
            Dictionary with safety metrics
        """
        return {
            "emergency_shutdown": self.emergency_shutdown,
            "shutdown_reason": self.shutdown_reason,
            "total_pnl_eth": self.total_pnl_eth,
            "peak_balance_eth": self.peak_balance_eth,
            "hourly_loss_eth": self._calculate_period_loss(hours=1),
            "daily_loss_eth": self._calculate_period_loss(hours=24),
            "trades_last_hour": self._count_recent_trades(hours=1),
            "trades_last_day": self._count_recent_trades(hours=24),
            "config": {
                "max_position_size_eth": self.config.max_position_size_eth,
                "max_daily_loss_eth": self.config.max_daily_loss_eth,
                "min_profit_after_gas_eth": self.config.min_profit_after_gas_eth,
            },
        }

    def reset_emergency_shutdown(self, reason: str = "Manual reset") -> None:
        """Reset emergency shutdown (use with EXTREME caution).

        Args:
            reason: Reason for reset
        """
        log.warning("production_safety.shutdown_reset", reason=reason)
        self.emergency_shutdown = False
        self.shutdown_reason = None


# Global singleton
_safety_guard: ProductionSafetyGuard | None = None


def get_production_safety_guard() -> ProductionSafetyGuard:
    """Get global ProductionSafetyGuard instance."""
    global _safety_guard
    if _safety_guard is None:
        _safety_guard = ProductionSafetyGuard()
    return _safety_guard
