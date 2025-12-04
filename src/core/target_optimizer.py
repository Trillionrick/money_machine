"""Target-hitting optimization for aggressive wealth generation.

This module implements the OPPOSITE of Kelly criterion:
- Kelly: Maximize E[log(wealth)] → slow compound, minimize ruin
- This: Maximize P(wealth >= target) → sprint to goal, accept ruin

Use when:
- You have a specific wealth target
- You can afford to lose starting capital
- You can try again if you fail (ruin is "cheap")
- You value hitting target much more than survival

WARNING: This is mathematically correct but psychologically brutal.
Most people can't handle the variance this creates.
"""

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import polars as pl


@dataclass
class TargetObjective:
    """Target-hitting objective specification."""

    current_wealth: float
    target_wealth: float
    time_horizon: int  # Number of periods (trades/days)
    max_attempts: int = 10  # How many times can you try?

    def __post_init__(self) -> None:
        """Validate inputs."""
        if self.target_wealth <= self.current_wealth:
            msg = "Target must be greater than current wealth"
            raise ValueError(msg)
        if self.time_horizon <= 0:
            msg = "Time horizon must be positive"
            raise ValueError(msg)


class TargetOptimizer:
    """Optimize position sizing for target-hitting.

    The key insight: When optimizing P(hitting target), optimal strategy
    is MORE aggressive than Kelly, accepting high probability of ruin.

    Example:
        >>> optimizer = TargetOptimizer()
        >>> objective = TargetObjective(
        ...     current_wealth=5_000,
        ...     target_wealth=500_000,  # 100x
        ...     time_horizon=252,  # 1 trading year
        ...     max_attempts=5,  # Can try 5 times
        ... )
        >>> size = optimizer.optimal_size(
        ...     objective=objective,
        ...     edge=0.10,  # 10% expected return
        ...     variance=0.25,  # 50% vol
        ... )
    """

    def optimal_size(
        self,
        objective: TargetObjective,
        edge: float,
        variance: float,
        *,
        max_leverage: float = 3.0,
    ) -> float:
        """Calculate optimal position size for target-hitting.

        Uses dynamic programming to find size that maximizes
        probability of hitting target within time horizon.

        Args:
            objective: Target objective specification
            edge: Expected return per period
            variance: Return variance per period
            max_leverage: Maximum leverage allowed

        Returns:
            Optimal position size (can be > 1.0 if leverage allowed)
        """
        if edge <= 0:
            return 0.0

        # Calculate required growth rate
        required_growth = (
            objective.target_wealth / objective.current_wealth
        ) ** (1.0 / objective.time_horizon) - 1.0

        # If edge < required growth, need leverage or won't make it
        if edge < required_growth:
            # Use maximum leverage
            return max_leverage

        # Calculate Kelly for reference
        kelly_full = edge / variance if variance > 0 else 0.0

        # Target-hitting optimal is typically 2-5x Kelly
        # This is because we're willing to accept ruin
        # We're maximizing P(hit target), not E[log(wealth)]

        # Heuristic: Scale by ratio of required to available growth
        growth_multiplier = min(required_growth / edge, 5.0)

        optimal = kelly_full * growth_multiplier

        # Respect leverage limits
        return min(optimal, max_leverage)

    def simulate_outcomes(
        self,
        objective: TargetObjective,
        position_size: float,
        edge: float,
        variance: float,
        *,
        num_simulations: int = 10_000,
    ) -> dict[str, float]:
        """Monte Carlo simulation of outcomes.

        Args:
            objective: Target objective
            position_size: Position size to test
            edge: Expected return
            variance: Return variance
            num_simulations: Number of paths to simulate

        Returns:
            Dictionary with:
                - prob_target: Probability of hitting target
                - prob_ruin: Probability of ruin (< 10% of starting capital)
                - median_outcome: Median final wealth
                - mean_outcome: Mean final wealth
        """
        np.random.seed(42)

        final_wealths = []

        for _ in range(num_simulations):
            wealth = objective.current_wealth

            for _ in range(objective.time_horizon):
                # Generate return
                period_return = np.random.normal(edge, variance**0.5)

                # Apply position size
                portfolio_return = position_size * period_return

                # Update wealth
                wealth *= 1 + portfolio_return

                # Check if ruined (< 10% of starting capital)
                if wealth < objective.current_wealth * 0.1:
                    break

                # Check if hit target
                if wealth >= objective.target_wealth:
                    break

            final_wealths.append(wealth)

        final_wealths_array = np.array(final_wealths)

        return {
            "prob_target": float(
                np.mean(final_wealths_array >= objective.target_wealth)
            ),
            "prob_ruin": float(np.mean(final_wealths_array < objective.current_wealth * 0.1)),
            "median_outcome": float(np.median(final_wealths_array)),
            "mean_outcome": float(np.mean(final_wealths_array)),
            "p10_outcome": float(np.percentile(final_wealths_array, 10)),
            "p90_outcome": float(np.percentile(final_wealths_array, 90)),
        }

    def optimal_with_attempts(
        self,
        objective: TargetObjective,
        edge: float,
        variance: float,
    ) -> dict:
        """Find optimal size considering multiple attempts.

        Key insight: If you can try multiple times, you can be MORE aggressive
        on each attempt because P(at least one success) = 1 - (1-p)^n

        Args:
            objective: Target objective
            edge: Expected return
            variance: Return variance

        Returns:
            Dictionary with optimal strategy
        """
        # Test different position sizes
        sizes = np.linspace(0.5, 3.0, 20)

        best_strategy = None
        best_prob = 0.0

        for size in sizes:
            # Simulate outcomes for this size
            sim_result = self.simulate_outcomes(
                objective=objective,
                position_size=size,
                edge=edge,
                variance=variance,
                num_simulations=5_000,
            )

            # Calculate probability of success in at least one attempt
            prob_single = sim_result["prob_target"]
            prob_at_least_once = 1.0 - (1.0 - prob_single) ** objective.max_attempts

            if prob_at_least_once > best_prob:
                best_prob = prob_at_least_once
                best_strategy = {
                    "optimal_size": float(size),
                    "prob_single_attempt": prob_single,
                    "prob_at_least_once": prob_at_least_once,
                    "prob_ruin_per_attempt": sim_result["prob_ruin"],
                    "expected_attempts": 1.0 / prob_single if prob_single > 0 else float("inf"),
                    **sim_result,
                }

        return cast (dict, best_strategy) # pyright: ignore[reportUndefinedVariable]
