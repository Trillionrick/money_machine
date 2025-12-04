"""Market regime detection and adaptive sizing.

Regimes influence optimal position sizing:
- Bull markets: higher leverage, momentum works
- Bear markets: lower leverage, mean reversion works
- High volatility: reduce size, widen stops
- Low volatility: increase size, tighter stops
"""

from collections import deque
from enum import StrEnum
from typing import cast

import polars as pl


class MarketRegime(StrEnum):
    """Market regime classification."""

    BULL_LOW_VOL = "bull_low_vol"  # Best: increase leverage
    BULL_HIGH_VOL = "bull_high_vol"  # Good: momentum trades
    BEAR_LOW_VOL = "bear_low_vol"  # Neutral: mean reversion
    BEAR_HIGH_VOL = "bear_high_vol"  # Worst: reduce exposure
    SIDEWAYS = "sideways"  # Range-bound: market making


class RegimeDetector:
    """Detect market regime using price and volatility.

    Uses a simple but effective heuristic:
    1. Trend: SMA slope
    2. Volatility: rolling standard deviation
    3. Combine into regime classification

    Example:
        >>> detector = RegimeDetector(lookback=60)
        >>> for price in price_stream:
        ...     regime = detector.update(price)
        ...     print(f"Current regime: {regime}")
    """

    def __init__(self, lookback: int = 60) -> None:
        """Initialize regime detector.

        Args:
            lookback: Number of periods for regime calculation
        """
        self.lookback = lookback
        self.prices = deque(maxlen=lookback)

        # Regime thresholds
        self.trend_threshold = 0.0  # 0% for bull/bear classification
        self.vol_threshold = 0.015  # 1.5% daily vol threshold

    def update(self, price: float) -> MarketRegime:
        """Update with new price and return current regime.

        Args:
            price: New price observation

        Returns:
            Current market regime
        """
        self.prices.append(price)

        if len(self.prices) < self.lookback:
            return MarketRegime.SIDEWAYS  # Default until enough data

        return self._calculate_regime()

    def _calculate_regime(self) -> MarketRegime:
        """Calculate current market regime."""
        prices = pl.Series(list(self.prices), dtype=pl.Float64)

        # Calculate trend (SMA slope)
        sma = prices.mean()
        first_half_mean = prices[: len(prices) // 2].mean()

        # Handle None values with defaults
        if sma is None or first_half_mean is None or first_half_mean == 0:
            return MarketRegime.SIDEWAYS

        # Type narrowing: assert values are not None after the check
        assert sma is not None
        assert first_half_mean is not None

        # Convert to Python float for calculations
        # Use cast to tell type checker these are numeric after validation
        sma_val: float = float(cast(float, sma))
        first_half_val: float = float(cast(float, first_half_mean))
        trend = (sma_val - first_half_val) / first_half_val

        # Calculate volatility (rolling std of returns)
        returns = prices.pct_change().drop_nulls()

        if len(returns) == 0:
            volatility = 0.0
        else:
            returns_std = returns.std()
            # Ensure we handle None and convert properly to float
            volatility = 0.0 if returns_std is None else float(cast(float, returns_std))

        # Classify regime
        is_bull = trend > self.trend_threshold
        is_high_vol = volatility > self.vol_threshold

        # Determine regime
        if abs(trend) < self.trend_threshold / 2:
            return MarketRegime.SIDEWAYS

        if is_bull:
            if is_high_vol:
                return MarketRegime.BULL_HIGH_VOL
            return MarketRegime.BULL_LOW_VOL
        if is_high_vol:
            return MarketRegime.BEAR_HIGH_VOL
        return MarketRegime.BEAR_LOW_VOL

    def get_regime_multiplier(self, regime: MarketRegime) -> float:
        """Get position sizing multiplier for regime.

        Returns:
            Multiplier for position size (1.0 = normal, <1.0 = reduce, >1.0 = increase)
        """
        multipliers = {
            MarketRegime.BULL_LOW_VOL: 1.2,  # Best environment: increase size
            MarketRegime.BULL_HIGH_VOL: 1.0,  # Good: normal size
            MarketRegime.SIDEWAYS: 0.8,  # Neutral: slight reduction
            MarketRegime.BEAR_LOW_VOL: 0.6,  # Caution: reduce size
            MarketRegime.BEAR_HIGH_VOL: 0.3,  # Crisis: minimal size
        }
        return multipliers.get(regime, 1.0)


class AdaptiveSizer:
    """Adaptive position sizing based on regime and recent performance.

    Combines:
    1. Base Kelly sizing
    2. Regime adjustment
    3. Performance-based adjustment (reduce after losses)
    4. Volatility scaling

    This creates convex payoffs: bet bigger when winning, smaller when losing.
    """

    def __init__(
        self,
        base_kelly_fraction: float = 0.25,
        *,
        performance_window: int = 20,
    ) -> None:
        """Initialize adaptive sizer.

        Args:
            base_kelly_fraction: Base Kelly fraction
            performance_window: Window for performance tracking
        """
        self.base_kelly_fraction = base_kelly_fraction
        self.performance_window = performance_window

        # Track recent PnL
        self.recent_pnl = deque(maxlen=performance_window)

    def calculate_size(
        self,
        edge: float,
        variance: float,
        regime: MarketRegime,
        *,
        current_equity: float,
        max_drawdown: float = 0.20,
    ) -> float:
        """Calculate adaptive position size.

        Args:
            edge: Expected excess return
            variance: Return variance
            regime: Current market regime
            current_equity: Current portfolio equity
            max_drawdown: Maximum tolerable drawdown

        Returns:
            Position size as fraction of equity
        """
        from src.core.sizing import kelly_with_ruin

        # Base Kelly size
        base_size = kelly_with_ruin(
            edge=edge,
            variance=variance,
            max_drawdown=max_drawdown,
            kelly_fraction=self.base_kelly_fraction,
        )

        # Regime adjustment
        regime_detector = RegimeDetector()
        regime_mult = regime_detector.get_regime_multiplier(regime)

        # Performance adjustment
        perf_mult = self._calculate_performance_multiplier()

        # Volatility adjustment
        vol_mult = self._calculate_volatility_multiplier(variance)

        # Combine adjustments
        final_size = base_size * regime_mult * perf_mult * vol_mult

        # Hard cap at 1.0 (100% of capital)
        return min(final_size, 1.0)

    def record_pnl(self, pnl: float) -> None:
        """Record trade PnL for performance tracking.

        Args:
            pnl: Profit/loss from trade (as fraction of capital)
        """
        self.recent_pnl.append(pnl)

    def _calculate_performance_multiplier(self) -> float:
        """Calculate multiplier based on recent performance.

        Logic: Reduce size after losses (defensive), maintain/increase after wins.
        This creates convexity: compound wins, limit losses.
        """
        if len(self.recent_pnl) == 0:
            return 1.0

        # Calculate recent Sharpe-like metric
        pnl_series = pl.Series(list(self.recent_pnl), dtype=pl.Float64)

        mean_pnl_result = pnl_series.mean()
        std_pnl_result = pnl_series.std()

        # Handle None values with defaults
        if mean_pnl_result is None or std_pnl_result is None:
            return 1.0

        # Type narrowing: assert values are not None after the check
        assert mean_pnl_result is not None
        assert std_pnl_result is not None

        # Use cast to tell type checker these are numeric after validation
        mean_pnl: float = float(cast(float, mean_pnl_result))
        std_pnl: float = float(cast(float, std_pnl_result))

        if std_pnl == 0:
            return 1.0

        performance_score = mean_pnl / std_pnl

        # Map performance to multiplier
        # Negative performance: reduce size significantly
        # Positive performance: increase size moderately
        if performance_score < -1.0:
            return 0.3  # Reduce to 30% after bad streak
        if performance_score < 0:
            return 0.6  # Reduce to 60% after small losses
        if performance_score < 1.0:
            return 1.0  # Normal size
        return 1.3  # Increase to 130% after strong performance

    def _calculate_volatility_multiplier(self, variance: float) -> float:
        """Scale size inversely with volatility.

        Higher volatility -> smaller positions (constant risk)
        """
        # Target volatility: 2% daily
        target_vol = 0.02
        current_vol = variance**0.5

        if current_vol == 0:
            return 1.0

        # Inverse scaling
        return min(target_vol / current_vol, 2.0)  # Cap at 2x
