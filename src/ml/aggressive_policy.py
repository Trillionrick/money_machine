"""ML-powered aggressive policy optimized for target-hitting.

This is the "brain" that implements your philosophy:
- Scan for high-convexity opportunities (ML layer)
- Size aggressively for target-hitting (not Kelly)
- Accept high variance and ruin risk
- Maximize P(hitting wealth target)
"""

import polars as pl

from src.core import Order, OrderSeq, OrderType, Policy, PortfolioState, MarketSnapshot, Side
from src.core.target_optimizer import TargetObjective, TargetOptimizer
from src.core.types import ContextMap
from src.ml.feature_engine import ConvexityScanner


class AggressiveMLPolicy(Policy):
    """ML-powered policy optimized for rapid wealth generation.

    Philosophy:
    - Use ML to find asymmetric opportunities
    - Size for TARGET, not survival
    - Take concentrated bets on high-convexity setups
    - Accept ruin as cost of attempting 100x

    This is NOT a Sharpe-optimizing, Kelly-sizing, slow-compound strategy.
    This is a sprint-to-target, accept-variance, many-attempts strategy.

    Example:
        >>> policy = AggressiveMLPolicy(
        ...     target_wealth=500_000,
        ...     current_wealth=5_000,
        ...     time_horizon_days=365,
        ... )
        >>> orders = policy.decide(portfolio, snapshot)
    """

    def __init__(
        self,
        symbols: list[str],
        target_wealth: float,
        current_wealth: float,
        time_horizon_days: int = 252,
        *,
        max_positions: int = 3,
        min_convexity_score: float = 0.1,
        max_leverage: float = 2.0,
    ) -> None:
        """Initialize aggressive ML policy.

        Args:
            symbols: Symbols to scan
            target_wealth: Wealth target to hit
            current_wealth: Starting wealth
            time_horizon_days: Days to hit target
            max_positions: Max concurrent positions
            min_convexity_score: Min score to consider
            max_leverage: Max leverage per position
        """
        self.symbols = symbols
        self.target_wealth = target_wealth
        self.current_wealth = current_wealth
        self.time_horizon_days = time_horizon_days
        self.max_positions = max_positions
        self.max_leverage = max_leverage

        # ML components
        self.scanner = ConvexityScanner(min_convexity_score=min_convexity_score)
        self.target_optimizer = TargetOptimizer()

        # Track days elapsed
        self.days_elapsed = 0

    def decide(
        self,
        portfolio: PortfolioState,
        snapshot: MarketSnapshot,
        context: ContextMap | None = None,
    ) -> OrderSeq:
        """Generate aggressive orders based on ML convexity scan.

        Args:
            portfolio: Current portfolio
            snapshot: Market snapshot
            context: Optional context with market data history

        Returns:
            Aggressive orders sized for target-hitting
        """
        # Update time tracking
        self.days_elapsed += 1

        # Get market data from context (need history for features)
        if context is None or "market_data" not in context:
            return []  # Need historical data for ML features

        market_data = context["market_data"]

        # Scan for high-convexity opportunities
        opportunities = self.scanner.scan(market_data)

        if not opportunities:
            # No opportunities - exit existing positions if losing
            return self._exit_losing_positions(portfolio, snapshot)

        # Select top opportunities
        top_opportunities = opportunities[: self.max_positions]

        # Generate orders
        orders = []

        for opp in top_opportunities:
            order = self._create_aggressive_order(
                opportunity=opp,
                portfolio=portfolio,
                snapshot=snapshot,
            )

            if order:
                orders.append(order)

        return orders

    def _create_aggressive_order(
        self,
        opportunity: dict,
        portfolio: PortfolioState,
        snapshot: MarketSnapshot,
    ) -> Order | None:
        """Create aggressively sized order for opportunity.

        Args:
            opportunity: Dict with convexity metrics
            portfolio: Current portfolio
            snapshot: Market snapshot

        Returns:
            Aggressively sized order or None
        """
        symbol = opportunity["symbol"]
        price = snapshot.price(symbol)

        if price is None or price <= 0:
            return None

        # Estimate edge and variance from opportunity metrics
        # These are heuristics - in production, you'd use ML predictions
        edge = opportunity["convexity_score"] * 0.1  # 10% edge per 1.0 score
        variance = opportunity["volatility"] ** 2

        # Create target objective
        days_remaining = max(1, self.time_horizon_days - self.days_elapsed)
        objective = TargetObjective(
            current_wealth=portfolio.equity,
            target_wealth=self.target_wealth,
            time_horizon=days_remaining,
            max_attempts=5,  # Can try again if this fails
        )

        # Get AGGRESSIVE sizing (NOT Kelly!)
        size_fraction = self.target_optimizer.optimal_size(
            objective=objective,
            edge=edge,
            variance=variance,
            max_leverage=self.max_leverage,
        )

        # Calculate target value and quantity
        target_value = portfolio.equity * size_fraction
        target_quantity = target_value / price

        # Adjust for current position
        current_pos = portfolio.position(symbol)
        delta = target_quantity - current_pos

        # Only trade if significant
        if abs(delta * price) < portfolio.equity * 0.05:  # Less than 5%
            return None

        # Determine side and direction
        side = Side.BUY if delta > 0 else Side.SELL
        quantity = abs(delta)

        # Use LIMIT orders to avoid bad fills
        # But price aggressively (close to market)
        if side == Side.BUY:
            limit_price = price * 1.001  # 0.1% above market
        else:
            limit_price = price * 0.999  # 0.1% below market

        return Order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=limit_price,
            order_type=OrderType.LIMIT,
        )

    def _exit_losing_positions(
        self,
        portfolio: PortfolioState,
        snapshot: MarketSnapshot,
    ) -> OrderSeq:
        """Exit positions that are losing.

        When no new opportunities, cut losses quickly.
        """
        orders = []

        for symbol, quantity in portfolio.positions.items():
            if abs(quantity) < 0.01:
                continue

            price = snapshot.price(symbol)
            if price is None:
                continue

            # For simplicity, exit all positions when no opportunities
            # In production, you'd track entry prices and stop losses

            side = Side.SELL if quantity > 0 else Side.BUY

            orders.append(
                Order(
                    symbol=symbol,
                    side=side,
                    quantity=abs(quantity),
                    price=price,
                    order_type=OrderType.MARKET,
                )
            )

        return orders

    def on_fill(self, fill) -> None:
        """Handle fill notification.

        Args:
            fill: Fill object
        """
        # Could update internal state, log metrics, etc.
        pass


