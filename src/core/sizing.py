"""Position sizing and utility functions.

This module implements the mathematical foundation for position sizing:
- Kelly criterion (log-utility maximization)
- Target-hitting utility (maximize probability of reaching wealth target)
- Risk-adjusted sizing with drawdown constraints

Key insight from the design document:
"Change the utility, change the universe."

- Log utility -> house mentality, slow compounding
- Target utility -> smart YOLO, maximize P(hitting target)
"""

from typing import Protocol

import polars as pl


class Utility(Protocol):
    """Abstract utility function.

    Different utility functions encode different risk preferences:
    - Log utility: maximize long-run growth (Kelly criterion)
    - Target utility: maximize probability of hitting a wealth target
    - Power utility: constant relative risk aversion
    - Exponential utility: constant absolute risk aversion
    """

    def value(self, wealth_path: pl.Series) -> float:
        """Compute utility of a wealth path.

        Args:
            wealth_path: Series of wealth values over time

        Returns:
            Utility value (higher is better)
        """
        ...


class LogUtility:
    """Log-wealth maximization (Kelly criterion).

    This is the "house always wins" objective:
    - Maximize E[log(W_T)]
    - Leads to fractional Kelly sizing
    - Optimizes long-run growth rate
    - Penalizes ruin heavily

    Use this when:
    - You have infinite horizon
    - You want to minimize risk of ruin
    - You care about compounding over many trades
    """

    def value(self, wealth_path: pl.Series) -> float:
        """Compute expected log wealth."""
        # Add small epsilon to avoid log(0)
        log_wealth = (wealth_path + 1e-10).log()
        mean_val = log_wealth.mean()

        if mean_val is None:
            return float('-inf')

        # Handle potential non-numeric types by converting to float
        if isinstance(mean_val, (int, float)):
            return float(mean_val)

        # For any other type, convert to physical representation
        return float(pl.Series([mean_val]).to_physical().item())


class TargetUtility:
    """Target-hitting utility.

    Maximize probability of hitting a target wealth level.
    This is NOT "house mentality" - it's optimized for sprint, not marathon.

    Use this when:
    - You have a specific wealth target
    - You're willing to risk ruin for higher upside
    - You can recycle capital if you fail (cheap ruin)

    This encodes: "I don't care about most outcomes, I want to maximize
    the probability of hitting my target."
    """

    def __init__(self, target: float, *, threshold_prob: float = 0.5) -> None:
        """Initialize target utility.

        Args:
            target: Target wealth level
            threshold_prob: Minimum probability threshold for "success"
        """
        self.target = target
        self.threshold_prob = threshold_prob

    def value(self, wealth_path: pl.Series) -> float:
        """Compute probability of hitting target."""
        above_target = wealth_path >= self.target
        mean_val = above_target.mean()

        if mean_val is None:
            prob_above = 0.0
        elif isinstance(mean_val, (int, float)):
            prob_above = float(mean_val)
        else:
            # For any other type, convert to physical representation
            prob_above = float(pl.Series([mean_val]).to_physical().item())

        # Return probability if above threshold, else large penalty
        if prob_above >= self.threshold_prob:
            return prob_above
        # Smooth penalty below threshold
        return -(1.0 / (prob_above + 1e-6))


def fractional_kelly(
    edge: float,
    variance: float,
    *,
    fraction: float = 0.25,
) -> float:
    """Fractional Kelly sizing with Gaussian approximation.

    Full Kelly: f* = μ/σ² where μ=edge, σ²=variance
    This gives maximum growth rate but can have large drawdowns.

    Fractional Kelly: f = fraction * f*
    Reduces volatility at the cost of slower growth.

    Common fractions:
    - 0.5 (half Kelly): reduces volatility by ~50%, growth by ~25%
    - 0.25 (quarter Kelly): very conservative, smooth equity curve
    - 1.0 (full Kelly): maximum growth, high volatility

    Args:
        edge: Expected excess return (μ)
        variance: Return variance (σ²)
        fraction: Kelly fraction to use (default: 0.25 for safety)

    Returns:
        Position size as fraction of capital [0, 1]
    """
    if variance <= 0 or edge <= 0:
        return 0.0

    kelly_full = edge / variance

    # Clamp to [0, 1] and apply fraction
    return max(0.0, min(1.0, fraction * kelly_full))


