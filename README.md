# Trading Bot - Modern Algorithmic Trading System

A high-performance algorithmic trading system built with 2025 best practices, featuring Python 3.12+, modern tooling, and clean architecture.

## Architecture Overview

This system is designed with the philosophy: **"Don't look for magic trades; look for game designs where small equity controls large optionality with structurally positive drift."**

### Key Design Principles

1. **House Over Player**: Design payoff structures rather than just finding trades
2. **Explicit Utility Functions**: Choose between log-utility (Kelly) vs target-hitting
3. **Asymmetric Payoff Engineering**: Convex upside with controlled downside
4. **Python-First, Native When Proven**: Optimize for research velocity, not premature optimization

## Technology Stack

### Core Technologies (2025 Standards)
- **Python 3.12+**: Modern type system with PEP 695 generics
- **uv**: Ultra-fast package management (replaces poetry/pip-tools)
- **Polars**: High-performance dataframes (10-100x faster than pandas)
- **DuckDB**: Embedded OLAP for time-series analytics
- **msgspec**: Zero-copy serialization (10-100x faster than Pydantic)
- **orjson**: Ultra-fast JSON (10-100x faster than stdlib)
- **Pydantic V2**: Modern config management with validation

### Developer Tools
- **ruff**: All-in-one linter/formatter (replaces black, isort, flake8, pylint)
- **pyright**: Strict type checking
- **pytest**: Testing with async support and benchmarking
- **structlog**: Structured logging for production
- **OpenTelemetry**: Modern observability stack

### Optional Performance
- **Rust (PyO3)**: For order book and execution hot paths
- **C++ (nanobind)**: For simulation loops if needed

## Project Structure


trading-bot/
├── src/
│   ├── core/          # Pure math, types, protocols
│   │   ├── execution.py    # Order/Fill types, ExecutionEngine protocol
│   │   ├── policy.py       # Policy interface, portfolio state
│   │   ├── sizing.py       # Kelly sizing, utility functions
│   │   └── types.py        # Shared type definitions
│   │
│   ├── data/          # Ingestion, storage, feature pipelines
│   │   ├── store.py        # Parquet-based data store
│   │   ├── feeds.py        # Market data feeds
│   │   └── features.py     # Feature engineering
│   │
│   ├── research/      # Backtests, simulations, experiments
│   │   ├── backtest.py     # Backtesting engine
│   │   └── simulation.py   # Monte Carlo simulations
│   │
│   ├── live/          # Live trading engine, adapters, monitoring
│   │   ├── engine.py       # Async live trading engine
│   │   └── observability.py # OpenTelemetry instrumentation
│   │
│   └── native/        # (optional) Rust/C++ behind clean interfaces
│       ├── orderbook/      # High-performance order book
│       └── sim/            # Fast simulation loops
│
├── tests/             # Test suite
├── pyproject.toml     # Project metadata + tool configs
└── README.md          # This file


## Quick Start

### Installation

bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install core dependencies
uv pip install -e .

# Install development dependencies
uv pip install -e ".[dev]"


### Development Workflow

bash
# Format and lint code
ruff format src/ tests/
ruff check src/ tests/ --fix

# Type checking
pyright src/

# Run tests
pytest

# Run tests with coverage
pytest --cov

# Run only fast tests
pytest -m "not slow"

# Security scan
bandit -r src/
pip-audit


## Core Concepts

### 1. Utility Functions

The system supports multiple utility functions for different trading objectives:

- **Log Utility (Kelly)**: Maximize long-run growth, minimize ruin risk
- **Target Utility**: Maximize probability of hitting a wealth target
- **Hybrid**: Combine approaches based on market regime

### 2. Policy Interface

All trading strategies implement the `Policy` protocol:

python
class Policy(Protocol):
    def decide(
        self,
        portfolio: PortfolioState,
        snapshot: MarketSnapshot,
        context: ContextMap | None = None,
    ) -> OrderSeq:
        """Generate orders given current state."""
        ...


### 3. Execution Abstraction

The `ExecutionEngine` protocol allows swapping between:
- Paper trading
- Real broker connections
- Simulated execution
- Native (Rust/C++) implementations

### 4. Data Pipeline

Polars-first data pipeline with:
- Parquet storage (zstd compression)
- DuckDB for ad-hoc SQL analytics
- Zero-copy operations where possible

### 5. Broker Integration

Production-ready broker adapters with real-time streaming:

**Supported Brokers & Assets:**
- **Alpaca** (US Stocks + Crypto) - Real-time SSE streaming, commission-free
  - 20+ cryptocurrencies (BTC, ETH, SOL, etc.)
  - 24/7 crypto trading
- **Binance** (Crypto) - High-frequency trading, testnet support
- **Interactive Brokers** (Everything) - Professional trading platform

**Real-Time Event Streaming:**
The system uses Server-Sent Events (SSE) for push-based updates:
- ⚡ < 100ms latency (vs 1000ms polling)
- 📉 Single persistent connection (vs 60+ requests/min)
- 🎯 Never miss events (server pushes all updates)

python
# Stream fills in real-time
adapter = AlpacaAdapter(api_key="...", api_secret="...", paper=True)

async for fill in adapter.stream_fills():
    print(f"Fill: {fill.symbol} @ ${fill.price}")  # Instant notification!


**See:** `SSE_STREAMING_GUIDE.md` for full details

## Configuration

All tool configurations are in `pyproject.toml`:

- **Ruff**: Comprehensive linting rules with sensible defaults
- **Pyright**: Strict type checking enabled
- **Pytest**: Async support, coverage, benchmarking
- **Coverage**: Branch coverage with detailed reports

## Performance Philosophy

1. **Python first**: Write everything in Python initially
2. **Profile**: Use `py-spy` or `scalene` to find actual bottlenecks
3. **Vectorize**: Use Polars expressions for data operations
4. **Native last**: Only rewrite in Rust/C++ when profiling proves it necessary

The "genius" layer (your edge, your alpha) stays in Python for maximum flexibility.

## Security

- Pin all dependencies in `uv.lock`
- Run `pip-audit` regularly for CVE scanning
- Use `bandit` for security linting
- Never commit secrets (use environment variables)
- Validate all external data with `msgspec` schemas

## Testing Strategy

- **Unit tests**: Fast, isolated tests for core logic
- **Integration tests**: Test component interactions
- **Benchmarks**: Track performance regressions
- **Property tests**: Use hypothesis for edge cases (optional)

## Observability

Production deployment uses OpenTelemetry for:
- **Traces**: Request flow through the system
- **Metrics**: Order latency, fill rates, PnL
- **Logs**: Structured JSON logs with context

## License

MIT

## Contributing

This is a research/personal project. Core principles:
1. Keep it simple - avoid over-engineering
2. Make changes only when clearly necessary
3. Optimize for research velocity, not premature optimization
4. Security first - validate all external inputs

## Resources

- [uv documentation](https://github.com/astral-sh/uv)
- [Polars guide](https://pola-rs.github.io/polars-book/)
- [ruff rules](https://docs.astral.sh/ruff/rules/)
- [msgspec guide](https://jcristharif.com/msgspec/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
