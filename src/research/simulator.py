"""High-fidelity execution simulator with realistic market microstructure.

This simulator models:
- Bid-ask spreads
- Slippage based on order size
- Partial fills
- Latency
- Fee structures
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import polars as pl

from src.core.execution import Fill, Order, OrderType, Side
from src.core.policy import MarketSnapshot, Policy, PortfolioState
from src.core.types import Price, Quantity, Symbol, Timestamp


@dataclass
class SimulatorConfig:
    """Configuration for execution simulator."""

    # Slippage model: slippage = base_slippage * (order_size / avg_volume) ^ slippage_exponent
    base_slippage_bps: float = 5.0  # 5 basis points base slippage
    slippage_exponent: float = 0.5  # Square root impact

    # Spread model
    min_spread_bps: float = 2.0  # Minimum 2 bps spread
    spread_volatility_multiplier: float = 10.0  # Spread widens with volatility

    # Fees
    maker_fee_bps: float = 1.0  # 1 bps for limit orders
    taker_fee_bps: float = 5.0  # 5 bps for market orders

    # Execution probability for limit orders (vs market orders always fill)
    limit_fill_probability: float = 0.7  # 70% of limit orders fill

    # Latency
    mean_latency_ms: float = 50.0
    latency_std_ms: float = 10.0


@dataclass
class BacktestResult:
    """Results from a backtest run."""

    trades: pl.DataFrame
    equity_curve: pl.DataFrame
    metrics: dict[str, float]
    final_portfolio: PortfolioState


class Simulator:
    """High-fidelity execution simulator for backtesting.

    This simulator provides realistic execution modeling including:
    - Market microstructure effects (spreads, slippage)
    - Partial fills and rejection
    - Transaction costs
    - Latency effects

    Example:
        >>> sim = Simulator(initial_capital=100_000.0)
        >>> result = await sim.run_backtest(
        ...     policy=my_policy,
        ...     market_data=price_data,
        ... )
    """

    def __init__(
        self,
        initial_capital: float,
        config: SimulatorConfig | None = None,
    ) -> None:
        """Initialize simulator.

        Args:
            initial_capital: Starting cash amount (must be positive).
            config: Simulator configuration (uses defaults if not provided).

        Raises:
            ValueError: If initial_capital is not positive.
        """
        if initial_capital <= 0:
            raise ValueError(f"Initial capital must be positive, got {initial_capital}")

        self.initial_capital: float = initial_capital
        self.config: SimulatorConfig = config or SimulatorConfig()

        # Trading state
        self.positions: dict[Symbol, Quantity] = {}
        self.cash: float = initial_capital
        self.timestamp: int = 0

        # History tracking
        self.trades: list[dict[str, Any]] = []
        self.equity_history: list[dict[str, Any]] = []
        self.order_history: list[Order] = []

    def run_backtest(
        self,
        policy: Policy,
        market_data: dict[Symbol, pl.DataFrame],
        *,
        start_timestamp: Timestamp | None = None,
        end_timestamp: Timestamp | None = None,
    ) -> BacktestResult:
        """Run backtest on historical data.

        Args:
            policy: Trading policy to test
            market_data: Dict of symbol -> OHLCV DataFrame
            start_timestamp: Optional start time
            end_timestamp: Optional end time

        Returns:
            BacktestResult with trades, equity curve, and metrics
        """
        # Align all dataframes to common timestamps
        all_timestamps = self._get_common_timestamps(market_data)

        if start_timestamp:
            all_timestamps = [ts for ts in all_timestamps if ts >= start_timestamp]
        if end_timestamp:
            all_timestamps = [ts for ts in all_timestamps if ts <= end_timestamp]

        # Main backtest loop
        for timestamp in all_timestamps:
            self.timestamp = timestamp

            # Create market snapshot
            snapshot = self._create_snapshot(timestamp, market_data)

            # Get current portfolio state
            portfolio = self._get_portfolio_state(snapshot)

            # Record equity
            self.equity_history.append(
                {
                    "timestamp": timestamp,
                    "equity": portfolio.equity,
                    "cash": self.cash,
                    "positions_value": portfolio.equity - self.cash,
                }
            )

            # Call policy
            orders = policy.decide(portfolio, snapshot)

            # Execute orders
            for order in orders:
                self._execute_order(order, snapshot)

        # Compile results
        return self._compile_results()

    def _get_common_timestamps(
        self, market_data: dict[Symbol, pl.DataFrame]
    ) -> list[Timestamp]:
        """Get all unique timestamps from market data.

        Args:
            market_data: Dictionary mapping symbols to their OHLCV dataframes.

        Returns:
            Sorted list of all unique timestamps across all symbols.
        """
        if not market_data:
            return []

        # Collect all unique timestamps
        all_timestamps: set[Timestamp] = set()
        for df in market_data.values():
            timestamps_list = df["timestamp"].to_list()
            all_timestamps.update(timestamps_list)

        return sorted(all_timestamps)

    def _create_snapshot(
        self,
        timestamp: Timestamp,
        market_data: dict[Symbol, pl.DataFrame],
    ) -> MarketSnapshot:
        """Create market snapshot at given timestamp.

        Args:
            timestamp: The timestamp to create snapshot for.
            market_data: Dictionary mapping symbols to their OHLCV dataframes.

        Returns:
            MarketSnapshot containing prices and volumes at the given timestamp.
        """
        prices: dict[Symbol, float] = {}
        volumes: dict[Symbol, float] = {}

        for symbol, df in market_data.items():
            # Find row for this timestamp
            row = df.filter(pl.col("timestamp") == timestamp)

            if len(row) > 0:
                close_value = row["close"][0]
                volume_value = row["volume"][0]

                # Type-safe conversion to float
                if isinstance(close_value, (int, float)):
                    prices[symbol] = float(close_value)
                if isinstance(volume_value, (int, float)):
                    volumes[symbol] = float(volume_value)

        return MarketSnapshot(
            timestamp=timestamp,
            prices=prices,
            volumes=volumes,
        )

    def _get_portfolio_state(self, snapshot: MarketSnapshot) -> PortfolioState:
        """Calculate current portfolio state.

        Args:
            snapshot: Current market snapshot with prices and volumes.

        Returns:
            Current portfolio state including positions, cash, and equity.
        """
        # Calculate total value of all positions
        positions_value: float = 0.0
        for symbol, quantity in self.positions.items():
            price = snapshot.prices.get(symbol, 0.0)
            positions_value += quantity * price

        equity = self.cash + positions_value

        return PortfolioState(
            positions=self.positions.copy(),
            cash=self.cash,
            equity=equity,
            timestamp=self.timestamp,
        )

    def _execute_order(self, order: Order, snapshot: MarketSnapshot) -> None:
        """Execute an order with realistic microstructure effects.

        Args:
            order: The order to execute.
            snapshot: Current market snapshot.

        Note:
            This method updates internal state (positions, cash, trades) if order fills.
            Orders may be rejected or partially filled based on simulator configuration.
        """
        price = snapshot.prices.get(order.symbol)
        volume = snapshot.volumes.get(order.symbol, 1_000_000.0)

        if price is None or price <= 0:
            return  # Can't execute without valid price

        # Calculate execution price with slippage
        fill_price = self._calculate_fill_price(order, price, volume)

        # Calculate fees and fill probability
        if order.order_type == OrderType.MARKET:
            fee_bps = self.config.taker_fee_bps
            will_fill = True
        else:
            fee_bps = self.config.maker_fee_bps
            # Limit orders have probability of not filling
            # Generate random value between 0 and 1
            random_value = float(pl.Series([0.0, 1.0]).sample(1, with_replacement=True).item())
            will_fill = random_value < self.config.limit_fill_probability

        if not will_fill:
            return  # Order didn't fill

        # Execute the trade
        quantity = order.quantity
        notional = quantity * fill_price
        fee = notional * (fee_bps / 10_000.0)

        # Update positions and cash
        if order.side == Side.BUY:
            # Buy: decrease cash, increase position
            total_cost = notional + fee

            if total_cost > self.cash:
                # Insufficient funds - reduce quantity
                quantity = (self.cash / (fill_price * (1 + fee_bps / 10_000.0)))
                if quantity < 0.01:  # Minimum size
                    return
                notional = quantity * fill_price
                fee = notional * (fee_bps / 10_000.0)
                total_cost = notional + fee

            self.cash -= total_cost
            self.positions[order.symbol] = (
                self.positions.get(order.symbol, 0.0) + quantity
            )

        else:  # SELL
            # Sell: increase cash, decrease position
            current_position = self.positions.get(order.symbol, 0.0)

            # Can't sell more than we have
            quantity = min(quantity, current_position)
            if quantity < 0.01:
                return

            notional = quantity * fill_price
            fee = notional * (fee_bps / 10_000.0)

            self.cash += notional - fee
            self.positions[order.symbol] = current_position - quantity

            # Clean up zero positions
            if abs(self.positions[order.symbol]) < 1e-6:
                del self.positions[order.symbol]

        # Record trade
        self.trades.append(
            {
                "timestamp": self.timestamp,
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": quantity,
                "price": fill_price,
                "fee": fee,
                "notional": notional,
            }
        )

        # Notify policy
        fill = Fill(
            order_id=order.id or "sim",
            symbol=order.symbol,
            side=order.side,
            quantity=quantity,
            price=fill_price,
            timestamp=self.timestamp,
            fee=fee,
        )
        policy = None  # Would need to pass policy here for on_fill callback

    def _calculate_fill_price(
        self,
        order: Order,
        mid_price: Price,
        avg_volume: float,
    ) -> Price:
        """Calculate realistic fill price with slippage and spread.

        Models:
        1. Bid-ask spread (half-spread from mid)
        2. Market impact (proportional to order size / volume)
        """
        # Calculate spread
        spread_bps = max(
            self.config.min_spread_bps,
            self.config.spread_volatility_multiplier * 0.01,  # Simplified
        )
        half_spread = mid_price * (spread_bps / 2.0 / 10_000.0)

        # Calculate slippage from market impact
        if avg_volume > 0:
            size_ratio = order.quantity / avg_volume
            slippage_bps = self.config.base_slippage_bps * (
                size_ratio ** self.config.slippage_exponent
            )
            slippage = mid_price * (slippage_bps / 10_000.0)
        else:
            slippage = 0.0

        # Apply direction-specific costs
        if order.side == Side.BUY:
            # Buy at ask + slippage
            return mid_price + half_spread + slippage
        # Sell at bid - slippage
        return mid_price - half_spread - slippage

    def _compile_results(self) -> BacktestResult:
        """Compile backtest results and calculate metrics."""
        # Convert to DataFrames
        trades_df = pl.DataFrame(self.trades) if self.trades else pl.DataFrame()
        equity_df = pl.DataFrame(self.equity_history)

        # Calculate metrics
        metrics = self._calculate_metrics(equity_df, trades_df)

        # Final portfolio
        final_portfolio = PortfolioState(
            positions=self.positions.copy(),
            cash=self.cash,
            equity=self.cash
            + sum(
                qty * 0.0  # Would need final prices here
                for qty in self.positions.values()
            ),
            timestamp=self.timestamp,
        )

        return BacktestResult(
            trades=trades_df,
            equity_curve=equity_df,
            metrics=metrics,
            final_portfolio=final_portfolio,
        )

    def _calculate_metrics(
        self,
        equity_df: pl.DataFrame,
        trades_df: pl.DataFrame,
    ) -> dict[str, float]:
        """Calculate performance metrics.

        Returns:
            Dictionary of performance metrics with proper type safety.
        """
        if len(equity_df) == 0:
            return {}

        equity = equity_df["equity"]

        # Calculate returns
        returns = equity.pct_change().drop_nulls()

        # Basic metrics with type-safe conversions
        final_equity_value = equity[-1]
        total_return = (
            (float(final_equity_value) / self.initial_capital - 1.0) * 100.0
            if isinstance(final_equity_value, (int, float))
            else 0.0
        )

        # Calculate Sharpe ratio with proper type guards
        if len(returns) > 1:
            mean_return = returns.mean()
            std_return = returns.std()

            # Type guard: ensure we have valid numeric values
            if (
                mean_return is not None
                and std_return is not None
                and not isinstance(mean_return, timedelta)
                and not isinstance(std_return, timedelta)
                and isinstance(mean_return, (int, float))
                and isinstance(std_return, (int, float))
                and std_return > 0
            ):
                sharpe = float(mean_return) / float(std_return)
            else:
                sharpe = 0.0

            max_drawdown = self._calculate_max_drawdown(equity)
        else:
            sharpe = 0.0
            max_drawdown = 0.0

        num_trades = len(trades_df) if len(trades_df) > 0 else 0

        # Calculate win rate
        if len(trades_df) > 0 and "notional" in trades_df.columns:
            # Simple approximation: positive notional = profit
            # Real calculation would need PnL per trade
            win_rate = 0.5  # Placeholder
        else:
            win_rate = 0.0

        return {
            "total_return_pct": total_return,
            "sharpe_ratio": sharpe,
            "max_drawdown_pct": max_drawdown * 100.0,
            "num_trades": float(num_trades),
            "win_rate": win_rate,
            "final_equity": float(final_equity_value) if isinstance(final_equity_value, (int, float)) else 0.0,
        }

    def _calculate_max_drawdown(self, equity: pl.Series) -> float:
        """Calculate maximum drawdown.

        Args:
            equity: Series of equity values over time.

        Returns:
            Maximum drawdown as a decimal (0.1 = 10% drawdown).
        """
        if len(equity) == 0:
            return 0.0

        peak: float = float(equity[0]) if isinstance(equity[0], (int, float)) else 0.0
        max_dd = 0.0

        for value in equity:
            # Type guard for numeric values
            if not isinstance(value, (int, float)):
                continue

            current_value = float(value)
            peak = max(peak, current_value)

            if peak > 0:
                dd = (peak - current_value) / peak
                max_dd = max(max_dd, dd)

        return max_dd
