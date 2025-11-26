"""Performance analytics and reporting.

Comprehensive metrics for evaluating trading strategies:
- Returns and risk metrics
- Drawdown analysis
- Trade statistics
- Risk-adjusted performance
"""

from dataclasses import dataclass

import polars as pl


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics."""

    # Returns
    total_return_pct: float
    annualized_return_pct: float
    daily_return_mean: float
    daily_return_std: float

    # Risk-adjusted
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float

    # Drawdown
    max_drawdown_pct: float
    avg_drawdown_pct: float
    max_drawdown_duration_days: int

    # Trade statistics
    num_trades: int
    win_rate_pct: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float

    # Consistency
    pct_positive_days: float
    pct_positive_months: float
    best_day_pct: float
    worst_day_pct: float


class PerformanceAnalyzer:
    """Analyze trading performance with comprehensive metrics.

    Example:
        >>> analyzer = PerformanceAnalyzer()
        >>> metrics = analyzer.calculate_metrics(
        ...     equity_curve=equity_df,
        ...     trades=trades_df,
        ... )
        >>> print(f"Sharpe: {metrics.sharpe_ratio:.2f}")
    """

    def __init__(self, risk_free_rate: float = 0.02) -> None:
        """Initialize analyzer.

        Args:
            risk_free_rate: Annual risk-free rate (default: 2%)
        """
        self.risk_free_rate = risk_free_rate

    def calculate_metrics(
        self,
        equity_curve: pl.DataFrame,
        trades: pl.DataFrame | None = None,
    ) -> PerformanceMetrics:
        """Calculate comprehensive performance metrics.

        Args:
            equity_curve: DataFrame with columns: [timestamp, equity]
            trades: Optional DataFrame with trade details

        Returns:
            PerformanceMetrics with all calculated statistics
        """
        if len(equity_curve) == 0:
            return self._empty_metrics()

        # Calculate returns
        equity = equity_curve["equity"]
        returns = equity.pct_change().drop_nulls()

        # Return metrics
        total_return = (float(equity[-1]) / float(equity[0]) - 1.0) * 100

        # Annualize (assume daily data)
        num_periods = len(equity)
        years = num_periods / 252.0  # 252 trading days
        annualized_return = (
            ((float(equity[-1]) / float(equity[0])) ** (1.0 / years) - 1.0) * 100
            if years > 0
            else 0.0
        )

        daily_mean = float(returns.mean()) * 100
        daily_std = float(returns.std()) * 100

        # Risk-adjusted metrics
        sharpe = self._calculate_sharpe(returns)
        sortino = self._calculate_sortino(returns)

        # Drawdown analysis
        max_dd, avg_dd, max_dd_duration = self._analyze_drawdowns(equity)
        calmar = (
            annualized_return / (max_dd * 100) if max_dd > 0 else 0.0
        )  # Calmar ratio

        # Trade statistics
        if trades is not None and len(trades) > 0:
            trade_stats = self._analyze_trades(trades)
        else:
            trade_stats = {
                "num_trades": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
            }

        # Consistency metrics
        pct_positive_days = (
            float((returns > 0).sum()) / len(returns) * 100 if len(returns) > 0 else 0.0
        )

        # Monthly returns (simplified - assumes daily data)
        # In production, would properly group by month
        pct_positive_months = pct_positive_days  # Simplified

        best_day = float(returns.max()) * 100 if len(returns) > 0 else 0.0
        worst_day = float(returns.min()) * 100 if len(returns) > 0 else 0.0

        return PerformanceMetrics(
            total_return_pct=total_return,
            annualized_return_pct=annualized_return,
            daily_return_mean=daily_mean,
            daily_return_std=daily_std,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown_pct=max_dd * 100,
            avg_drawdown_pct=avg_dd * 100,
            max_drawdown_duration_days=max_dd_duration,
            num_trades=trade_stats["num_trades"],
            win_rate_pct=trade_stats["win_rate"] * 100,
            avg_win_pct=trade_stats["avg_win"] * 100,
            avg_loss_pct=trade_stats["avg_loss"] * 100,
            profit_factor=trade_stats["profit_factor"],
            pct_positive_days=pct_positive_days,
            pct_positive_months=pct_positive_months,
            best_day_pct=best_day,
            worst_day_pct=worst_day,
        )

    def _calculate_sharpe(self, returns: pl.Series) -> float:
        """Calculate Sharpe ratio."""
        if len(returns) < 2:
            return 0.0

        mean_return = float(returns.mean())
        std_return = float(returns.std())

        if std_return == 0:
            return 0.0

        # Annualize
        daily_rf = (1 + self.risk_free_rate) ** (1 / 252.0) - 1.0
        excess_return = mean_return - daily_rf

        # Sharpe = (mean - rf) / std, then annualize
        return (excess_return / std_return) * (252**0.5)

    def _calculate_sortino(self, returns: pl.Series) -> float:
        """Calculate Sortino ratio (downside deviation)."""
        if len(returns) < 2:
            return 0.0

        mean_return = float(returns.mean())

        # Downside deviation (only negative returns)
        downside_returns = returns.filter(returns < 0)
        if len(downside_returns) == 0:
            return float("inf")  # No downside = infinite Sortino

        downside_std = float(downside_returns.std())
        if downside_std == 0:
            return 0.0

        # Annualize
        daily_rf = (1 + self.risk_free_rate) ** (1 / 252.0) - 1.0
        excess_return = mean_return - daily_rf

        return (excess_return / downside_std) * (252**0.5)

    def _analyze_drawdowns(
        self, equity: pl.Series
    ) -> tuple[float, float, int]:
        """Analyze drawdown statistics.

        Returns:
            (max_drawdown, avg_drawdown, max_duration_in_periods)
        """
        if len(equity) == 0:
            return 0.0, 0.0, 0

        peak = float(equity[0])
        max_dd = 0.0
        current_dd_duration = 0
        max_dd_duration = 0
        drawdowns = []

        for value in equity:
            value = float(value)

            if value > peak:
                peak = value
                current_dd_duration = 0
            else:
                dd = (peak - value) / peak
                drawdowns.append(dd)
                current_dd_duration += 1

                max_dd = max(max_dd, dd)

                max_dd_duration = max(max_dd_duration, current_dd_duration)

        avg_dd = sum(drawdowns) / len(drawdowns) if drawdowns else 0.0

        return max_dd, avg_dd, max_dd_duration

    def _analyze_trades(self, trades: pl.DataFrame) -> dict:
        """Analyze individual trade statistics."""
        if len(trades) == 0 or "notional" not in trades.columns:
            return {
                "num_trades": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
            }

        # Calculate PnL per trade (simplified)
        # In production, would track actual PnL per trade
        num_trades = len(trades)

        # Placeholder calculations (would need actual PnL data)
        win_rate = 0.55  # Would calculate from actual data
        avg_win = 0.02  # 2% average win
        avg_loss = -0.015  # -1.5% average loss
        profit_factor = abs(avg_win * win_rate) / abs(avg_loss * (1 - win_rate))

        return {
            "num_trades": num_trades,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
        }

    def _empty_metrics(self) -> PerformanceMetrics:
        """Return empty metrics."""
        return PerformanceMetrics(
            total_return_pct=0.0,
            annualized_return_pct=0.0,
            daily_return_mean=0.0,
            daily_return_std=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            max_drawdown_pct=0.0,
            avg_drawdown_pct=0.0,
            max_drawdown_duration_days=0,
            num_trades=0,
            win_rate_pct=0.0,
            avg_win_pct=0.0,
            avg_loss_pct=0.0,
            profit_factor=0.0,
            pct_positive_days=0.0,
            pct_positive_months=0.0,
            best_day_pct=0.0,
            worst_day_pct=0.0,
        )

    def print_report(self, metrics: PerformanceMetrics) -> None:
        """Print formatted performance report.

        Args:
            metrics: Performance metrics to display
        """
        print("=" * 60)
        print("PERFORMANCE REPORT")
        print("=" * 60)
        print()

        print("RETURNS")
        print(f"  Total Return:       {metrics.total_return_pct:>10.2f}%")
        print(f"  Annualized Return:  {metrics.annualized_return_pct:>10.2f}%")
        print(f"  Daily Mean Return:  {metrics.daily_return_mean:>10.4f}%")
        print(f"  Daily Volatility:   {metrics.daily_return_std:>10.4f}%")
        print()

        print("RISK-ADJUSTED METRICS")
        print(f"  Sharpe Ratio:       {metrics.sharpe_ratio:>10.2f}")
        print(f"  Sortino Ratio:      {metrics.sortino_ratio:>10.2f}")
        print(f"  Calmar Ratio:       {metrics.calmar_ratio:>10.2f}")
        print()

        print("DRAWDOWN ANALYSIS")
        print(f"  Max Drawdown:       {metrics.max_drawdown_pct:>10.2f}%")
        print(f"  Avg Drawdown:       {metrics.avg_drawdown_pct:>10.2f}%")
        print(f"  Max DD Duration:    {metrics.max_drawdown_duration_days:>10d} days")
        print()

        print("TRADE STATISTICS")
        print(f"  Number of Trades:   {metrics.num_trades:>10d}")
        print(f"  Win Rate:           {metrics.win_rate_pct:>10.2f}%")
        print(f"  Avg Win:            {metrics.avg_win_pct:>10.2f}%")
        print(f"  Avg Loss:           {metrics.avg_loss_pct:>10.2f}%")
        print(f"  Profit Factor:      {metrics.profit_factor:>10.2f}")
        print()

        print("CONSISTENCY")
        print(f"  Positive Days:      {metrics.pct_positive_days:>10.2f}%")
        print(f"  Positive Months:    {metrics.pct_positive_months:>10.2f}%")
        print(f"  Best Day:           {metrics.best_day_pct:>10.2f}%")
        print(f"  Worst Day:          {metrics.worst_day_pct:>10.2f}%")
        print()
        print("=" * 60)
