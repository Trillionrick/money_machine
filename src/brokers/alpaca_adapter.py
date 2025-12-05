"""Alpaca broker adapter for US stocks.

Alpaca offers:
- Free paper trading (perfect for testing)
- Commission-free trading
- Simple REST API
- Real-time data via websocket

Get API keys: https://alpaca.markets
"""

import asyncio
from collections.abc import AsyncIterator

import structlog

from src.core.execution import (
    ExecutionEngine,
    Fill,
    Order,
    OrderSeq,
    OrderType,
    Side,
)
from src.core.types import Quantity, Symbol

log = structlog.get_logger()


class AlpacaAdapter:
    """Alpaca broker adapter implementing ExecutionEngine protocol.

    Example:
        >>> adapter = AlpacaAdapter(
        ...     api_key="YOUR_KEY",
        ...     api_secret="YOUR_SECRET",
        ...     paper=True,  # Start with paper trading!
        ... )
        >>> await adapter.submit_orders([order])
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        paper: bool = True,
    ) -> None:
        """Initialize Alpaca adapter.

        Args:
            api_key: Alpaca API key
            api_secret: Alpaca API secret
            paper: Use paper trading (True) or live (False)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.paper = paper

        # Import here to make it optional
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.trading.requests import (
                MarketOrderRequest,
                LimitOrderRequest,
            )
            from alpaca.trading.enums import OrderSide, TimeInForce

            self.TradingClient = TradingClient
            self.MarketOrderRequest = MarketOrderRequest
            self.LimitOrderRequest = LimitOrderRequest
            self.OrderSide = OrderSide
            self.TimeInForce = TimeInForce

        except ImportError as e:
            msg = (
                "Alpaca SDK not installed. Install with: "
                "uv pip install alpaca-py"
            )
            raise ImportError(msg) from e

        # Initialize client
        self.client = self.TradingClient(
            api_key=api_key,
            secret_key=api_secret,
            paper=paper,
        )

        log.info(
            "alpaca.initialized",
            paper=paper,
            base_url=getattr(self.client, '_base_url', 'unknown'),
        )

    async def submit_orders(self, orders: OrderSeq) -> None:
        """Submit orders to Alpaca.

        Args:
            orders: Orders to submit
        """
        for order in orders:
            try:
                await self._submit_single_order(order)
            except Exception:
                log.exception(
                    "alpaca.order_failed",
                    symbol=order.symbol,
                    side=order.side,
                )

    async def _submit_single_order(self, order: Order) -> None:
        """Submit single order to Alpaca."""
        # Convert our types to Alpaca types
        alpaca_side = (
            self.OrderSide.BUY if order.side == Side.BUY else self.OrderSide.SELL
        )

        # Alpaca requires integer quantities for stocks
        quantity = int(order.quantity)

        if quantity < 1:
            log.warning(
                "alpaca.quantity_too_small",
                symbol=order.symbol,
                quantity=order.quantity,
            )
            return

        # Create order request based on type
        if order.order_type == OrderType.MARKET:
            request = self.MarketOrderRequest(
                symbol=order.symbol,
                qty=quantity,
                side=alpaca_side,
                time_in_force=self.TimeInForce.DAY,
            )
        else:  # LIMIT
            if order.price is None:
                log.error("alpaca.limit_order_no_price", symbol=order.symbol)
                return

            request = self.LimitOrderRequest(
                symbol=order.symbol,
                qty=quantity,
                side=alpaca_side,
                time_in_force=self.TimeInForce.DAY,
                limit_price=float(order.price),
            )

        # Submit (synchronous call, wrap in executor for async)
        loop = asyncio.get_running_loop()
        alpaca_order = await loop.run_in_executor(
            None,
            self.client.submit_order,
            request,
        )

        log.info(
            "alpaca.order_submitted",
            symbol=order.symbol,
            side=order.side,
            quantity=quantity,
            alpaca_order_id=alpaca_order.id,
        )

    async def cancel_order(self, order_id: str) -> None:
        """Cancel order by ID.

        Args:
            order_id: Alpaca order ID
        """
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            self.client.cancel_order_by_id,
            order_id,
        )
        log.info("alpaca.order_cancelled", order_id=order_id)

    async def cancel_all_orders(self, symbol: Symbol | None = None) -> None:
        """Cancel all open orders.

        Args:
            symbol: If provided, only cancel for this symbol
        """
        loop = asyncio.get_running_loop()

        if symbol:
            # Alpaca doesn't have cancel by symbol, so get all and filter
            orders = await loop.run_in_executor(
                None,
                self.client.get_orders,
            )
            for order in orders:
                if order.symbol == symbol:
                    await self.cancel_order(order.id)
        else:
            # Cancel all
            await loop.run_in_executor(
                None,
                self.client.cancel_orders,
            )

        log.info("alpaca.orders_cancelled", symbol=symbol or "all")

    async def get_open_orders(self, symbol: Symbol | None = None) -> OrderSeq:
        """Get open orders.

        Args:
            symbol: If provided, only return for this symbol

        Returns:
            List of open orders
        """
        loop = asyncio.get_running_loop()
        alpaca_orders = await loop.run_in_executor(
            None,
            lambda: self.client.get_orders(
                filter={"symbols": [symbol]} if symbol else None
            ),
        )

        # Convert to our Order type
        orders = []
        for ao in alpaca_orders:
            orders.append(
                Order(
                    symbol=ao.symbol,
                    side=Side.BUY if ao.side == "buy" else Side.SELL,
                    quantity=float(ao.qty),
                    price=float(ao.limit_price) if ao.limit_price else None,
                    order_type=OrderType.LIMIT if ao.limit_price else OrderType.MARKET,
                    id=ao.id,
                )
            )

        return orders

    async def get_positions(self) -> dict[Symbol, Quantity]:
        """Get current positions.

        Returns:
            Dictionary of symbol -> quantity
        """
        loop = asyncio.get_running_loop()
        alpaca_positions = await loop.run_in_executor(
            None,
            self.client.get_all_positions,
        )

        positions = {}
        for pos in alpaca_positions:
            positions[pos.symbol] = float(pos.qty)

        return positions

    async def stream_fills(self) -> AsyncIterator[Fill]:
        """Stream fills as they occur using real-time SSE.

        This uses Alpaca's Server-Sent Events API for push-based updates
        instead of polling. Much lower latency and more efficient.

        Yields:
            Fill objects as trades execute
        """
        # Import SSE client here to keep it optional
        try:
            from src.brokers.alpaca_sse import (
                AlpacaSSEClient,
                convert_trade_event_to_fill,
            )
        except ImportError:
            log.warning(
                "alpaca.sse_unavailable",
                msg="httpx-sse not installed, falling back to polling",
            )
            # Fallback to polling if SSE dependencies not available
            async for fill in self._stream_fills_polling():
                yield fill
            return

        # Create SSE client
        sse_client = AlpacaSSEClient(
            api_key=self.api_key,
            api_secret=self.api_secret,
            paper=self.paper,
        )

        # Stream trade events in real-time
        log.info("alpaca.streaming_fills", method="sse")

        # Import reconnection strategy
        from src.brokers.alpaca_sse import ReconnectStrategy

        reconnect = ReconnectStrategy(base_delay=1.0, max_delay=60.0, factor=2.0)

        while True:
            try:
                async for event in sse_client.stream_trade_events():
                    # Successful event - reset backoff
                    reconnect.reset()

                    # Log event for debugging
                    event_type = event.get("event")
                    order = event.get("order", {})
                    symbol = order.get("symbol", "unknown")

                    log.debug(
                        "alpaca.trade_event",
                        event_type=event_type,
                        symbol=symbol,
                    )

                    # Convert to Fill if it's a fill event
                    fill = await convert_trade_event_to_fill(event)
                    if fill:
                        yield fill

            except Exception:
                log.exception("alpaca.sse_stream_error")
                # Exponential backoff before reconnecting
                await reconnect.wait()
                log.info("alpaca.reconnecting_sse")

    async def _stream_fills_polling(self) -> AsyncIterator[Fill]:
        """Fallback polling implementation if SSE unavailable.

        Yields:
            Fill objects (polled every second)
        """
        seen_orders = set()

        while True:
            await asyncio.sleep(1.0)  # Poll every second

            try:
                loop = asyncio.get_running_loop()
                filled_orders = await loop.run_in_executor(
                    None,
                    lambda: self.client.get_orders(filter={"status": "filled"}),
                )

                for order in filled_orders:
                    if order.id in seen_orders:
                        continue

                    seen_orders.add(order.id)

                    # Create fill
                    fill = Fill(
                        order_id=order.id,
                        symbol=order.symbol,
                        side=Side.BUY if order.side == "buy" else Side.SELL,
                        quantity=float(order.filled_qty),
                        price=float(order.filled_avg_price),
                        timestamp=int(order.filled_at.timestamp() * 1e9),
                        fee=0.0,  # Alpaca is commission-free
                    )

                    yield fill

            except Exception:
                log.exception("alpaca.stream_fills_error")
                await asyncio.sleep(5.0)

    async def get_account(self) -> dict:
        """Get account information.

        Returns:
            Dictionary with cash, equity, buying_power
        """
        loop = asyncio.get_running_loop()
        account = await loop.run_in_executor(
            None,
            self.client.get_account,
        )

        return {
            "cash": float(account.cash),
            "equity": float(account.equity),
            "buying_power": float(account.buying_power),
            "pattern_day_trader": account.pattern_day_trader,
        }
