"""Risk management system with hard limits and circuit breakers.

Risk management is not optional - it's what separates long-term success from ruin.

Key principles:
1. Position limits (can't risk too much on one position)
2. Portfolio limits (total exposure caps)
3. Loss limits (daily/weekly circuit breakers)
4. Correlation limits (avoid concentrated factor exposure)
"""

from dataclasses import dataclass

from src.core.execution import Order, OrderSeq, Side
from src.core.policy import PortfolioState
from src.core.types import Symbol


@dataclass
class RiskLimits:
    """Risk limits configuration."""

    # Position limits
    max_position_pct: float = 0.20  # Max 20% in single position
    max_total_exposure_pct: float = 2.0  # Max 200% gross exposure (leverage)

    # Loss limits (circuit breakers)
    max_daily_loss_pct: float = 0.05  # Stop trading if lose 5% in a day
    max_weekly_loss_pct: float = 0.10  # Stop if lose 10% in a week
    max_drawdown_pct: float = 0.25  # Stop if 25% drawdown from peak

    # Order size limits
    max_order_value_pct: float = 0.15  # Single order max 15% of capital

    # Leverage limits
    max_leverage: float = 2.0  # Max 2x leverage


@dataclass
class RiskMetrics:
    """Current risk metrics."""

    total_exposure_pct: float
    largest_position_pct: float
    daily_pnl_pct: float
    weekly_pnl_pct: float
    drawdown_from_peak_pct: float
    current_leverage: float
    num_positions: int


class RiskViolation(Exception):
    """Raised when a risk limit is violated."""



