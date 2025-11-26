"""Policy interface: the "brain" of the trading system.

This module defines the Policy protocol - the core abstraction for trading strategies.
A Policy takes market data and portfolio state, then decides what orders to generate.

The key insight: we're not just "finding good trades", we're designing payoff structures
where small equity controls large optionality with structurally positive drift.
"""

from typing import Protocol

import msgspec
import polars as pl

from src.core.execution import OrderSeq
from src.core.types import ContextMap, Price, Quantity, Symbol, Timestamp


class PortfolioState(msgspec.Struct, frozen=True, kw_only=True):
    """Immutable snapshot of portfolio state.

    Attributes:
        positions: Current positions (negative for short)
        cash: Available cash
        equity: Total equity (cash + position values)
        timestamp: State timestamp (nanosecond epoch)
        margin_used: Margin currently in use
        margin_available: Available margin
    """

    positions: dict[Symbol, Quantity]
    cash: float
    equity: float
    timestamp: Timestamp
    margin_used: float = 0.0
    margin_available: float = 0.0

    def position(self, symbol: Symbol) -> Quantity:
        """Get position for a symbol (0 if not held)."""
        return self.positions.get(symbol, 0.0)

    def is_long(self, symbol: Symbol) -> bool:
        """Check if we have a long position."""
        return self.position(symbol) > 0

    def is_short(self, symbol: Symbol) -> bool:
        """Check if we have a short position."""
        return self.position(symbol) < 0

    def is_flat(self, symbol: Symbol) -> bool:
        """Check if we have no position."""
        return self.position(symbol) == 0


class MarketSnapshot(msgspec.Struct, frozen=True, kw_only=True):
    """Immutable snapshot of market data at a point in time.

    Attributes:
        timestamp: Snapshot timestamp (nanosecond epoch)
        prices: Current prices for each symbol
        volumes: Recent volumes for each symbol
        features: Optional DataFrame with derived features (signals, indicators, etc.)
        regime: Optional market regime indicator ("bull", "bear", "neutral", etc.)
    """

    timestamp: Timestamp
    prices: dict[Symbol, Price]
    volumes: dict[Symbol, float]
    features: pl.DataFrame | None = None
    regime: str | None = None

    def price(self, symbol: Symbol) -> Price | None:
        """Get price for a symbol."""
        return self.prices.get(symbol)


class Policy(Protocol):
    """Abstract policy interface - implement this for your trading strategy.

    The Policy is the "genius" layer - your edge, your alpha. This is where
    the mathematical intelligence lives.

    Key design principle: A Policy should be:
    1. Stateless (or manage its own state explicitly)
    2. Deterministic given the same inputs
    3. Fast (called on every market update in live trading)
    4. Testable (pure function from state -> orders)

    Example policies:
    - Mean reversion with Kelly sizing
    - Momentum following with target-hitting utility
    - Market making with inventory management
    - Statistical arbitrage with regime switching
    """

    def decide(
        self,
        portfolio: PortfolioState,
        snapshot: MarketSnapshot,
        context: ContextMap | None = None,
    ) -> OrderSeq:
        """Generate orders given current state.

        This is the core method called by the trading engine.

        Args:
            portfolio: Current portfolio state
            snapshot: Current market data
            context: Optional additional context (model predictions, etc.)

        Returns:
            Sequence of orders to submit (may be empty)

        Note:
            This method should NOT have side effects. State management
            should be handled in on_fill() or external state stores.
        """
        ...

    def on_fill(self, fill: msgspec.Struct) -> None:
        """Optional callback when an order is filled.

        Use this to update internal state, log executions, etc.

        Args:
            fill: The fill that occurred
        """
        ...


class ModelPrediction(msgspec.Struct, frozen=True, kw_only=True):
    """Model prediction for a symbol.

    This is a standard interface between ML models and policies.

    Attributes:
        symbol: Symbol being predicted
        expected_return: Expected return (μ)
        return_variance: Return variance (σ²)
        confidence: Prediction confidence [0, 1]
        regime: Optional market regime
        horizon: Prediction horizon in seconds
    """

    symbol: Symbol
    expected_return: float
    return_variance: float
    confidence: float
    regime: str | None = None
    horizon: int | None = None

    def sharpe_estimate(self) -> float:
        """Estimate Sharpe ratio from prediction."""
        if self.return_variance <= 0:
            return 0.0
        return self.expected_return / (self.return_variance**0.5)


class SimplePolicy:
    """Example policy implementation showing the pattern.

    This is a minimal example - real policies would have more sophistication.
    """

    def __init__(self, target_symbols: list[Symbol], *, kelly_fraction: float = 0.25) -> None:
        """Initialize policy.

        Args:
            target_symbols: Symbols to trade
            kelly_fraction: Fraction of Kelly sizing to use (0.25 = quarter Kelly)
        """
        self.target_symbols = target_symbols
        self.kelly_fraction = kelly_fraction

    def decide(
        self,
        _portfolio: PortfolioState,
        _snapshot: MarketSnapshot,
        _context: ContextMap | None = None,
    ) -> OrderSeq:
        """Generate orders (example implementation)."""
        # Real implementation would go here
        # This is just a skeleton to show the interface
        return []

    def on_fill(self, _fill: msgspec.Struct) -> None:
        """Handle fill (example implementation)."""
        # Real implementation would log, update state, etc.
