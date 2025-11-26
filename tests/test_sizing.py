"""Tests for position sizing functions."""

import polars as pl
import pytest
from src.core.sizing import (
    LogUtility,
    TargetUtility,
    compute_sharpe,
    fractional_kelly,
    kelly_with_ruin,
    optimal_target_size,
)


class TestFractionalKelly:
    """Tests for fractional Kelly sizing."""

    def test_positive_edge_returns_size(self) -> None:
        """Test that positive edge returns a position size."""
        size = fractional_kelly(edge=0.1, variance=0.04, fraction=0.5)
        assert size > 0
        assert size <= 1.0

    def test_zero_edge_returns_zero(self) -> None:
        """Test that zero edge returns zero size."""
        size = fractional_kelly(edge=0.0, variance=0.04)
        assert size == 0.0

    def test_negative_edge_returns_zero(self) -> None:
        """Test that negative edge returns zero size."""
        size = fractional_kelly(edge=-0.1, variance=0.04)
        assert size == 0.0

    def test_zero_variance_returns_zero(self) -> None:
        """Test that zero variance returns zero size."""
        size = fractional_kelly(edge=0.1, variance=0.0)
        assert size == 0.0

    def test_full_kelly_formula(self) -> None:
        """Test Kelly formula: f* = μ/σ²."""
        edge = 0.2
        variance = 0.04
        expected_full = edge / variance  # 5.0, but clamped to 1.0
        size = fractional_kelly(edge=edge, variance=variance, fraction=1.0)
        assert size == min(1.0, expected_full)

    def test_quarter_kelly_reduces_size(self) -> None:
        """Test that quarter Kelly is smaller than half Kelly."""
        edge, variance = 0.1, 0.04
        quarter = fractional_kelly(edge, variance, fraction=0.25)
        half = fractional_kelly(edge, variance, fraction=0.5)
        assert quarter < half


class TestKellyWithRuin:
    """Tests for Kelly with drawdown constraint."""

    def test_respects_max_drawdown(self) -> None:
        """Test that sizing respects max drawdown."""
        # High volatility, low max DD should result in smaller size
        size = kelly_with_ruin(edge=0.1, variance=1.0, max_drawdown=0.05)
        assert 0 <= size <= 0.1  # Should be quite small

    def test_loose_constraint_allows_larger_size(self) -> None:
        """Test that loose drawdown allows larger sizing."""
        small = kelly_with_ruin(edge=0.1, variance=0.04, max_drawdown=0.05)
        large = kelly_with_ruin(edge=0.1, variance=0.04, max_drawdown=0.30)
        assert large >= small


class TestTargetUtility:
    """Tests for target-hitting utility."""

    def test_above_target_positive(self) -> None:
        """Test utility is positive when above target."""
        util = TargetUtility(target=1000.0)
        wealth = pl.Series([1100.0, 1200.0, 1050.0])
        value = util.value(wealth)
        assert value > 0

    def test_below_target_negative(self) -> None:
        """Test utility is negative when below target."""
        util = TargetUtility(target=1000.0)
        wealth = pl.Series([900.0, 800.0, 950.0])
        value = util.value(wealth)
        assert value < 0

    def test_higher_prob_higher_utility(self) -> None:
        """Test that higher probability gives higher utility."""
        util = TargetUtility(target=1000.0)
        low_prob = pl.Series([900.0, 950.0, 1100.0])  # 1/3 above
        high_prob = pl.Series([1100.0, 1200.0, 1050.0])  # 3/3 above

        assert util.value(high_prob) > util.value(low_prob)


class TestLogUtility:
    """Tests for log utility."""

    def test_higher_wealth_higher_utility(self) -> None:
        """Test that higher wealth gives higher utility."""
        util = LogUtility()
        low_wealth = pl.Series([100.0, 110.0, 120.0])
        high_wealth = pl.Series([1000.0, 1100.0, 1200.0])

        assert util.value(high_wealth) > util.value(low_wealth)

    def test_handles_zero_wealth(self) -> None:
        """Test that zero wealth doesn't cause errors."""
        util = LogUtility()
        wealth = pl.Series([0.0, 100.0, 200.0])
        value = util.value(wealth)
        assert not pl.Series([value]).is_nan().any()


class TestOptimalTargetSize:
    """Tests for target-hitting optimal sizing."""

    def test_returns_zero_for_no_edge(self) -> None:
        """Test zero sizing with no edge."""
        size = optimal_target_size(
            edge=0.0,
            variance=0.04,
            current_wealth=1000.0,
            target_wealth=10000.0,
        )
        assert size == 0.0

    def test_larger_target_larger_size(self) -> None:
        """Test that farther targets lead to more aggressive sizing."""
        # Use targets that won't hit the 3x cap
        small_target = optimal_target_size(
            edge=0.2,
            variance=0.04,
            current_wealth=1000.0,
            target_wealth=1100.0,  # 10% gain
            max_leverage=10.0,
        )
        large_target = optimal_target_size(
            edge=0.2,
            variance=0.04,
            current_wealth=1000.0,
            target_wealth=1300.0,  # 30% gain
            max_leverage=10.0,
        )
        assert large_target >= small_target  # Allow equal or greater

    def test_respects_leverage_limit(self) -> None:
        """Test that sizing respects max leverage."""
        size = optimal_target_size(
            edge=0.5,
            variance=0.01,
            current_wealth=1000.0,
            target_wealth=100000.0,
            max_leverage=2.0,
        )
        assert size <= 2.0


class TestComputeSharpe:
    """Tests for Sharpe ratio calculation."""

    def test_positive_returns_positive_sharpe(self) -> None:
        """Test positive returns give positive Sharpe."""
        returns = pl.Series([0.01, 0.02, 0.015, 0.018])
        sharpe = compute_sharpe(returns)
        assert sharpe > 0

    def test_zero_returns_zero_sharpe(self) -> None:
        """Test zero returns give zero Sharpe."""
        returns = pl.Series([0.0, 0.0, 0.0, 0.0])
        sharpe = compute_sharpe(returns)
        assert sharpe == 0.0

    def test_higher_mean_higher_sharpe(self) -> None:
        """Test higher mean gives higher Sharpe (same vol)."""
        # Generate returns with different means but similar variance
        low = pl.Series([0.01, 0.02, 0.01, 0.02])
        high = pl.Series([0.05, 0.06, 0.05, 0.06])

        assert compute_sharpe(high) > compute_sharpe(low)


@pytest.mark.benchmark
def test_kelly_performance(benchmark: pytest.fixture) -> None:
    """Benchmark Kelly calculation performance."""

    def run_kelly() -> float:
        return fractional_kelly(edge=0.1, variance=0.04, fraction=0.25)

    result = benchmark(run_kelly)
    assert result > 0
