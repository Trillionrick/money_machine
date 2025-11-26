# Quick Start Guide

Congratulations! Your modern trading bot infrastructure is ready to use.

## ✅ What's Been Set Up

### 1. **Project Structure**

trading-bot/
├── src/
│   ├── core/          # Pure math, types, protocols (THE BRAIN)
│   │   ├── execution.py    # Order/Fill types, ExecutionEngine protocol
│   │   ├── policy.py       # Policy interface - YOUR TRADING LOGIC GOES HERE
│   │   ├── sizing.py       # Kelly sizing, utility functions
│   │   └── types.py        # Shared type definitions
│   │
│   ├── data/          # Data storage and pipelines
│   │   └── store.py        # High-performance Parquet-based storage
│   │
│   ├── live/          # Live trading engine
│   │   └── engine.py       # Async event loop with structured concurrency
│   │
│   ├── research/      # Backtesting and simulations (expand as needed)
│   └── native/        # Rust/C++ extensions (only when proven necessary)
│
├── tests/             # Comprehensive test suite (30 tests, all passing)
├── pyproject.toml     # Modern dependencies and tool configurations
└── Makefile           # Common development commands


### 2. **Modern Tooling Installed**
- ✅ **uv** (0.9.11): Ultra-fast package manager
- ✅ **Python 3.12.3**: Modern type system with PEP 695
- ✅ **ruff**: All-in-one linter/formatter (passing)
- ✅ **pyright**: Strict type checking
- ✅ **pytest**: 30 tests passing with 40% coverage
- ✅ **polars**: High-performance dataframes
- ✅ **msgspec**: Fast serialization
- ✅ **structlog**: Structured logging

### 3. **Core Features Implemented**

#### Execution Layer (`src/core/execution.py`)
- `Order` and `Fill` types (immutable, fast serialization)
- `ExecutionEngine` protocol (swap implementations: paper/live/native)
- Side and OrderType enums

#### Policy Interface (`src/core/policy.py`)
- `Policy` protocol - **implement this for your strategies**
- `PortfolioState` and `MarketSnapshot` types
- `ModelPrediction` interface for ML models
- `SimplePolicy` example

#### Position Sizing (`src/core/sizing.py`)
- `fractional_kelly()`: Conservative Kelly sizing
- `kelly_with_ruin()`: Kelly with drawdown constraints
- `optimal_target_size()`: Target-hitting optimization
- `LogUtility` and `TargetUtility` classes
- Sharpe ratio utilities

#### Data Storage (`src/data/store.py`)
- Parquet-based time-series storage
- DuckDB integration for analytics
- Symbol and timeframe partitioning

#### Live Engine (`src/live/engine.py`)
- Async event loop with structured concurrency
- Market data processing
- Order submission pipeline
- Fill handling
- Health monitoring

## 🚀 Next Steps

### Step 1: Activate Environment
bash
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate     # Windows


### Step 2: Verify Installation
bash
make test          # Run all tests
make lint          # Check code quality
make format        # Format code


### Step 3: Create Your First Policy

Create `src/research/my_strategy.py`:

python
"""My first trading strategy."""

from src.core import (
    Order,
    OrderSeq,
    OrderType,
    Policy,
    PortfolioState,
    MarketSnapshot,
    Side,
    fractional_kelly,
)
from src.core.types import ContextMap

class MomentumStrategy(Policy):
    """Simple momentum strategy example."""

    def __init__(
        self,
        symbols: list[str],
        kelly_fraction: float = 0.25,
    ) -> None:
        self.symbols = symbols
        self.kelly_fraction = kelly_fraction

    def decide(
        self,
        portfolio: PortfolioState,
        snapshot: MarketSnapshot,
        context: ContextMap | None = None,
    ) -> OrderSeq:
        """Generate orders based on momentum signals."""
        orders = []

        # Example: Simple momentum logic
        for symbol in self.symbols:
            price = snapshot.price(symbol)
            if price is None:
                continue

            # Your strategy logic here
            # This is where the "genius" lives

            # Example: If we have a signal in context
            if context and symbol in context:
                signal = context[symbol]

                # Size position using Kelly
                edge = signal.get("expected_return", 0.0)
                variance = signal.get("variance", 0.04)
                size = fractional_kelly(
                    edge=edge,
                    variance=variance,
                    fraction=self.kelly_fraction,
                )

                # Create order
                if size > 0.01:  # Minimum threshold
                    target_value = portfolio.equity * size
                    quantity = target_value / price

                    orders.append(Order(
                        symbol=symbol,
                        side=Side.BUY,
                        quantity=quantity,
                        price=price * 0.999,  # Slightly below market
                        order_type=OrderType.LIMIT,
                    ))

        return orders

    def on_fill(self, fill: msgspec.Struct) -> None:
        """Handle fill notifications."""
        # Update internal state, log, etc.
        pass


