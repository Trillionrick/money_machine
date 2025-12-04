"""Execution layer: orders, fills, and execution engine protocol.

This module defines the core types and protocols for order execution.
Uses msgspec for high-performance serialization (10-100x faster than dataclasses).
"""

from collections.abc import AsyncIterator, Sequence
from enum import StrEnum
from typing import Protocol

import msgspec

from src.core.types import Price, Quantity, Symbol, Timestamp


class Side(StrEnum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    """Order type."""

    LIMIT = "limit"
    MARKET = "market"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class Order(msgspec.Struct, frozen=True, kw_only=True):
    """Immutable order representation.

    Uses msgspec.Struct for zero-copy serialization, much faster than
    dataclasses or Pydantic for high-frequency operations.

    Attributes:
        symbol: Trading symbol (e.g., "AAPL", "BTC/USD")
        side: BUY or SELL
        quantity: Order size
        price: Limit price (None for market orders)
        order_type: Type of order
        id: Optional order ID (assigned by exchange)
        timestamp: Order creation time (nanosecond epoch)
    """

    symbol: Symbol
    side: Side
    quantity: Quantity
    order_type: OrderType = OrderType.LIMIT
    price: Price | None = None
    id: str | None = None
    timestamp: Timestamp | None = None


class Fill(msgspec.Struct, frozen=True, kw_only=True):
    """Immutable fill (execution) representation.

    Attributes:
        order_id: ID of the order that was filled
        symbol: Trading symbol
        side: BUY or SELL
        quantity: Filled quantity
        price: Execution price
        timestamp: Fill time (nanosecond epoch)
        fee: Execution fee/commission
    """

    order_id: str
    symbol: Symbol
    side: Side
    quantity: Quantity
    price: Price
    timestamp: Timestamp
    fee: float = 0.0


# Type aliases for sequences
type OrderSeq = Sequence[Order]
type FillSeq = Sequence[Fill]


class ExecutionEngine(Protocol):
    """Protocol for execution backends.

    This protocol allows swapping between different execution implementations:
    - Paper trading for testing
    - Live broker connections (IBKR, Alpaca, etc.)
    - Simulated execution for backtesting
    - Native (Rust/C++) implementations for performance

    All methods are async to support high-performance event-driven architectures.
    """

    async def submit_orders(self, orders: OrderSeq) -> None:
        """Submit one or more orders for execution.

        Args:
            orders: Sequence of orders to submit

        Raises:
            ExecutionError: If order submission fails
        """
        ...

    async def cancel_order(self, order_id: str) -> None:
        """Cancel an open order.

        Args:
            order_id: ID of the order to cancel

        Raises:
            ExecutionError: If order not found or cancellation fails
        """
        ...

    async def cancel_all_orders(self, symbol: Symbol | None = None) -> None:
        """Cancel all open orders, optionally filtered by symbol.

        Args:
            symbol: If provided, only cancel orders for this symbol
        """
        ...

    async def get_open_orders(self, symbol: Symbol | None = None) -> OrderSeq:
        """Get all open orders.

        Args:
            symbol: If provided, only return orders for this symbol

        Returns:
            Sequence of open orders
        """
        ...

    async def get_positions(self) -> dict[Symbol, Quantity]:
        """Get current positions.

        Returns:
            Dictionary mapping symbols to position sizes (negative for short)
        """
        ...

    async def stream_fills(self) -> AsyncIterator[Fill]:
        """Stream execution fills as they occur.

        Yields:
            Fill objects as orders are executed
        """
        ...

    async def get_account(self) -> dict[str, float]:
        """Get account information (optional, not all engines support this).

        Returns:
            Dictionary with keys like 'cash', 'equity', 'buying_power'.
            May raise NotImplementedError if engine doesn't support account queries.
        """
        ...


class ExecutionError(Exception):
    """Base exception for execution errors."""



class OrderRejectedError(ExecutionError):
    """Raised when an order is rejected by the exchange."""



class InsufficientFundsError(ExecutionError):
    """Raised when there are insufficient funds for an order."""

