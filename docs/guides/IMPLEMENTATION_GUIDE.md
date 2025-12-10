
# Implementation Guide: Building Your Trading Edge

This guide shows you how to implement real trading strategies using the system we've built.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Concepts](#core-concepts)
3. [Building Your First Strategy](#building-your-first-strategy)
4. [Advanced Techniques](#advanced-techniques)
5. [Risk Management](#risk-management)
6. [Going Live](#going-live)

---

## Architecture Overview

The system is built on four layers:


┌─────────────────────────────────────────────────────────────┐
│                     YOUR STRATEGY                            │
│                   (Policy Implementation)                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  RISK MANAGEMENT                             │
│    (Position Limits, Circuit Breakers, Drawdown Control)    │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                 EXECUTION ENGINE                             │
│          (Paper Trading / Live Broker / Simulator)           │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    MARKET DATA                               │
│              (Live Feed / Historical / API)                  │
└─────────────────────────────────────────────────────────────┘


---

## Core Concepts

### 1. The Policy Pattern

Your strategy implements the `Policy` protocol:

python
class Policy(Protocol):
    def decide(
        self,
        portfolio: PortfolioState,    # Current positions & cash
        snapshot: MarketSnapshot,      # Current market prices
        context: ContextMap | None,    # Optional additional data
    ) -> OrderSeq:                     # Orders to submit
        ...


**This is where your "genius" lives.** Everything else is infrastructure.

### 2. Position Sizing: The Key to Survival

Never hard-code position sizes. Always use mathematical sizing:

python
from src.core.sizing import kelly_with_ruin

size = kelly_with_ruin(
    edge=0.05,              # Expected 5% return
    variance=0.04,          # 20% vol (0.2^2)
    max_drawdown=0.15,      # Stop at 15% DD
    kelly_fraction=0.25,    # Quarter Kelly (conservative)
)


**Why this matters:** The difference between 100x returns and ruin is often just position sizing.

### 3. Three Types of Edge

1. **Structural Edge** (Market Making)
   - You design the game
   - Example: Earn bid-ask spread
   - High win rate, small gains

2. **Behavioral Edge** (Momentum)
   - Exploit market psychology
   - Example: Under/over-reaction to news
   - Lower win rate, asymmetric payoffs

3. **Statistical Edge** (Mean Reversion)
   - Exploit temporary mispricings
   - Example: Pairs trading
   - Medium win rate, controlled losses

---

## Building Your First Strategy

### Step 1: Define Your Edge

Ask yourself:
- **What information do I have that the market doesn't?**
- **What behavioral bias am I exploiting?**
- **What structural advantage do I have?**

If you can't answer these, you don't have an edge. Go back to research.

### Step 2: Implement the Policy

Create `src/research/my_strategy.py`:

python
from collections import deque
import polars as pl

from src.core import (
    Order,
    OrderSeq,
    OrderType,
    Policy,
    PortfolioState,
    MarketSnapshot,
    Side,
    kelly_with_ruin,
)
from src.core.types import ContextMap, Symbol


class MyStrategy(Policy):
    """My custom strategy.

    Edge: [Describe your edge here]
    Expected Sharpe: [Your estimate]
    Typical holding period: [Time]
    """

    def __init__(
        self,
        symbols: list[Symbol],
        lookback: int = 20,
        kelly_fraction: float = 0.25,
    ) -> None:
        self.symbols = symbols
        self.lookback = lookback
        self.kelly_fraction = kelly_fraction

        # Track price history
        self.price_history = {
            sym: deque(maxlen=lookback) for sym in symbols
        }

    def decide(
        self,
        portfolio: PortfolioState,
        snapshot: MarketSnapshot,
        context: ContextMap | None = None,
    ) -> OrderSeq:
        """Generate orders based on your edge."""
        orders = []

        for symbol in self.symbols:
            price = snapshot.price(symbol)
            if price is None:
                continue

            # Update history
            self.price_history[symbol].append(price)

            # Need enough data
            if len(self.price_history[symbol]) < self.lookback:
                continue

            # YOUR LOGIC HERE
            signal = self._calculate_signal(symbol)

            if signal is None:
                continue

            # Create order with Kelly sizing
            order = self._create_order(
                symbol, signal, price, portfolio
            )

            if order:
                orders.append(order)

        return orders

    def _calculate_signal(self, symbol: Symbol) -> dict | None:
        """Calculate your signal.

        Returns:
            Dictionary with:
                - direction: 1 (buy) or -1 (sell)
                - confidence: 0-1
                - expected_return: your edge estimate
                - variance: return variance estimate
        """
        prices = pl.Series(list(self.price_history[symbol]))

        # Example: Simple momentum
        returns = prices.pct_change().drop_nulls()

        if len(returns) < 2:
            return None

        mean_return = float(returns.mean())
        std_return = float(returns.std())

        if std_return == 0:
            return None

        # Z-score as signal strength
        z_score = mean_return / std_return

        if abs(z_score) < 1.0:  # Weak signal
            return None

        return {
            "direction": 1.0 if z_score > 0 else -1.0,
            "confidence": min(abs(z_score) / 3.0, 1.0),
            "expected_return": abs(mean_return),
            "variance": std_return ** 2,
        }

    def _create_order(
        self,
        symbol: Symbol,
        signal: dict,
        price: float,
        portfolio: PortfolioState,
    ) -> Order | None:
        """Create order with Kelly sizing."""

        # Calculate position size
        size_fraction = kelly_with_ruin(
            edge=signal["expected_return"],
            variance=signal["variance"],
            max_drawdown=0.15,
            kelly_fraction=self.kelly_fraction,
        )

        # Scale by confidence
        size_fraction *= signal["confidence"]

        # Calculate target position
        target_value = portfolio.equity * size_fraction
        target_quantity = target_value / price

        # Adjust for direction
        target_quantity *= signal["direction"]

        # Calculate delta from current
        current_pos = portfolio.position(symbol)
        delta = target_quantity - current_pos

        if abs(delta * price) < portfolio.equity * 0.01:
            return None  # Too small

        return Order(
            symbol=symbol,
            side=Side.BUY if delta > 0 else Side.SELL,
            quantity=abs(delta),
            price=price,
            order_type=OrderType.LIMIT,
        )

    def on_fill(self, fill: Fill) -> None:
        """Handle fill notification."""
        # Update internal state if needed
        pass


### Step 3: Backtest Rigorously

Create `examples/test_my_strategy.py`:

python
from pathlib import Path
from src.data import DataStore
from src.research.simulator import Simulator
from src.research.analytics import PerformanceAnalyzer
from src.research.my_strategy import MyStrategy

def main():
    # Load real data
    store = DataStore(Path("./data"))
    market_data = {
        "AAPL": store.load_bars("AAPL", "1h"),
        "GOOGL": store.load_bars("GOOGL", "1h"),
    }

    # Create strategy
    strategy = MyStrategy(
        symbols=["AAPL", "GOOGL"],
        lookback=20,
        kelly_fraction=0.25,
    )

    # Run backtest
    simulator = Simulator(initial_capital=100_000.0)
    result = simulator.run_backtest(strategy, market_data)

    # Analyze
    analyzer = PerformanceAnalyzer()
    metrics = analyzer.calculate_metrics(
        result.equity_curve,
        result.trades,
    )

    analyzer.print_report(metrics)

    # Validate
    assert metrics.sharpe_ratio > 1.0, "Sharpe too low"
    assert metrics.max_drawdown_pct < 25.0, "Drawdown too high"
    assert metrics.num_trades > 10, "Not enough trades"

    print("✓ Strategy passed validation!")

if __name__ == "__main__":
    main()


Run it:
bash
python examples/test_my_strategy.py


---

## Advanced Techniques

### 1. Regime-Aware Sizing

Adapt position size to market conditions:

python
from src.core.regime import RegimeDetector, AdaptiveSizer

detector = RegimeDetector(lookback=60)
sizer = AdaptiveSizer(base_kelly_fraction=0.25)

# In your strategy
for price in price_stream:
    regime = detector.update(price)

    # Adjust size based on regime
    base_size = kelly_with_ruin(edge, variance)
    regime_mult = detector.get_regime_multiplier(regime)
    final_size = base_size * regime_mult


### 2. Multi-Strategy Portfolio

Combine uncorrelated strategies:

python
from src.research.strategies import (
    MarketMakingStrategy,
    MomentumStrategy,
    PairsTradingStrategy,
)

class PortfolioStrategy(Policy):
    def __init__(self):
        # Allocate capital to sub-strategies
        self.strategies = [
            (MarketMakingStrategy([...]), 0.33),  # 33% to MM
            (MomentumStrategy([...]), 0.33),       # 33% to momentum
            (PairsTradingStrategy(...), 0.34),     # 34% to stat arb
        ]

    def decide(self, portfolio, snapshot, context):
        all_orders = []

        for strategy, weight in self.strategies:
            # Create sub-portfolio
            sub_portfolio = PortfolioState(
                positions=portfolio.positions,
                cash=portfolio.cash * weight,
                equity=portfolio.equity * weight,
                timestamp=portfolio.timestamp,
            )

            # Get orders from sub-strategy
            orders = strategy.decide(sub_portfolio, snapshot, context)
            all_orders.extend(orders)

        return all_orders


### 3. Dynamic Hedging

Protect profits with options or inverse positions:

python
def decide(self, portfolio, snapshot, context):
    orders = []

    # Main strategy orders
    main_orders = self._generate_main_orders(...)
    orders.extend(main_orders)

    # Calculate portfolio delta
    total_delta = self._calculate_delta(portfolio, snapshot)

    # If heavily exposed, add hedge
    if abs(total_delta) > portfolio.equity * 0.5:
        hedge_order = self._create_hedge_order(total_delta, snapshot)
        if hedge_order:
            orders.append(hedge_order)

    return orders


---

## Risk Management

**ALWAYS** wrap your strategy with risk management:

python
from src.core.risk import RiskManager, RiskLimits

# Configure limits
risk_mgr = RiskManager(
    limits=RiskLimits(
        max_position_pct=0.20,          # Max 20% in one position
        max_total_exposure_pct=2.0,     # Max 200% gross leverage
        max_daily_loss_pct=0.05,        # Stop at 5% daily loss
        max_weekly_loss_pct=0.10,       # Stop at 10% weekly loss
        max_drawdown_pct=0.25,          # Stop at 25% drawdown
        max_order_value_pct=0.15,       # Max 15% per order
        max_leverage=2.0,                # Max 2x leverage
    )
)

# In your trading loop
try:
    orders = strategy.decide(portfolio, snapshot)

    # Filter through risk manager
    safe_orders = risk_mgr.filter_orders(
        orders, portfolio, current_prices=snapshot.prices
    )

    await execution_engine.submit_orders(safe_orders)

except RiskViolation as e:
    print(f"Trading halted: {e}")
    # Alert, log, investigate


**Key principle:** Risk management is not optional. It's what keeps you in the game.

---

## Going Live

### Step 1: Paper Trade

Test with live data, zero risk:

python
from src.live.paper_trading import PaperTradingEngine
from src.live.engine import LiveEngine

# Create paper trading engine
paper_engine = PaperTradingEngine(
    initial_cash=100_000.0,
    slippage_bps=5.0,
)

# Create live engine
engine = LiveEngine(
    exec_engine=paper_engine,
    data_feed=your_live_data_feed,
    policy=your_strategy,
    tick_rate_hz=1.0,
)

# Run paper trading
async with engine.lifecycle():
    await engine.run()


Run for **at least 30 days** before considering real money.

### Step 2: Start Small

When going live:
1. Start with 10% of intended capital
2. Watch for 1 week
3. Double capital every week if performing as expected
4. Hit full capital in ~4 weeks

### Step 3: Monitor Continuously

python
# Get metrics
metrics = risk_mgr.get_metrics(portfolio, current_prices)

# Alert if issues
if metrics.daily_pnl_pct < -0.03:  # Down 3% today
    send_alert("Daily loss approaching limit")

if metrics.largest_position_pct > 0.15:  # Position too large
    send_alert("Position size exceeds comfortable level")


---

## Checklist Before Going Live

- [ ] Backtested on ≥2 years of data
- [ ] Sharpe ratio > 1.0
- [ ] Max drawdown < 25%
- [ ] Strategy profitable in multiple regimes
- [ ] Paper traded for ≥30 days
- [ ] Risk limits configured and tested
- [ ] Monitoring/alerting set up
- [ ] Emergency stop procedure defined
- [ ] Position sizing conservative (quarter Kelly or less)
- [ ] Understanding of worst-case scenario
- [ ] Can afford to lose the capital

If you can't check all boxes, **don't go live**.

---

## Philosophy Reminder

From the design document:

> "The trick is to stop thinking like a trader and start thinking like an architect of payoff structures."

You're not trying to predict the market. You're trying to design a game where:
1. You have a structural edge
2. Position sizing maximizes long-run growth
3. Risk management prevents ruin
4. Convexity gives you asymmetric payoffs

Focus on the **process**, not individual trades. The math takes care of the rest.

---

## Resources

- **Kelly Criterion**: `src/core/sizing.py`
- **Risk Management**: `src/core/risk.py`
- **Regime Detection**: `src/core/regime.py`
- **Example Strategies**: `src/research/strategies.py`
- **Backtesting**: `src/research/simulator.py`
- **Paper Trading**: `src/live/paper_trading.py`

## Support

Issues? Questions? Check:
1. `README.md` - Architecture overview
2. `QUICKSTART.md` - Getting started guide
3. `examples/README.md` - Example walkthroughs
4. Test suite: `pytest` - Working code examples

Remember: **Start simple. Add complexity only when proven necessary.**

Good luck building your edge. 🚀
