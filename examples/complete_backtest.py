"""Complete backtest example demonstrating the entire system.

This example shows:
1. Loading market data
2. Creating a strategy with risk management
3. Running a backtest
4. Analyzing performance
5. Displaying results
"""


import polars as pl
from src.research.analytics import PerformanceAnalyzer
from src.research.simulator import Simulator, SimulatorConfig
from src.research.strategies import MomentumConfig, MomentumStrategy


def create_sample_data() -> dict[str, pl.DataFrame]:
    """Create sample market data for testing.

    In production, you would load this from your DataStore or API.
    """
    # Create synthetic data for 3 symbols
    timestamps = list(range(1000, 2000))  # 1000 time periods

    data = {}

    for symbol in ["AAPL", "GOOGL", "MSFT"]:
        # Generate random walk prices
        import random

        random.seed(hash(symbol))

        prices = []
        price = 100.0

        for _ in timestamps:
            # Random walk with slight upward drift
            change = random.gauss(0.001, 0.02)
            price *= 1 + change
            prices.append(price)

        # Create OHLCV data
        data[symbol] = pl.DataFrame(
            {
                "timestamp": timestamps,
                "open": [p * 0.99 for p in prices],
                "high": [p * 1.01 for p in prices],
                "low": [p * 0.98 for p in prices],
                "close": prices,
                "volume": [1_000_000.0] * len(timestamps),
            }
        )

    return data


def main() -> None:
    """Run complete backtest example."""
    print("=" * 80)
    print("TRADING BOT - COMPLETE BACKTEST EXAMPLE")
    print("=" * 80)
    print()

    # 1. Create sample data
    print("1. Loading market data...")
    market_data = create_sample_data()
    symbols = list(market_data.keys())
    print(f"   Loaded data for {len(symbols)} symbols: {', '.join(symbols)}")
    print()

    # 2. Create strategy with risk management
    print("2. Initializing strategy...")

    # Configure momentum strategy
    strategy = MomentumStrategy(
        symbols=symbols,
        config=MomentumConfig(
            lookback_periods=20,
            entry_threshold=1.5,
            exit_threshold=0.5,
            kelly_fraction=0.25,
            max_drawdown=0.15,
        ),
    )
    print("   Strategy: Momentum with adaptive Kelly sizing")
    print()

    # 3. Set up simulator
    print("3. Configuring simulator...")
    simulator = Simulator(
        initial_capital=100_000.0,
        config=SimulatorConfig(
            base_slippage_bps=5.0,
            slippage_exponent=0.5,
            maker_fee_bps=1.0,
            taker_fee_bps=5.0,
        ),
    )
    print("   Initial capital: $100,000")
    print("   Fees: 1 bps maker, 5 bps taker")
    print()

    # 4. Run backtest
    print("4. Running backtest...")
    print("   This may take a moment...")

    result = simulator.run_backtest(
        policy=strategy,
        market_data=market_data,
    )

    print("   ✓ Backtest complete!")
    print(f"   - Trades executed: {len(result.trades)}")
    print(f"   - Final equity: ${result.final_portfolio.equity:,.2f}")
    print()

    # 5. Analyze performance
    print("5. Analyzing performance...")
    analyzer = PerformanceAnalyzer(risk_free_rate=0.02)

    metrics = analyzer.calculate_metrics(
        equity_curve=result.equity_curve,
        trades=result.trades,
    )
    print()

    # 6. Display results
    analyzer.print_report(metrics)
    print()

    # 7. Key insights
    print("KEY INSIGHTS")
    print("=" * 60)

    if metrics.sharpe_ratio > 1.5:
        print("  ✓ Excellent Sharpe ratio - strategy shows strong risk-adjusted returns")
    elif metrics.sharpe_ratio > 1.0:
        print("  ✓ Good Sharpe ratio - strategy is profitable with acceptable risk")
    else:
        print("  ⚠ Low Sharpe ratio - strategy needs improvement")

    if metrics.max_drawdown_pct < 15:
        print("  ✓ Drawdown well controlled - risk management working")
    elif metrics.max_drawdown_pct < 25:
        print("  ⚠ Moderate drawdown - consider tighter risk limits")
    else:
        print("  ⚠ High drawdown - risk management needs attention")

    if metrics.win_rate_pct > 55:
        print(f"  ✓ Win rate {metrics.win_rate_pct:.1f}% - good trade selection")
    else:
        print(f"  ⚠ Win rate {metrics.win_rate_pct:.1f}% - review entry/exit logic")

    print()
    print("=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print()
    print("1. Review the performance metrics above")
    print("2. Adjust strategy parameters if needed")
    print("3. Run more backtests with different configurations")
    print("4. Test with paper trading (see examples/paper_trading.py)")
    print("5. Only go live after thorough validation")
    print()
    print("Remember: Past performance doesn't guarantee future results!")
    print("=" * 80)


if __name__ == "__main__":
    main()
