"""Compare multiple strategies side-by-side.

Demonstrates:
1. Market Making (house edge)
2. Momentum (trend following)
3. Statistical Arbitrage (mean reversion)
"""

import polars as pl
from src.research.analytics import PerformanceAnalyzer
from src.research.simulator import Simulator
from src.research.strategies import (
    MarketMakingConfig,
    MarketMakingStrategy,
    MomentumConfig,
    MomentumStrategy,
    PairsTradingStrategy,
    StatArbConfig,
)


def create_sample_data(num_periods: int = 1000) -> dict[str, pl.DataFrame]:
    """Create sample data with different characteristics."""
    import random

    timestamps = list(range(num_periods))
    data = {}

    # Trending asset (AAPL)
    random.seed(42)
    price = 100.0
    prices_aapl = []
    for _ in timestamps:
        price *= 1 + random.gauss(0.0005, 0.015)  # Positive drift
        prices_aapl.append(price)

    data["AAPL"] = pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": prices_aapl,
            "high": [p * 1.01 for p in prices_aapl],
            "low": [p * 0.99 for p in prices_aapl],
            "close": prices_aapl,
            "volume": [1_000_000.0] * len(timestamps),
        }
    )

    # Mean-reverting pair (GOOGL/MSFT)
    random.seed(43)
    base_ratio = 1.5
    googl_prices = []
    msft_prices = []

    for i in timestamps:
        # Create mean-reverting spread
        deviation = random.gauss(0, 0.05) + 0.1 * (i % 20 - 10) / 10
        ratio = base_ratio * (1 + deviation)

        msft_price = 100.0 + random.gauss(0, 5)
        googl_price = msft_price * ratio

        googl_prices.append(googl_price)
        msft_prices.append(msft_price)

    data["GOOGL"] = pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": googl_prices,
            "high": [p * 1.01 for p in googl_prices],
            "low": [p * 0.99 for p in googl_prices],
            "close": googl_prices,
            "volume": [500_000.0] * len(timestamps),
        }
    )

    data["MSFT"] = pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": msft_prices,
            "high": [p * 1.01 for p in msft_prices],
            "low": [p * 0.99 for p in msft_prices],
            "close": msft_prices,
            "volume": [500_000.0] * len(timestamps),
        }
    )

    return data


def main() -> None:
    """Compare strategies."""
    print("=" * 80)
    print("STRATEGY COMPARISON")
    print("=" * 80)
    print()

    # Create data
    print("Creating test data...")
    market_data = create_sample_data(1000)
    print()

    analyzer = PerformanceAnalyzer()
    results = []

    # Strategy 1: Market Making
    print("Testing Strategy 1: Market Making")
    print("-" * 80)

    strategy1 = MarketMakingStrategy(
        symbols=["AAPL", "GOOGL", "MSFT"],
        config=MarketMakingConfig(
            target_spread_bps=10.0,
            inventory_limit=10_000.0,
            quote_size_pct=0.05,
        ),
    )

    sim1 = Simulator(initial_capital=100_000.0)
    result1 = sim1.run_backtest(strategy1, market_data)
    metrics1 = analyzer.calculate_metrics(result1.equity_curve, result1.trades)

    print(f"  Sharpe Ratio: {metrics1.sharpe_ratio:.2f}")
    print(f"  Max Drawdown: {metrics1.max_drawdown_pct:.2f}%")
    print(f"  Total Return: {metrics1.total_return_pct:.2f}%")
    print(f"  # Trades: {metrics1.num_trades}")
    print()

    results.append(("Market Making", metrics1))

    # Strategy 2: Momentum
    print("Testing Strategy 2: Momentum")
    print("-" * 80)

    strategy2 = MomentumStrategy(
        symbols=["AAPL"],  # Use trending asset
        config=MomentumConfig(
            lookback_periods=20,
            entry_threshold=1.5,
            kelly_fraction=0.25,
        ),
    )

    sim2 = Simulator(initial_capital=100_000.0)
    result2 = sim2.run_backtest(strategy2, market_data)
    metrics2 = analyzer.calculate_metrics(result2.equity_curve, result2.trades)

    print(f"  Sharpe Ratio: {metrics2.sharpe_ratio:.2f}")
    print(f"  Max Drawdown: {metrics2.max_drawdown_pct:.2f}%")
    print(f"  Total Return: {metrics2.total_return_pct:.2f}%")
    print(f"  # Trades: {metrics2.num_trades}")
    print()

    results.append(("Momentum", metrics2))

    # Strategy 3: Statistical Arbitrage
    print("Testing Strategy 3: Pairs Trading (Stat Arb)")
    print("-" * 80)

    strategy3 = PairsTradingStrategy(
        pair=("GOOGL", "MSFT"),  # Use mean-reverting pair
        config=StatArbConfig(
            lookback_periods=60,
            entry_z_score=2.0,
            kelly_fraction=0.25,
        ),
    )

    sim3 = Simulator(initial_capital=100_000.0)
    result3 = sim3.run_backtest(strategy3, market_data)
    metrics3 = analyzer.calculate_metrics(result3.equity_curve, result3.trades)

    print(f"  Sharpe Ratio: {metrics3.sharpe_ratio:.2f}")
    print(f"  Max Drawdown: {metrics3.max_drawdown_pct:.2f}%")
    print(f"  Total Return: {metrics3.total_return_pct:.2f}%")
    print(f"  # Trades: {metrics3.num_trades}")
    print()

    results.append(("Pairs Trading", metrics3))

    # Summary comparison
    print("=" * 80)
    print("SUMMARY COMPARISON")
    print("=" * 80)
    print()
    print(f"{'Strategy':<20} {'Sharpe':<10} {'Return %':<12} {'Max DD %':<12} {'Trades':<10}")
    print("-" * 80)

    for name, metrics in results:
        print(
            f"{name:<20} {metrics.sharpe_ratio:<10.2f} "
            f"{metrics.total_return_pct:<12.2f} "
            f"{metrics.max_drawdown_pct:<12.2f} "
            f"{metrics.num_trades:<10.0f}"
        )

    print()
    print("=" * 80)
    print("INSIGHTS")
    print("=" * 80)
    print()
    print("Market Making:")
    print("  - 'House edge' strategy: earns spread on every transaction")
    print("  - High frequency, small wins")
    print("  - Structural edge from providing liquidity")
    print()
    print("Momentum:")
    print("  - 'Ride the trend' strategy: exploits behavioral under-reaction")
    print("  - Fewer trades, larger wins")
    print("  - Works best in trending markets")
    print()
    print("Pairs Trading:")
    print("  - 'Mean reversion' strategy: exploits temporary mispricings")
    print("  - Market neutral (hedged)")
    print("  - High win rate, controlled losses")
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()