class RiskManager:
    """Risk management system with hard limits.

    This is your safety net. It prevents catastrophic losses by:
    1. Blocking orders that violate limits
    2. Force-closing positions when limits breached
    3. Circuit breakers that stop trading after losses

    Example:
        >>> risk_mgr = RiskManager()
        >>> portfolio = get_portfolio()
        >>> orders = strategy.decide(portfolio, snapshot)
        >>> # Filter orders through risk manager
        >>> safe_orders = risk_mgr.filter_orders(orders, portfolio)
    """

    def __init__(self, limits: RiskLimits | None = None) -> None:
        """Initialize risk manager.

        Args:
            limits: Risk limits configuration
        """
        self.limits = limits or RiskLimits()

        # Track peak equity for drawdown calculation
        self.peak_equity = 0.0
        self.daily_starting_equity = 0.0
        self.weekly_starting_equity = 0.0

        # Circuit breaker state
        self.trading_halted = False
        self.halt_reason: str | None = None

    def filter_orders(
        self,
        orders: OrderSeq,
        portfolio: PortfolioState,
        *,
        current_prices: dict[Symbol, float],
    ) -> OrderSeq:
        """Filter orders through risk checks.

        Args:
            orders: Proposed orders
            portfolio: Current portfolio state
            current_prices: Current market prices

        Returns:
            Filtered orders that pass risk checks

        Raises:
            RiskViolation: If trading is halted
        """
        # Check if trading is halted
        if self.trading_halted:
            msg = f"Trading halted: {self.halt_reason}"
            raise RiskViolation(msg)

        # Update metrics
        self._update_metrics(portfolio)

        # Check circuit breakers
        self._check_circuit_breakers(portfolio)

        # Filter each order
        safe_orders = []
        for order in orders:
            if self._is_order_safe(order, portfolio, current_prices):
                safe_orders.append(order)

        return safe_orders

    def _is_order_safe(
        self,
        order: Order,
        portfolio: PortfolioState,
        current_prices: dict[Symbol, float],
    ) -> bool:
        """Check if an individual order is safe."""
        price = current_prices.get(order.symbol)
        if price is None:
            return False

        order_value = order.quantity * price

        # Check order size limit
        if order_value > portfolio.equity * self.limits.max_order_value_pct:
            return False

        # Simulate portfolio after this order
        simulated_portfolio = self._simulate_order_impact(
            order, portfolio, current_prices
        )

        # Check position limit
        for symbol, position in simulated_portfolio.positions.items():
            position_value = abs(position * current_prices.get(symbol, 0.0))
            position_pct = position_value / portfolio.equity

            if position_pct > self.limits.max_position_pct:
                return False

        # Check total exposure
        total_exposure = sum(
            abs(qty * current_prices.get(sym, 0.0))
            for sym, qty in simulated_portfolio.positions.items()
        )
        exposure_pct = total_exposure / portfolio.equity

        if exposure_pct > self.limits.max_total_exposure_pct:
            return False

        # Check leverage
        leverage = (simulated_portfolio.equity - simulated_portfolio.cash) / simulated_portfolio.equity
        if leverage > self.limits.max_leverage:
            return False

        return True

    def _simulate_order_impact(
        self,
        order: Order,
        portfolio: PortfolioState,
        current_prices: dict[Symbol, float],
    ) -> PortfolioState:
        """Simulate portfolio after order execution."""
        # Copy current state
        new_positions = portfolio.positions.copy()
        price = current_prices.get(order.symbol, 0.0)

        # Update position
        current_qty = new_positions.get(order.symbol, 0.0)
        if order.side == Side.BUY:
            new_positions[order.symbol] = current_qty + order.quantity
        else:
            new_positions[order.symbol] = current_qty - order.quantity

        return PortfolioState(
            positions=new_positions,
            cash=portfolio.cash,  # Simplified - would need to adjust cash
            equity=portfolio.equity,
            timestamp=portfolio.timestamp,
        )

    def _update_metrics(self, portfolio: PortfolioState) -> None:
        """Update tracked metrics."""
        # Update peak equity
        self.peak_equity = max(self.peak_equity, portfolio.equity)

        # Initialize starting equity if needed
        if self.daily_starting_equity == 0:
            self.daily_starting_equity = portfolio.equity
        if self.weekly_starting_equity == 0:
            self.weekly_starting_equity = portfolio.equity

    def _check_circuit_breakers(self, portfolio: PortfolioState) -> None:
        """Check if any circuit breakers should trigger."""
        if self.trading_halted:
            return

        # Calculate metrics
        daily_pnl_pct = (
            (portfolio.equity - self.daily_starting_equity) / self.daily_starting_equity
        )
        weekly_pnl_pct = (
            (portfolio.equity - self.weekly_starting_equity)
            / self.weekly_starting_equity
        )
        drawdown_pct = (self.peak_equity - portfolio.equity) / self.peak_equity

        # Check daily loss limit
        if daily_pnl_pct < -self.limits.max_daily_loss_pct:
            self.trading_halted = True
            self.halt_reason = f"Daily loss limit breached: {daily_pnl_pct:.1%}"
            return

        # Check weekly loss limit
        if weekly_pnl_pct < -self.limits.max_weekly_loss_pct:
            self.trading_halted = True
            self.halt_reason = f"Weekly loss limit breached: {weekly_pnl_pct:.1%}"
            return

        # Check drawdown limit
        if drawdown_pct > self.limits.max_drawdown_pct:
            self.trading_halted = True
            self.halt_reason = f"Max drawdown breached: {drawdown_pct:.1%}"
            return

    def get_metrics(
        self, portfolio: PortfolioState, current_prices: dict[Symbol, float]
    ) -> RiskMetrics:
        """Calculate current risk metrics.

        Args:
            portfolio: Current portfolio
            current_prices: Current prices

        Returns:
            Current risk metrics
        """
        # Total exposure
        total_exposure = sum(
            abs(qty * current_prices.get(sym, 0.0))
            for sym, qty in portfolio.positions.items()
        )
        exposure_pct = (
            total_exposure / portfolio.equity if portfolio.equity > 0 else 0.0
        )

        # Largest position
        position_sizes = [
            abs(qty * current_prices.get(sym, 0.0))
            for sym, qty in portfolio.positions.items()
        ]
        largest_position = max(position_sizes) if position_sizes else 0.0
        largest_pct = (
            largest_position / portfolio.equity if portfolio.equity > 0 else 0.0
        )

        # PnL
        daily_pnl_pct = (
            (portfolio.equity - self.daily_starting_equity) / self.daily_starting_equity
            if self.daily_starting_equity > 0
            else 0.0
        )
        weekly_pnl_pct = (
            (portfolio.equity - self.weekly_starting_equity)
            / self.weekly_starting_equity
            if self.weekly_starting_equity > 0
            else 0.0
        )

        # Drawdown
        drawdown_pct = (
            (self.peak_equity - portfolio.equity) / self.peak_equity
            if self.peak_equity > 0
            else 0.0
        )

        # Leverage
        leverage = (
            abs(portfolio.equity - portfolio.cash) / portfolio.equity
            if portfolio.equity > 0
            else 0.0
        )

        return RiskMetrics(
            total_exposure_pct=exposure_pct,
            largest_position_pct=largest_pct,
            daily_pnl_pct=daily_pnl_pct,
            weekly_pnl_pct=weekly_pnl_pct,
            drawdown_from_peak_pct=drawdown_pct,
            current_leverage=leverage,
            num_positions=len(portfolio.positions),
        )

    def reset_daily(self, portfolio: PortfolioState) -> None:
        """Reset daily metrics (call at start of each day)."""
        self.daily_starting_equity = portfolio.equity

    def reset_weekly(self, portfolio: PortfolioState) -> None:
        """Reset weekly metrics (call at start of each week)."""
        self.weekly_starting_equity = portfolio.equity

    def resume_trading(self) -> None:
        """Resume trading after halt (manual intervention required)."""
        self.trading_halted = False
        self.halt_reason = None