class AdaptiveAggressivePolicy(AggressiveMLPolicy):
    """Adaptive version that adjusts aggression based on progress.

    Key insight: If you're ahead of schedule, can be LESS aggressive.
    If you're behind, need to be MORE aggressive.
    """

    def decide(
        self,
        portfolio: PortfolioState,
        snapshot: MarketSnapshot,
        context: ContextMap | None = None,
    ) -> OrderSeq:
        """Adjust aggression based on progress toward goal.

        Args:
            portfolio: Current portfolio
            snapshot: Market snapshot
            context: Optional context

        Returns:
            Adaptively sized orders
        """
        # Calculate progress
        progress = portfolio.equity / self.current_wealth
        time_progress = self.days_elapsed / self.time_horizon_days

        # Required pace to hit target
        required_pace = (
            self.target_wealth / self.current_wealth
        ) ** time_progress

        # Are we ahead or behind?
        if progress > required_pace * 1.2:
            # Ahead of schedule - reduce aggression, lock in gains
            self.max_leverage = 1.0
        elif progress < required_pace * 0.8:
            # Behind schedule - increase aggression
            self.max_leverage = 3.0
        else:
            # On track - maintain
            self.max_leverage = 2.0

        # Generate orders with adjusted aggression
        return super().decide(portfolio, snapshot, context)
