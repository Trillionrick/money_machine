"""Paper trading adapter - test strategies in real-time without risk.

Paper trading simulates real trading with live data but without real money.
This is essential for validating strategies before going live.
"""

import asyncio
from collections.abc import AsyncIterator
import time

import msgspec
import structlog

from src.core.execution import (
    Fill,
    Order,
    OrderSeq,
    Side,
)
from src.core.types import Quantity, Symbol

log = structlog.get_logger()


class PaperTradingEngine:
    """Paper trading execution engine.

    Simulates order execution with:
    - Realistic fill simulation
    - Position tracking
    - Fill event streaming

    Example:
        >>> engine = PaperTradingEngine(initial_cash=100_000.0)
        >>> await engine.submit_orders([order1, order2])
        >>> positions = await engine.get_positions()
    """

    def __init__(
        self,
        initial_cash: float = 100_000.0,
        *,
        fill_delay_ms: float = 50.0,
        slippage_bps: float = 5.0,
    ) -> None:
        """Initialize paper trading engine.

        Args:
            initial_cash: Starting capital
            fill_delay_ms: Simulated execution delay
            slippage_bps: Simulated slippage in basis points
        """
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.fill_delay_ms = fill_delay_ms
        self.slippage_bps = slippage_bps

        # State
        self.positions: dict[Symbol, Quantity] = {}
        self.open_orders: dict[str, Order] = {}
        self.order_counter = 0

        # Fill queue for streaming
        self.fill_queue: asyncio.Queue[Fill] = asyncio.Queue()

        # Current prices (would come from data feed in production)
        self.current_prices: dict[Symbol, float] = {}

    async def submit_orders(self, orders: OrderSeq) -> None:
        """Submit orders for execution.

        Args:
            orders: Orders to submit
        """
        for order in orders:
            # Assign order ID
            order_id = f"paper_{self.order_counter}"
            self.order_counter += 1

            # Create order with ID
            order_with_id = msgspec.structs.replace(order, id=order_id)

            # Store open order
            self.open_orders[order_id] = order_with_id

            # Schedule fill simulation
            asyncio.create_task(self._simulate_fill(order_with_id))

            log.info(
                "order.submitted",
                order_id=order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
            )

    async def _simulate_fill(self, order: Order) -> None:
        """Simulate order fill with delay and slippage."""
        # Simulate execution delay
        await asyncio.sleep(self.fill_delay_ms / 1000.0)

        # Check if order was cancelled
        if order.id not in self.open_orders:
            return

        # Get current price
        price = self.current_prices.get(order.symbol)
        if price is None:
            # No price available - reject order
            log.warning("order.rejected", order_id=order.id, reason="no_price")
            del self.open_orders[order.id]
            return

        # Calculate fill price with slippage
        fill_price = self._calculate_fill_price(order, price)

        # Execute the fill
        notional = order.quantity * fill_price
        fee = notional * 0.001  # 10 bps fee

        # Update positions and cash
        if order.side == Side.BUY:
            total_cost = notional + fee

            if total_cost > self.cash:
                # Insufficient funds
                log.warning("order.rejected", order_id=order.id, reason="insufficient_funds")
                del self.open_orders[order.id]
                return

            self.cash -= total_cost
            self.positions[order.symbol] = (
                self.positions.get(order.symbol, 0.0) + order.quantity
            )

        else:  # SELL
            current_pos = self.positions.get(order.symbol, 0.0)
            quantity = min(order.quantity, current_pos)

            if quantity < 0.01:
                # Cannot sell what we don't have
                log.warning("order.rejected", order_id=order.id, reason="insufficient_position")
                del self.open_orders[order.id]
                return

            notional = quantity * fill_price
            fee = notional * 0.001

            self.cash += notional - fee
            self.positions[order.symbol] = current_pos - quantity

            # Clean up zero positions
            if abs(self.positions[order.symbol]) < 1e-6:
                del self.positions[order.symbol]

        # Remove from open orders
        del self.open_orders[order.id]

        # Create fill
        fill = Fill(
            order_id=order.id or "unknown",
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            timestamp=time.time_ns(),
            fee=fee,
        )

        # Add to queue
        await self.fill_queue.put(fill)

        log.info(
            "order.filled",
            order_id=order.id,
            symbol=order.symbol,
            quantity=order.quantity,
            price=fill_price,
            fee=fee,
        )

    def _calculate_fill_price(self, order: Order, mid_price: float) -> float:
        """Calculate fill price with simulated slippage."""
        slippage = mid_price * (self.slippage_bps / 10_000.0)

        if order.side == Side.BUY:
            # Pay the ask (mid + slippage)
            return mid_price + slippage
        # Receive the bid (mid - slippage)
        return mid_price - slippage

    async def cancel_order(self, order_id: str) -> None:
        """Cancel an open order.

        Args:
            order_id: ID of order to cancel
        """
        if order_id in self.open_orders:
            del self.open_orders[order_id]
            log.info("order.cancelled", order_id=order_id)

    async def cancel_all_orders(self, symbol: Symbol | None = None) -> None:
        """Cancel all open orders.

        Args:
            symbol: If provided, only cancel orders for this symbol
        """
        to_cancel = []

        for order_id, order in self.open_orders.items():
            if symbol is None or order.symbol == symbol:
                to_cancel.append(order_id)

        for order_id in to_cancel:
            await self.cancel_order(order_id)

    async def get_open_orders(self, symbol: Symbol | None = None) -> OrderSeq:
        """Get all open orders.

        Args:
            symbol: If provided, only return orders for this symbol

        Returns:
            Sequence of open orders
        """
        if symbol is None:
            return list(self.open_orders.values())

        return [o for o in self.open_orders.values() if o.symbol == symbol]

    async def get_positions(self) -> dict[Symbol, Quantity]:
        """Get current positions.

        Returns:
            Dictionary of symbol -> quantity
        """
        return self.positions.copy()

    async def stream_fills(self) -> AsyncIterator[Fill]:
        """Stream execution fills as they occur.

        Yields:
            Fill objects as orders execute
        """
        while True:
            fill = await self.fill_queue.get()
            yield fill

    def update_prices(self, prices: dict[Symbol, float]) -> None:
        """Update current market prices.

        Args:
            prices: Dictionary of symbol -> price
        """
        self.current_prices.update(prices)

    def get_equity(self) -> float:
        """Calculate current equity.

        Returns:
            Total equity (cash + positions value)
        """
        positions_value = sum(
            qty * self.current_prices.get(sym, 0.0)
            for sym, qty in self.positions.items()
        )
        return self.cash + positions_value

    def reset(self) -> None:
        """Reset to initial state."""
        self.cash = self.initial_cash
        self.positions.clear()
        self.open_orders.clear()
        self.order_counter = 0
        # Don't clear fill_queue as it might be in use
