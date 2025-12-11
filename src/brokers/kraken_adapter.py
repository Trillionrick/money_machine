"""Kraken crypto exchange adapter.

Kraken offers:
- 200+ cryptocurrencies
- Fiat pairs (USD, EUR, GBP, CAD)
- High security and regulatory compliance
- Competitive fees (0.16% maker, 0.26% taker)

Get API keys: https://www.kraken.com/u/security/api
"""

import asyncio
import base64
import hashlib
import hmac
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog

from src.core.execution import Fill, Order, OrderSeq, OrderType, Side
from src.core.types import Quantity, Symbol

log = structlog.get_logger()


class KrakenAdapter:
    """Kraken exchange adapter implementing ExecutionEngine protocol.

    Example:
        >>> from src.brokers.credentials import BrokerCredentials
        >>> creds = BrokerCredentials()
        >>> adapter = KrakenAdapter(
        ...     api_key=creds.kraken_api_key.get_secret_value(),
        ...     api_secret=creds.kraken_api_secret.get_secret_value(),
        ... )
        >>> await adapter.get_account()
    """

    # API endpoints by category (from Kraken docs)
    PUBLIC_ENDPOINTS = {
        "Time",
        "Assets",
        "AssetPairs",
        "Ticker",
        "OHLC",
        "Depth",
        "Trades",
        "Spread",
        "SystemStatus",
    }

    PRIVATE_ENDPOINTS = {
        "Balance",
        "BalanceEx",
        "TradeBalance",
        "OpenOrders",
        "ClosedOrders",
        "QueryOrders",
        "TradesHistory",
        "QueryTrades",
        "OpenPositions",
        "Ledgers",
        "QueryLedgers",
        "TradeVolume",
        "GetWebSocketsToken",
    }

    TRADING_ENDPOINTS = {
        "AddOrder",
        "AddOrderBatch",
        "EditOrder",
        "CancelOrder",
        "CancelOrderBatch",
        "CancelAll",
        "CancelAllOrdersAfter",
    }

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        base_url: str = "https://api.kraken.com",
    ) -> None:
        """Initialize Kraken adapter.

        Args:
            api_key: Kraken API public key
            api_secret: Kraken API private (secret) key
            base_url: API base URL (default: production)
        """
        self.api_key = api_key
        self.api_secret = base64.b64decode(api_secret)
        self.base_url = base_url

        # Create async HTTP client with connection pooling
        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            headers={"User-Agent": "Kraken-Trading-Bot/2025"},
        )

        log.info("kraken.initialized", base_url=base_url)

    def _generate_signature(
        self, url_path: str, data: dict[str, Any], nonce: str
    ) -> str:
        """Generate HMAC-SHA512 signature for private API calls.

        Args:
            url_path: API endpoint path (e.g., "/0/private/Balance")
            data: Request parameters including nonce
            nonce: Unique nonce (timestamp in milliseconds)

        Returns:
            Base64-encoded signature
        """
        # Encode POST data
        postdata = "&".join([f"{k}={v}" for k, v in data.items()])

        # Create SHA256 hash of nonce + postdata
        message = nonce.encode() + postdata.encode()
        sha256_hash = hashlib.sha256(message).digest()

        # Create HMAC-SHA512 signature
        signature = hmac.new(
            self.api_secret,
            url_path.encode() + sha256_hash,
            hashlib.sha512,
        )

        return base64.b64encode(signature.digest()).decode()

    async def _request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        private: bool = False,
    ) -> dict[str, Any]:
        """Make API request to Kraken.

        Args:
            endpoint: API endpoint name (e.g., "Balance", "Ticker")
            params: Request parameters
            private: Whether this is a private API call

        Returns:
            API response data

        Raises:
            Exception: If API returns error
        """
        params = params or {}

        if private:
            # Private API call - requires authentication
            url_path = f"/0/private/{endpoint}"
            nonce = str(int(time.time() * 1000))
            params["nonce"] = nonce

            # Generate signature
            signature = self._generate_signature(url_path, params, nonce)

            headers = {
                "API-Key": self.api_key,
                "API-Sign": signature,
            }

            response = await self.client.post(
                url_path,
                data=params,
                headers=headers,
            )
        else:
            # Public API call - no authentication
            url_path = f"/0/public/{endpoint}"
            response = await self.client.get(url_path, params=params)

        response.raise_for_status()
        data = response.json()

        # Check for API errors
        if data.get("error"):
            error_msg = ", ".join(data["error"])
            raise Exception(f"Kraken API error: {error_msg}")

        return data.get("result", {})

    async def get_server_time(self) -> int:
        """Get Kraken server time (for testing connectivity).

        Returns:
            Unix timestamp in seconds
        """
        result = await self._request("Time")
        return result["unixtime"]

    async def get_account(self) -> dict[str, Any]:
        """Get account balances.

        Returns:
            Dictionary of asset balances
        """
        balances = await self._request("Balance", private=True)

        log.info("kraken.account.fetched", asset_count=len(balances))
        return balances

    async def get_trade_balance(self, asset: str = "ZUSD") -> dict[str, Any]:
        """Get trade balance summary.

        Args:
            asset: Base asset for balance (default: ZUSD = USD)

        Returns:
            Trade balance including equity, margin, etc.
        """
        result = await self._request(
            "TradeBalance",
            params={"asset": asset},
            private=True,
        )
        return result

    async def get_ticker(self, pair: str) -> dict[str, Any]:
        """Get ticker information for a trading pair.

        Args:
            pair: Trading pair (e.g., "XXBTZUSD" for BTC/USD)

        Returns:
            Ticker data including price, volume, etc.
        """
        result = await self._request("Ticker", params={"pair": pair})
        return result

    async def get_positions(self) -> list[dict[str, Any]]:
        """Get open positions.

        Returns:
            List of open positions
        """
        try:
            positions = await self._request("OpenPositions", private=True)
            return list(positions.values()) if positions else []
        except Exception as e:
            # No open positions returns error - that's OK
            if "No positions found" in str(e):
                return []
            raise

    async def submit_orders(self, orders: OrderSeq) -> None:
        """Submit orders to Kraken.

        Args:
            orders: Orders to submit
        """
        for order in orders:
            await self._submit_single_order(order)

    async def _submit_single_order(self, order: Order) -> str:
        """Submit a single order to Kraken.

        Args:
            order: Order to submit

        Returns:
            Order ID (txid)
        """
        # Convert symbol format (e.g., "BTC/USD" -> "XXBTZUSD")
        pair = self._convert_symbol_to_kraken(order.symbol)

        # Build order parameters
        params = {
            "pair": pair,
            "type": "buy" if order.side == Side.BUY else "sell",
            "ordertype": self._convert_order_type(order.order_type),
            "volume": str(order.quantity),
        }

        # Add price for limit orders
        price = getattr(order, "price", None)
        if order.order_type == OrderType.LIMIT and price is not None:
            params["price"] = str(price)

        # Add leverage if specified
        leverage = getattr(order, "leverage", None)
        if leverage and leverage > 1.0:
            params["leverage"] = str(int(leverage))

        # Submit order
        result = await self._request("AddOrder", params=params, private=True)

        txids = result.get("txid") or []
        if not txids:
            msg = "Kraken did not return a txid for submitted order"
            raise RuntimeError(msg)
        txid = str(txids[0])
        log.info(
            "kraken.order.submitted",
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            txid=txid,
        )

        return txid

    async def cancel_order(self, order_id: str) -> None:
        """Cancel an order.

        Args:
            order_id: Order ID (txid) to cancel
        """
        await self._request(
            "CancelOrder",
            params={"txid": order_id},
            private=True,
        )
        log.info("kraken.order.cancelled", order_id=order_id)

    async def get_orders(self, *, status: str = "open") -> list[dict[str, Any]]:
        """Get orders by status.

        Args:
            status: Order status ("open" or "closed")

        Returns:
            List of orders
        """
        endpoint = "OpenOrders" if status == "open" else "ClosedOrders"
        result = await self._request(endpoint, private=True)

        # Extract orders from response
        orders = result.get("open" if status == "open" else "closed", {})
        return list(orders.values()) if orders else []

    async def stream_fills(self) -> AsyncIterator[Fill]:
        """Stream order fills in real-time.

        Note: Kraken doesn't have SSE, so this polls for new fills.
        For production, consider using WebSocket API.

        Yields:
            Fill objects as they occur
        """
        last_check = time.time()
        seen_trades = set()

        while True:
            try:
                # Get recent trades
                trades = await self._request("TradesHistory", private=True)

                for trade_id, trade in trades.get("trades", {}).items():
                    if trade_id not in seen_trades:
                        seen_trades.add(trade_id)

                        # Convert to Fill object
                        fill = Fill(
                            order_id=str(trade.get("ordertxid") or trade_id),
                            symbol=self._convert_kraken_to_symbol(trade["pair"]),
                            quantity=float(trade["vol"]),
                            price=float(trade["price"]),
                            side=Side.BUY if trade["type"] == "buy" else Side.SELL,
                            timestamp=int(trade["time"] * 1_000_000_000),
                        )

                        yield fill

                # Poll every 2 seconds
                await asyncio.sleep(2.0)

            except Exception as e:
                log.error("kraken.stream_fills.error", error=str(e))
                await asyncio.sleep(5.0)  # Longer wait on error

    def _convert_symbol_to_kraken(self, symbol: Symbol) -> str:
        """Convert standard symbol to Kraken format.

        Args:
            symbol: Standard symbol (e.g., "BTC/USD")

        Returns:
            Kraken pair format (e.g., "XXBTZUSD")
        """
        # Common conversions
        conversions = {
            "BTC/USD": "XXBTZUSD",
            "ETH/USD": "XETHZUSD",
            "SOL/USD": "SOLUSD",
            "DOGE/USD": "XDGUSD",
            "XRP/USD": "XXRPZUSD",
            "ADA/USD": "ADAUSD",
            "DOT/USD": "DOTUSD",
        }

        return conversions.get(symbol, symbol.replace("/", ""))

    def _convert_kraken_to_symbol(self, pair: str) -> Symbol:
        """Convert Kraken pair to standard symbol.

        Args:
            pair: Kraken pair (e.g., "XXBTZUSD")

        Returns:
            Standard symbol (e.g., "BTC/USD")
        """
        # Reverse conversions
        conversions = {
            "XXBTZUSD": "BTC/USD",
            "XETHZUSD": "ETH/USD",
            "SOLUSD": "SOL/USD",
            "XDGUSD": "DOGE/USD",
            "XXRPZUSD": "XRP/USD",
            "ADAUSD": "ADA/USD",
            "DOTUSD": "DOT/USD",
        }

        return conversions.get(pair, pair)

    def _convert_order_type(self, order_type: OrderType) -> str:
        """Convert OrderType to Kraken format.

        Args:
            order_type: Order type

        Returns:
            Kraken order type string
        """
        mapping = {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
        }
        return mapping[order_type]

    async def close(self) -> None:
        """Close HTTP client connection."""
        await self.client.aclose()
        log.info("kraken.closed")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
