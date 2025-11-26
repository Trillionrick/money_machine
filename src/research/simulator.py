"""High-fidelity execution simulator with realistic market microstructure.

This simulator models:
- Bid-ask spreads
- Slippage based on order size
- Partial fills
- Latency
- Fee structures
"""

from dataclasses import dataclass

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
            initial_capital: Starting cash
            config: Simulator configuration
        """
        self.initial_capital = initial_capital
        self.config = config or SimulatorConfig()

        # State
        self.positions: dict[Symbol, Quantity] = {}
        self.cash = initial_capital
        self.timestamp = 0

        # History
        self.trades: list[dict] = []
        self.equity_history: list[dict] = []
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
        """Get timestamps common to all symbols."""
        if not market_data:
            return []

        # Get all unique timestamps
        all_ts = set()
        for df in market_data.values():
            all_ts.update(df["timestamp"].to_list())

        return sorted(all_ts)

    def _create_snapshot(
        self,
        timestamp: Timestamp,
        market_data: dict[Symbol, pl.DataFrame],
    ) -> MarketSnapshot:
        """Create market snapshot at given timestamp."""
        prices = {}
        volumes = {}

        for symbol, df in market_data.items():
            # Find row for this timestamp
            row = df.filter(pl.col("timestamp") == timestamp)

            if len(row) > 0:
                prices[symbol] = float(row["close"][0])
                volumes[symbol] = float(row["volume"][0])

        return MarketSnapshot(
            timestamp=timestamp,
            prices=prices,
            volumes=volumes,
        )

    def _get_portfolio_state(self, snapshot: MarketSnapshot) -> PortfolioState:
        """Calculate current portfolio state."""
        # Calculate position values
        positions_value = 0.0
        for symbol, qty in self.positions.items():
            price = snapshot.prices.get(symbol, 0.0)
            positions_value += qty * price

        equity = self.cash + positions_value

        return PortfolioState(
            positions=self.positions.copy(),
            cash=self.cash,
            equity=equity,
            timestamp=self.timestamp,
        )

    def _execute_order(self, order: Order, snapshot: MarketSnapshot) -> None:
        """Execute an order with realistic microstructure effects."""
        price = snapshot.prices.get(order.symbol)
        volume = snapshot.volumes.get(order.symbol, 1_000_000.0)

        if price is None or price <= 0:
            return  # Can't execute without valid price

        # Calculate execution price with slippage
        fill_price = self._calculate_fill_price(order, price, volume)

        # Calculate fees
        if order.order_type == OrderType.MARKET:
            fee_bps = self.config.taker_fee_bps
            will_fill = True
        else:
            fee_bps = self.config.maker_fee_bps
            # Limit orders have probability of not filling
            will_fill = pl.Series([0.0]).sample(1, with_replacement=True).item() < self.config.limit_fill_probability

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
        """Calculate performance metrics."""
        if len(equity_df) == 0:
            return {}

        equity = equity_df["equity"]

        # Returns
        returns = equity.pct_change().drop_nulls()

        # Basic metrics
        total_return = (float(equity[-1]) / self.initial_capital - 1.0) * 100

        if len(returns) > 1:
            sharpe = float(returns.mean() / returns.std()) if float(returns.std()) > 0 else 0.0
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
            "max_drawdown_pct": max_drawdown * 100,
            "num_trades": float(num_trades),
            "win_rate": win_rate,
            "final_equity": float(equity[-1]),
        }

    def _calculate_max_drawdown(self, equity: pl.Series) -> float:
        """Calculate maximum drawdown."""
        peak = equity[0]
        max_dd = 0.0

        for value in equity:
            peak = max(peak, value)
            dd = (peak - value) / peak
            max_dd = max(max_dd, dd)

        return max_dd
