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
from typing import TYPE_CHECKING, Protocol, cast

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


class AlpacaOrderModel(Protocol):
    id: str | object  # UUID in real API
    symbol: str | None
    side: object | None  # Enum or string depending on SDK version
    qty: float | str | None
    limit_price: float | str | None
    filled_qty: float | str | None
    filled_avg_price: float | str | None
    filled_at: object | None


class AlpacaPositionModel(Protocol):
    symbol: str
    qty: float | str


class AlpacaTradeAccountModel(Protocol):
    cash: float | str | None
    equity: float | str | None
    buying_power: float | str | None
    pattern_day_trader: bool | None


if TYPE_CHECKING:
    from alpaca.trading.models import Order as AlpacaOrder  # pragma: no cover
    from alpaca.trading.models import Position as AlpacaPosition  # pragma: no cover
    from alpaca.trading.models import TradeAccount as AlpacaTradeAccount  # pragma: no cover
else:  # Provide runtime names without importing optional dependency
    AlpacaOrder = AlpacaOrderModel
    AlpacaPosition = AlpacaPositionModel
    AlpacaTradeAccount = AlpacaTradeAccountModel


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
                GetOrdersRequest,
            )
            from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce

            self.TradingClient = TradingClient
            self.MarketOrderRequest = MarketOrderRequest
            self.LimitOrderRequest = LimitOrderRequest
            self.GetOrdersRequest = GetOrdersRequest
            self.OrderSide = OrderSide
            self.QueryOrderStatus = QueryOrderStatus
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

    def _to_side(self, raw_side: object) -> Side:
        """Normalize Alpaca side enums/strings to our Side enum."""
        if raw_side == self.OrderSide.BUY:
            return Side.BUY
        if raw_side == self.OrderSide.SELL:
            return Side.SELL

        side_str = str(raw_side).lower()
        if "buy" in side_str:
            return Side.BUY
        return Side.SELL

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
            alpaca_order_id=cast(AlpacaOrder, alpaca_order).id,
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
            request = self.GetOrdersRequest(status=self.QueryOrderStatus.OPEN)
            orders = await loop.run_in_executor(
                None,
                lambda: self.client.get_orders(request),
            )
            for order in orders:
                alpaca_order = cast(AlpacaOrder, order)
                if alpaca_order.symbol == symbol:
                    await self.cancel_order(str(alpaca_order.id))
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
        request = (
            self.GetOrdersRequest(
                status=self.QueryOrderStatus.OPEN,
                symbols=[symbol] if symbol else None,
            )
        )
        alpaca_orders = await loop.run_in_executor(
            None,
            lambda: self.client.get_orders(request),
        )

        # Convert to our Order type
        orders = []
        for ao in alpaca_orders:
            alpaca_order = cast(AlpacaOrder, ao)
            if not alpaca_order.symbol:
                continue  # Skip malformed broker responses

            # Extract and validate quantity
            qty_raw = alpaca_order.qty
            if qty_raw is None:
                continue  # Skip orders with no quantity
            quantity = float(qty_raw)

            # Extract limit price if present
            limit_price_raw = alpaca_order.limit_price
            limit_price: float | None = (
                float(limit_price_raw)
                if limit_price_raw is not None
                else None
            )

            orders.append(
                Order(
                    symbol=str(alpaca_order.symbol),
                    side=self._to_side(alpaca_order.side),
                    quantity=quantity,
                    price=limit_price,
                    order_type=(
                        OrderType.LIMIT if limit_price is not None else OrderType.MARKET
                    ),
                    id=str(alpaca_order.id),
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
            alpaca_pos = cast(AlpacaPosition, pos)
            positions[alpaca_pos.symbol] = float(alpaca_pos.qty)

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
                    lambda: self.client.get_orders(
                        self.GetOrdersRequest(status=self.QueryOrderStatus.CLOSED)
                    ),
                )

                for order in filled_orders:
                    alpaca_order = cast(AlpacaOrder, order)

                    if alpaca_order.id in seen_orders:
                        continue

                    # Validate filled quantity and price
                    filled_qty = alpaca_order.filled_qty
                    filled_price = alpaca_order.filled_avg_price

                    if filled_qty is None or filled_price is None:
                        continue  # Skip incomplete fills

                    # Validate symbol
                    if alpaca_order.symbol is None:
                        continue  # Skip fills without symbol

                    seen_orders.add(alpaca_order.id)

                    # Create fill
                    fill = Fill(
                        order_id=str(alpaca_order.id),
                        symbol=alpaca_order.symbol,
                        side=self._to_side(alpaca_order.side),
                        quantity=float(filled_qty),
                        price=float(filled_price),
                        timestamp=int(
                            alpaca_order.filled_at.timestamp() * 1e9  # type: ignore[attr-defined]
                        ),
                        fee=0.0,  # Alpaca is commission-free
                    )

                    yield fill

            except Exception:
                log.exception("alpaca.stream_fills_error")
                await asyncio.sleep(5.0)

    async def get_account(self) -> dict[str, float | bool]:
        """Get account information.

        Returns:
            Dictionary with cash, equity, buying_power
        """
        loop = asyncio.get_running_loop()
        account_raw = await loop.run_in_executor(
            None,
            self.client.get_account,
        )
        account = cast(AlpacaTradeAccount, account_raw)

        # Handle potential None values from API
        cash = account.cash if account.cash is not None else 0.0
        equity = account.equity if account.equity is not None else 0.0
        buying_power = account.buying_power if account.buying_power is not None else 0.0

        return {
            "cash": float(cash),
            "equity": float(equity),
            "buying_power": float(buying_power),
            "pattern_day_trader": bool(account.pattern_day_trader if account.pattern_day_trader is not None else False),
        }