def kelly_with_ruin(
    edge: float,
    variance: float,
    *,
    max_drawdown: float = 0.20,
    kelly_fraction: float = 0.5,
) -> float:
    """Kelly sizing with hard drawdown constraint.

    This adjusts Kelly sizing to respect a maximum drawdown tolerance.
    Uses simplified VaR approximation.

    Args:
        edge: Expected excess return
        variance: Return variance
        max_drawdown: Maximum tolerable drawdown (default: 20%)
        kelly_fraction: Base Kelly fraction before drawdown adjustment

    Returns:
        Risk-adjusted position size as fraction of capital
    """
    base_size = fractional_kelly(edge, variance, fraction=kelly_fraction)

    if base_size <= 0:
        return 0.0

    # Approximate expected drawdown using VaR at 99th percentile
    # Z-score for 99th percentile: ~2.33
    z_score = 2.33
    volatility = variance**0.5
    expected_dd = z_score * volatility * base_size

    # If expected drawdown exceeds tolerance, scale down
    if expected_dd > max_drawdown:
        scale_factor = max_drawdown / expected_dd
        return base_size * scale_factor

    return base_size


def optimal_target_size(
    edge: float,
    variance: float,
    current_wealth: float,
    target_wealth: float,
    *,
    max_leverage: float = 1.0,
) -> float:
    """Optimal sizing for target-hitting objective.

    When optimizing P(W_T >= K) rather than E[log W], the optimal strategy
    is generally MORE aggressive than Kelly, accepting high ruin probability
    to maximize target-hitting probability.

    This is a simplified heuristic. True optimization requires solving
    a dynamic program, but this provides reasonable approximation.

    Args:
        edge: Expected excess return
        variance: Return variance
        current_wealth: Current wealth level
        target_wealth: Target wealth level
        max_leverage: Maximum leverage allowed

    Returns:
        Optimal position size (can be > 1.0 if leverage allowed)
    """
    if edge <= 0 or variance <= 0 or target_wealth <= current_wealth:
        return 0.0

    # Ratio of target to current
    wealth_ratio = target_wealth / current_wealth

    # Log of ratio gives required growth
    required_growth = pl.Series([wealth_ratio]).log().item()

    # Heuristic: scale Kelly by required growth factor
    # More aggressive when target is farther away
    base_kelly = edge / variance
    growth_multiplier = min(required_growth / edge, 3.0)  # cap at 3x

    optimal = base_kelly * growth_multiplier

    # Respect leverage limits
    return max(0.0, min(max_leverage, optimal))


def compute_sharpe(returns: pl.Series) -> float:
    """Compute Sharpe ratio from returns series.

    Args:
        returns: Series of returns

    Returns:
        Sharpe ratio (mean / std)
    """
    mean_val = returns.mean()
    std_val = returns.std()

    # Handle mean value
    if mean_val is None:
        mean_ret = 0.0
    elif isinstance(mean_val, (int, float)):
        mean_ret = float(mean_val)
    else:
        mean_ret = float(pl.Series([mean_val]).to_physical().item())

    # Handle std value
    if std_val is None:
        std_ret = 0.0
    elif isinstance(std_val, (int, float)):
        std_ret = float(std_val)
    else:
        std_ret = float(pl.Series([std_val]).to_physical().item())

    if std_ret <= 0:
        return 0.0

    return mean_ret / std_ret


def compute_kelly_from_sharpe(sharpe: float, *, fraction: float = 0.25) -> float:
    """Convert Sharpe ratio to Kelly position size.

    For Gaussian returns, Kelly fraction ≈ Sharpe ratio.
    This is a convenient shortcut when you have Sharpe estimate.

    Args:
        sharpe: Sharpe ratio estimate
        fraction: Kelly fraction to apply

    Returns:
        Position size as fraction of capital
    """
    return max(0.0, min(1.0, fraction * sharpe))
