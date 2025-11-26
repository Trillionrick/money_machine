"""Binance adapter for crypto trading.

Binance offers:
- Spot trading (buy/sell crypto)
- Futures (leverage up to 125x)
- Large liquidity
- Low fees

Get API keys: https://www.binance.com/en/my/settings/api-management
"""

import asyncio
import time
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


class BinanceAdapter:
    """Binance adapter for crypto trading.

    Example:
        >>> adapter = BinanceAdapter(
        ...     api_key="YOUR_KEY",
        ...     api_secret="YOUR_SECRET",
        ...     testnet=True,  # Start with testnet!
        ... )
        >>> await adapter.submit_orders([order])
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        testnet: bool = True,
    ) -> None:
        """Initialize Binance adapter.

        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            testnet: Use testnet (True) or mainnet (False)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet

        # Import here to make it optional
        try:
            from binance.client import Client
            from binance.exceptions import BinanceAPIException

            self.Client = Client
            self.BinanceAPIException = BinanceAPIException

        except ImportError as e:
            msg = (
                "Binance SDK not installed. Install with: "
                "uv pip install python-binance"
            )
            raise ImportError(msg) from e

        # Initialize client
        self.client = self.Client(
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
        )

        log.info(
            "binance.initialized",
            testnet=testnet,
        )

    async def submit_orders(self, orders: OrderSeq) -> None:
        """Submit orders to Binance.

        Args:
            orders: Orders to submit
        """
        for order in orders:
            try:
                await self._submit_single_order(order)
            except Exception:
                log.exception(
                    "binance.order_failed",
                    symbol=order.symbol,
                    side=order.side,
                )

    async def _submit_single_order(self, order: Order) -> None:
        """Submit single order to Binance."""
        # Binance symbol format: BTCUSDT (no slash)
        symbol = order.symbol.replace("/", "")

        # Binance side
        side = "BUY" if order.side == Side.BUY else "SELL"

        # Get symbol info for precision
        loop = asyncio.get_event_loop()
        symbol_info = await loop.run_in_executor(
            None,
            self.client.get_symbol_info,
            symbol,
        )

        # Round quantity to correct precision
        quantity_precision = None
        for f in symbol_info["filters"]:
            if f["filterType"] == "LOT_SIZE":
                # Find precision from stepSize
                step = float(f["stepSize"])
                quantity_precision = len(str(step).rstrip("0").split(".")[-1])
                break

        if quantity_precision is not None:
            quantity = round(order.quantity, quantity_precision)
        else:
            quantity = order.quantity

        # Submit order
        if order.order_type == OrderType.MARKET:
            result = await loop.run_in_executor(
                None,
                lambda: self.client.create_order(
                    symbol=symbol,
                    side=side,
                    type="MARKET",
                    quantity=quantity,
                ),
            )
        else:  # LIMIT
            if order.price is None:
                log.error("binance.limit_order_no_price", symbol=order.symbol)
                return

            result = await loop.run_in_executor(
                None,
                lambda: self.client.create_order(
                    symbol=symbol,
                    side=side,
                    type="LIMIT",
                    timeInForce="GTC",  # Good til cancelled
                    quantity=quantity,
                    price=order.price,
                ),
            )

        log.info(
            "binance.order_submitted",
            symbol=order.symbol,
            side=order.side,
            quantity=quantity,
            binance_order_id=result["orderId"],
        )

    async def cancel_order(self, order_id: str) -> None:
        """Cancel order by ID.

        Args:
            order_id: Binance order ID (format: "SYMBOL:ORDER_ID")
        """
        symbol, binance_order_id = order_id.split(":")
        loop = asyncio.get_event_loop()

        await loop.run_in_executor(
            None,
            lambda: self.client.cancel_order(
                symbol=symbol,
                orderId=binance_order_id,
            ),
        )

        log.info("binance.order_cancelled", order_id=order_id)

    async def cancel_all_orders(self, symbol: Symbol | None = None) -> None:
        """Cancel all open orders.

        Args:
            symbol: If provided, only cancel for this symbol
        """
        loop = asyncio.get_event_loop()

        if symbol:
            binance_symbol = symbol.replace("/", "")
            await loop.run_in_executor(
                None,
                lambda: self.client.cancel_open_orders(symbol=binance_symbol),
            )
        else:
            # Cancel all symbols
            open_orders = await self.get_open_orders()
            for order in open_orders:
                await self.cancel_order(order.id)

        log.info("binance.orders_cancelled", symbol=symbol or "all")

    async def get_open_orders(self, symbol: Symbol | None = None) -> OrderSeq:
        """Get open orders.

        Args:
            symbol: If provided, only return for this symbol

        Returns:
            List of open orders
        """
        loop = asyncio.get_event_loop()

        if symbol:
            binance_symbol = symbol.replace("/", "")
            binance_orders = await loop.run_in_executor(
                None,
                lambda: self.client.get_open_orders(symbol=binance_symbol),
            )
        else:
            binance_orders = await loop.run_in_executor(
                None,
                self.client.get_open_orders,
            )

        # Convert to our Order type
        orders = []
        for bo in binance_orders:
            # Add slash back to symbol
            our_symbol = f"{bo['symbol'][:-4]}/{bo['symbol'][-4:]}"

            orders.append(
                Order(
                    symbol=our_symbol,
                    side=Side.BUY if bo["side"] == "BUY" else Side.SELL,
                    quantity=float(bo["origQty"]),
                    price=float(bo["price"]) if bo["price"] != "0" else None,
                    order_type=OrderType.LIMIT if bo["type"] == "LIMIT" else OrderType.MARKET,
                    id=f"{bo['symbol']}:{bo['orderId']}",
                )
            )

        return orders

    async def get_positions(self) -> dict[Symbol, Quantity]:
        """Get current positions (balances).

        Returns:
            Dictionary of symbol -> quantity
        """
        loop = asyncio.get_event_loop()
        account = await loop.run_in_executor(
            None,
            self.client.get_account,
        )

        positions = {}
        for balance in account["balances"]:
            free = float(balance["free"])
            locked = float(balance["locked"])
            total = free + locked

            if total > 0:
                symbol = balance["asset"]
                positions[symbol] = total

        return positions

    async def stream_fills(self) -> AsyncIterator[Fill]:
        """Stream fills via websocket.

        Yields:
            Fill objects as orders execute
        """
        # This would use Binance websocket in production
        # For now, poll for filled orders
        seen_orders = set()

        while True:
            await asyncio.sleep(1.0)

            try:
                loop = asyncio.get_event_loop()
                # Get recent trades
                trades = await loop.run_in_executor(
                    None,
                    lambda: self.client.get_my_trades(limit=50),
                )

                for trade in trades:
                    trade_id = trade["id"]
                    if trade_id in seen_orders:
                        continue

                    seen_orders.add(trade_id)

                    # Convert symbol
                    symbol = trade["symbol"]
                    our_symbol = f"{symbol[:-4]}/{symbol[-4:]}"

                    fill = Fill(
                        order_id=f"{symbol}:{trade['orderId']}",
                        symbol=our_symbol,
                        side=Side.BUY if trade["isBuyer"] else Side.SELL,
                        quantity=float(trade["qty"]),
                        price=float(trade["price"]),
                        timestamp=int(trade["time"] * 1e6),  # ms to ns
                        fee=float(trade["commission"]),
                    )

                    yield fill

            except Exception:
                log.exception("binance.stream_fills_error")
                await asyncio.sleep(5.0)

    async def get_account(self) -> dict:
        """Get account information.

        Returns:
            Dictionary with balances
        """
        loop = asyncio.get_event_loop()
        account = await loop.run_in_executor(
            None,
            self.client.get_account,
        )

        return {
            "can_trade": account["canTrade"],
            "can_withdraw": account["canWithdraw"],
            "can_deposit": account["canDeposit"],
            "balances": account["balances"],
        }

    async def get_ticker_price(self, symbol: str) -> float:
        """Get the latest traded price for a symbol (e.g., ETHUSDC)."""
        loop = asyncio.get_event_loop()
        ticker = await loop.run_in_executor(
            None,
            lambda: self.client.get_symbol_ticker(symbol=symbol),
        )
        return float(ticker["price"])