### Step 4: Backtest Your Strategy

Create `src/research/backtest.py`:

python
"""Simple backtesting framework."""

import polars as pl
from src.core import Policy, PortfolioState, MarketSnapshot
from src.data import DataStore

def run_backtest(
    policy: Policy,
    data_store: DataStore,
    symbols: list[str],
    initial_capital: float = 100_000.0,
) -> pl.DataFrame:
    """Simple backtest implementation."""

    # Load data
    all_bars = {}
    for symbol in symbols:
        all_bars[symbol] = data_store.load_bars(symbol, "1h")

    # Initialize state
    portfolio = PortfolioState(
        positions={},
        cash=initial_capital,
        equity=initial_capital,
        timestamp=0,
    )

    # Run through time
    results = []

    # ... implement your backtest loop here ...

    return pl.DataFrame(results)


### Step 5: Set Up Data Pipeline

python
"""Example: Download and store market data."""

from pathlib import Path
import polars as pl
from src.data import DataStore

# Initialize data store
store = DataStore(Path("./data"))

# Example: Create sample data (replace with real data source)
sample_bars = pl.DataFrame({
    "timestamp": [1000, 2000, 3000],
    "open": [100.0, 101.0, 102.0],
    "high": [101.0, 102.0, 103.0],
    "low": [99.0, 100.0, 101.0],
    "close": [100.5, 101.5, 102.5],
    "volume": [1000.0, 1100.0, 1200.0],
})

# Save to store
store.save_bars("AAPL", "1h", sample_bars)

# Load back
loaded = store.load_bars("AAPL", "1h")
print(loaded)


## 📋 Common Commands

bash
# Development
make install       # Install core dependencies
make dev           # Install dev dependencies
make test          # Run tests
make test-fast     # Run only fast tests
make lint          # Check code quality
make format        # Auto-format code
make type-check    # Run type checker
make security      # Security scans

# Cleaning
make clean         # Remove build artifacts


## 🎯 Key Design Principles

### 1. **Python First, Native When Proven**
- Write everything in Python initially
- Profile with `py-spy` or `scalene`
- Only move to Rust/C++ when profiling shows it's necessary

### 2. **Explicit Utility Functions**
- **Log Utility**: Slow compounding, minimize ruin (Kelly)
- **Target Utility**: Sprint to wealth target, accept higher variance

### 3. **"House Over Player" Mentality**
- Design payoff structures, don't just find trades
- Control optionality with limited downside
- Think like an architect, not a gambler

### 4. **Type Safety**
- Use strict type checking (`pyright`)
- Protocol-based interfaces for flexibility
- Immutable data structures (`msgspec.Struct`)

## 🔧 Configuration

### Environment Variables
Copy `.env.example` to `.env`:
bash
cp .env.example .env
# Edit .env with your API keys


### Broker Integration
Implement `ExecutionEngine` protocol for your broker:
python
from src.core import ExecutionEngine

class MyBrokerEngine:
    """Your broker implementation."""

    async def submit_orders(self, orders: OrderSeq) -> None:
        # Connect to your broker API
        pass

    # Implement other protocol methods...


## 📊 What Makes This Different

This isn't a typical "trading bot" project. It's designed around:

1. **Explicit utility optimization**: Choose your objective function
2. **Convex payoff engineering**: Asymmetric upside, controlled downside
3. **Architectural thinking**: Build games where small capital controls large optionality
4. **Modern Python**: Full type safety, fast tools, clean abstractions

## 🚨 Important Notes

- **Security**: Never commit `.env` files or API keys
- **Testing**: Write tests for your strategies (`tests/` directory)
- **Performance**: Start with Python, profile before optimizing
- **Risk**: This is educational. Test thoroughly before trading real money.

## 📚 Resources

- [uv documentation](https://github.com/astral-sh/uv)
- [Polars guide](https://pola-rs.github.io/polars-book/)
- [msgspec docs](https://jcristharif.com/msgspec/)
- [Kelly Criterion](https://en.wikipedia.org/wiki/Kelly_criterion)

## 💡 Philosophy

From the design document:

> "Don't look for magic trades; look for game designs where small equity controls large optionality with structurally positive drift and limited personal downside."

Your edge isn't in predicting the market perfectly. It's in:
1. Designing asymmetric payoffs
2. Sizing positions optimally
3. Managing risk structurally
4. Iterating quickly with clean, testable code

Now go build something interesting. 🚀