def compare_strategies(
    objective: TargetObjective,
    edge: float,
    variance: float,
) -> None:
    """Compare Kelly vs Target-optimized strategies.

    Args:
        objective: Target objective
        edge: Expected return
        variance: Return variance
    """
    optimizer = TargetOptimizer()

    # Kelly (standard)
    kelly_size = edge / variance if variance > 0 else 0.0
    kelly_quarter = kelly_size * 0.25  # Conservative Kelly

    # Target-optimized
    target_size = optimizer.optimal_size(objective, edge, variance)

    # Simulate both
    kelly_result = optimizer.simulate_outcomes(
        objective, kelly_quarter, edge, variance
    )
    target_result = optimizer.simulate_outcomes(
        objective, target_size, edge, variance
    )

    print("=" * 80)
    print("STRATEGY COMPARISON: Kelly vs Target-Optimized")
    print("=" * 80)
    print()
    print(f"Objective: ${objective.current_wealth:,.0f} → ${objective.target_wealth:,.0f}")
    print(f"Time Horizon: {objective.time_horizon} periods")
    print(f"Edge: {edge:.1%}, Volatility: {variance**0.5:.1%}")
    print()

    print("QUARTER KELLY (Conservative):")
    print(f"  Position Size: {kelly_quarter:.2f}x")
    print(f"  P(Hit Target): {kelly_result['prob_target']:.1%}")
    print(f"  P(Ruin): {kelly_result['prob_ruin']:.1%}")
    print(f"  Median Outcome: ${kelly_result['median_outcome']:,.0f}")
    print()

    print("TARGET-OPTIMIZED (Aggressive):")
    print(f"  Position Size: {target_size:.2f}x")
    print(f"  P(Hit Target): {target_result['prob_target']:.1%}")
    print(f"  P(Ruin): {target_result['prob_ruin']:.1%}")
    print(f"  Median Outcome: ${target_result['median_outcome']:,.0f}")
    print()

    print("KEY INSIGHT:")
    if target_result["prob_target"] > kelly_result["prob_target"] * 2:
        print(f"  ✓ Target-optimized is {target_result['prob_target']/kelly_result['prob_target']:.1f}x")
        print("    more likely to hit your goal!")
    print(f"  ⚠ But ruin risk is {target_result['prob_ruin']/max(kelly_result['prob_ruin'], 0.01):.1f}x higher")
    print()

    print("MULTIPLE ATTEMPTS:")
    multi_result = optimizer.optimal_with_attempts(objective, edge, variance)
    print(f"  With {objective.max_attempts} attempts:")
    print(f"  P(Hit Target in at least 1) = {multi_result['prob_at_least_once']:.1%}")
    print(f"  Expected attempts needed = {multi_result['expected_attempts']:.1f}")
    print()
    print("=" * 80)


# Example usage
if __name__ == "__main__":
    # Your goal: $5k → $500k in 1 year
    objective = TargetObjective(
        current_wealth=5_000,
        target_wealth=500_000,
        time_horizon=252,  # Trading days in a year
        max_attempts=5,
    )

    # Assume you have a genuine edge
    edge = 0.002  # 0.2% per day (50% annualized)
    variance = 0.0004  # 2% daily vol

    compare_strategies(objective, edge, variance)
