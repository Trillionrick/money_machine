"""OANDA v20 REST API broker adapter for forex trading.

OANDA offers:
- 120+ forex pairs, metals, commodities, indices
- No commission (spread-based pricing)
- Fractional pip pricing (5 decimals for most pairs)
- 50:1 leverage for forex (varies by jurisdiction)
- Professional-grade execution

Get API credentials: https://www.oanda.com/account/tpa/personal_token
API docs: https://developer.oanda.com/rest-live-v20/introduction/
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import httpx
import structlog

from src.brokers.oanda_config import (
    OandaConfig,
    denormalize_instrument_name,
    get_instrument_precision,
    normalize_instrument_name,
)
from src.core.execution import (
    ExecutionError,
    Fill,
    InsufficientFundsError,
    Order,
    OrderRejectedError,
    OrderSeq,
    OrderType,
    Side,
)
from src.core.types import Quantity, Symbol

log = structlog.get_logger()


class OandaAdapter:
    """OANDA v20 REST API adapter implementing ExecutionEngine protocol.

    This adapter integrates OANDA forex trading into the multi-broker
    abstraction layer, treating forex pairs as synthetic instruments
    alongside crypto.

    OANDA-specific handling:
    - Transaction IDs are strings (not integers like most exchanges)
    - Prices use Decimal for precision (5 decimals for most pairs)
    - Instruments use underscore notation (EUR_USD not EUR/USD)
    - Units are signed (positive=long, negative=short) vs side parameter
    - No native order books; only streaming bid/ask spreads
    - Weekend gaps: Markets close Friday 17:00 ET, reopen Sunday 17:00 ET

    Example:
        >>> from src.brokers.oanda_config import OandaConfig
        >>> config = OandaConfig.from_env()
        >>> adapter = OandaAdapter(config)
        >>> await adapter.get_account()
        >>> await adapter.submit_orders([order])
    """

    def __init__(self, config: OandaConfig) -> None:
        """Initialize OANDA adapter.

        Args:
            config: OANDA configuration with credentials and settings
        """
        self.config = config
        self.account_id = config.oanda_account_id
        self.base_url = config.get_base_url()
        self.stream_url = config.get_stream_url()

        # Create async HTTP client with HTTP/2 multiplexing
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(config.connection_timeout),
            limits=httpx.Limits(
                max_keepalive_connections=config.max_keepalive_connections,
                max_connections=config.max_connections,
            ),
            headers={
                "Authorization": f"Bearer {config.oanda_token.get_secret_value()}",
                "Content-Type": "application/json",
                "Accept-Datetime-Format": "UNIX",  # Unix timestamps instead of RFC3339
            },
            http2=True,  # Enable HTTP/2 for multiplexing
        )

        # Separate client for streaming (long-lived connections)
        self.stream_client = httpx.AsyncClient(
            base_url=self.stream_url,
            timeout=httpx.Timeout(None),  # No timeout for streaming
            headers={
                "Authorization": f"Bearer {config.oanda_token.get_secret_value()}",
                "Accept-Datetime-Format": "UNIX",
            },
            http2=True,
        )

        # Rate limiter state
        self._request_times: list[float] = []
        self._rate_limit_lock = asyncio.Lock()
        self._instrument_cache: dict[str, dict[str, Any]] = {}

        log.info(
            "oanda.initialized",
            environment=config.oanda_environment.value,
            account_id=self.account_id,
            base_url=self.base_url,
        )

    async def _rate_limit(self) -> None:
        """Adaptive rate limiting to avoid hitting OANDA's undocumented limits.

        OANDA doesn't publish explicit rate limits, so we use a conservative
        sliding window approach with exponential backoff on errors.
        """
        async with self._rate_limit_lock:
            now = asyncio.get_event_loop().time()
            window = 1.0  # 1 second window

            # Remove requests outside the window
            self._request_times = [t for t in self._request_times if now - t < window]

            # If at limit, wait
            if len(self._request_times) >= self.config.max_requests_per_second:
                wait_time = window - (now - self._request_times[0])
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                    now = asyncio.get_event_loop().time()
                    self._request_times = [
                        t for t in self._request_times if now - t < window
                    ]

            self._request_times.append(now)

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make rate-limited API request to OANDA.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path (e.g., "/v3/accounts/{accountID}/orders")
            params: Query parameters
            json: JSON request body

        Returns:
            API response data

        Raises:
            ExecutionError: If API returns error
        """
        await self._rate_limit()

        # Replace {accountID} placeholder
        endpoint = endpoint.replace("{accountID}", self.account_id)

        try:
            response = await self.client.request(
                method=method,
                url=endpoint,
                params=params,
                json=json,
            )

            # Handle rate limiting (429)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "5"))
                log.warning("oanda.rate_limited", retry_after=retry_after)
                await asyncio.sleep(retry_after)
                # Retry request
                return await self._request(method, endpoint, params=params, json=json)

            response.raise_for_status()
            data = response.json()

            # OANDA returns different structures; extract relevant data
            return data

        except httpx.HTTPStatusError as e:
            # Parse OANDA error response
            error_data = e.response.json() if e.response.text else {}
            error_msg = error_data.get("errorMessage", str(e))
            error_code = error_data.get("errorCode", "UNKNOWN")

            log.error(
                "oanda.api_error",
                status_code=e.response.status_code,
                error_code=error_code,
                error_message=error_msg,
                endpoint=endpoint,
            )

            # Map OANDA errors to our exception types
            if "INSUFFICIENT" in error_code or "margin" in error_msg.lower():
                raise InsufficientFundsError(error_msg) from e
            if "REJECT" in error_code or "invalid" in error_msg.lower():
                raise OrderRejectedError(error_msg) from e

            raise ExecutionError(f"OANDA API error: {error_msg}") from e

        except Exception as e:
            log.exception("oanda.request_failed", endpoint=endpoint)
            raise ExecutionError(f"Request failed: {e}") from e

    async def get_account(self) -> dict[str, Any]:
        """Get account summary including balance, equity, margin.

        Returns:
            Dictionary with account information:
            - balance: Account balance
            - unrealized_pl: Unrealized P&L
            - nav: Net asset value
            - margin_used: Used margin
            - margin_available: Available margin
            - position_value: Total position value
        """
        data = await self._request("GET", f"/v3/accounts/{self.account_id}")
        account = data.get("account", {})

        log.info(
            "oanda.account.fetched",
            balance=account.get("balance"),
            currency=account.get("currency"),
            open_positions=account.get("openPositionCount", 0),
        )

        return {
            "balance": Decimal(account.get("balance", "0")),
            "unrealized_pl": Decimal(account.get("unrealizedPL", "0")),
            "nav": Decimal(account.get("NAV", "0")),
            "margin_used": Decimal(account.get("marginUsed", "0")),
            "margin_available": Decimal(account.get("marginAvailable", "0")),
            "position_value": Decimal(account.get("positionValue", "0")),
            "currency": account.get("currency", "USD"),
        }

    async def get_instruments(self) -> list[dict[str, Any]]:
        """Get tradeable instruments for this account.

        Instrument availability depends on regulatory jurisdiction.
        Use this for runtime instrument discovery.

        Returns:
            List of instrument metadata
        """
        data = await self._request(
            "GET",
            f"/v3/accounts/{self.account_id}/instruments",
        )
        instruments = data.get("instruments", [])

        log.info("oanda.instruments.fetched", count=len(instruments))
        return instruments

    async def _get_instrument_metadata(self, instrument: str) -> dict[str, Any] | None:
        """Fetch and cache instrument metadata."""
        if instrument in self._instrument_cache:
            return self._instrument_cache[instrument]

        try:
            instruments = await self.get_instruments()
        except Exception:
            log.warning("oanda.instrument_lookup_failed", instrument=instrument)
            return None

        for meta in instruments:
            name = meta.get("name")
            if name:
                self._instrument_cache[name] = meta

        return self._instrument_cache.get(instrument)

    async def _prepare_units(self, order: Order, instrument: str) -> tuple[Decimal, int]:
        """Validate and round order units to OANDA requirements."""
        meta = await self._get_instrument_metadata(instrument)
        precision = int(meta.get("tradeUnitsPrecision", 0)) if meta else 0
        if meta:
            min_units_raw = meta.get("minimumTradeSize") or meta.get("minimumOrderUnits")
        else:
            min_units_raw = None
        min_units = Decimal(str(min_units_raw)) if min_units_raw is not None else Decimal("1")

        step = Decimal("1").scaleb(-precision)
        signed_units = Decimal(str(order.quantity))
        if order.side == Side.SELL:
            signed_units = -signed_units

        rounded_units = signed_units.quantize(step, rounding=ROUND_HALF_UP)

        if rounded_units == 0:
            msg = f"Order size rounds to 0 units for {instrument} at precision {precision}"
            raise OrderRejectedError(msg)

        if abs(rounded_units) < min_units:
            msg = (
                f"Order size {abs(rounded_units)} below minimum {min_units} for {instrument}"
            )
            raise OrderRejectedError(msg)

        return rounded_units, precision

    async def _get_reference_price(self, instrument: str) -> Decimal | None:
        """Fetch latest mid-price for margin estimation."""
        try:
            data = await self._request(
                "GET",
                f"/v3/accounts/{self.account_id}/pricing",
                params={"instruments": instrument},
            )
        except Exception:
            log.warning("oanda.price_lookup_failed", instrument=instrument)
            return None

        prices = data.get("prices", [])
        if not prices:
            return None

        price_data = prices[0]
        bid = price_data.get("closeoutBid")
        ask = price_data.get("closeoutAsk")
        if bid is not None and ask is not None:
            return (Decimal(str(bid)) + Decimal(str(ask))) / 2

        bids = price_data.get("bids", [])
        asks = price_data.get("asks", [])
        if bids and asks:
            return (Decimal(str(bids[0].get("price"))) + Decimal(str(asks[0].get("price")))) / 2
        if asks:
            return Decimal(str(asks[0].get("price")))
        if bids:
            return Decimal(str(bids[0].get("price")))

        return None

    async def _precheck_margin(
        self,
        instrument: str,
        units: Decimal,
        price_hint: float | None,
    ) -> None:
        """Validate available margin before submitting the order."""
        meta = await self._get_instrument_metadata(instrument)
        margin_rate = Decimal(str(meta.get("marginRate", "0"))) if meta else Decimal("0")

        if margin_rate == 0:
            log.info("oanda.margin_skip", instrument=instrument, reason="missing_margin_rate")
            return

        if price_hint is not None:
            reference_price = Decimal(str(price_hint))
        else:
            reference_price = await self._get_reference_price(instrument)

        if reference_price is None:
            log.warning("oanda.margin_skip", instrument=instrument, reason="missing_price")
            return

        notional = abs(units) * reference_price
        required_margin = notional * margin_rate
        account = await self.get_account()
        available_margin = account["margin_available"]

        if required_margin > available_margin:
            msg = (
                f"Insufficient margin for {instrument}: "
                f"required {required_margin} > available {available_margin}"
            )
            raise InsufficientFundsError(msg)

        log.info(
            "oanda.margin_precheck",
            instrument=instrument,
            required=float(required_margin),
            available=float(available_margin),
        )

    async def submit_orders(self, orders: OrderSeq) -> None:
        """Submit orders to OANDA.

        OANDA order submission quirks:
        - Uses "units" (signed: positive=long, negative=short) vs side+quantity
        - Supports clientExtensions for order tracking
        - Returns transaction IDs (strings, not integers)

        Args:
            orders: Orders to submit
        """
        for order in orders:
            try:
                await self._submit_single_order(order)
            except Exception:
                log.exception(
                    "oanda.order_failed",
                    symbol=order.symbol,
                    side=order.side,
                    quantity=order.quantity,
                )

    async def _submit_single_order(self, order: Order) -> str:
        """Submit a single order to OANDA.

        Args:
            order: Order to submit

        Returns:
            Order transaction ID (string)
        """
        # Convert symbol to OANDA instrument format
        instrument = normalize_instrument_name(order.symbol)

        # Validate and round units, then ensure margin suffices before sending
        units, unit_precision = await self._prepare_units(order, instrument)
        await self._precheck_margin(instrument, units, order.price)

        # Build order request
        order_spec: dict[str, Any] = {
            "instrument": instrument,
            "units": f"{units:.{unit_precision}f}",  # OANDA wants string representation
            "type": self._convert_order_type(order.order_type),
            "timeInForce": "FOK",  # Fill-or-Kill by default
        }

        # Add price for limit orders
        if order.order_type == OrderType.LIMIT and order.price is not None:
            precision = get_instrument_precision(instrument)
            price_str = f"{Decimal(str(order.price)):.{precision}f}"
            order_spec["price"] = price_str

        # Add stop price for stop orders
        if order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
            if hasattr(order, "stop_price") and order.stop_price is not None:
                precision = get_instrument_precision(instrument)
                stop_str = f"{Decimal(str(order.stop_price)):.{precision}f}"
                order_spec["priceBound"] = stop_str

        # Add client extensions for order tracking
        if order.id:
            order_spec["clientExtensions"] = {
                "id": order.id[:20],  # OANDA max length
                "tag": "money_machine",
            }

        # Submit order
        data = await self._request(
            "POST",
            f"/v3/accounts/{self.account_id}/orders",
            json={"order": order_spec},
        )

        # Extract transaction info
        transaction = data.get("orderCreateTransaction", {})
        order_id = transaction.get("id", "")
        fills = data.get("orderFillTransaction", {})

        log.info(
            "oanda.order.submitted",
            symbol=order.symbol,
            instrument=instrument,
            side=order.side,
            quantity=order.quantity,
            order_id=order_id,
            filled=bool(fills),
        )

        return order_id

    async def cancel_order(self, order_id: str) -> None:
        """Cancel an order by ID.

        Args:
            order_id: OANDA order transaction ID (string)
        """
        await self._request(
            "PUT",
            f"/v3/accounts/{self.account_id}/orders/{order_id}/cancel",
        )
        log.info("oanda.order.cancelled", order_id=order_id)

    async def cancel_all_orders(self, symbol: Symbol | None = None) -> None:
        """Cancel all open orders.

        Args:
            symbol: If provided, only cancel orders for this symbol
        """
        # Get all pending orders
        orders = await self.get_open_orders(symbol=symbol)

        # Cancel each order
        for order in orders:
            if order.id:
                await self.cancel_order(order.id)

        log.info("oanda.orders.cancelled", symbol=symbol or "all", count=len(orders))

    async def get_open_orders(self, symbol: Symbol | None = None) -> OrderSeq:
        """Get open orders.

        Args:
            symbol: If provided, only return orders for this symbol

        Returns:
            List of open orders
        """
        data = await self._request(
            "GET",
            f"/v3/accounts/{self.account_id}/pendingOrders",
        )

        orders_data = data.get("orders", [])

        # Convert to our Order type
        orders = []
        for o in orders_data:
            instrument = o.get("instrument", "")
            order_symbol = denormalize_instrument_name(instrument)

            # Filter by symbol if specified
            if symbol and order_symbol != symbol:
                continue

            # Parse units (signed) to side + quantity
            units = Decimal(o.get("units", "0"))
            side = Side.BUY if units > 0 else Side.SELL
            quantity = abs(float(units))

            orders.append(
                Order(
                    symbol=order_symbol,
                    side=side,
                    quantity=quantity,
                    price=float(o["price"]) if "price" in o else None,
                    order_type=self._parse_order_type(o.get("type", "MARKET")),
                    id=o.get("id"),
                )
            )

        return orders

    async def get_positions(self) -> dict[Symbol, Quantity]:
        """Get current positions.

        OANDA positions are per-instrument nets (not separate long/short like some exchanges).

        Returns:
            Dictionary of symbol -> quantity (negative for short)
        """
        data = await self._request(
            "GET",
            f"/v3/accounts/{self.account_id}/openPositions",
        )

        positions_data = data.get("positions", [])
        positions: dict[Symbol, Quantity] = {}

        for p in positions_data:
            instrument = p.get("instrument", "")
            symbol = denormalize_instrument_name(instrument)

            # OANDA has separate long/short for each instrument
            long_units = Decimal(p.get("long", {}).get("units", "0"))
            short_units = Decimal(p.get("short", {}).get("units", "0"))

            # Net position
            net_units = long_units + short_units  # short_units is negative
            positions[symbol] = float(net_units)

        return positions

    async def close_position(
        self,
        symbol: Symbol,
        *,
        long_units: str | None = "ALL",
        short_units: str | None = "ALL",
    ) -> None:
        """Close position for an instrument.

        OANDA-specific: Uses PUT to close positions (not cancel+reverse).

        Args:
            symbol: Symbol to close
            long_units: Long units to close ("ALL" or specific amount)
            short_units: Short units to close ("ALL" or specific amount)
        """
        instrument = normalize_instrument_name(symbol)

        body: dict[str, Any] = {}
        if long_units:
            body["longUnits"] = long_units
        if short_units:
            body["shortUnits"] = short_units

        data = await self._request(
            "PUT",
            f"/v3/accounts/{self.account_id}/positions/{instrument}/close",
            json=body,
        )

        log.info(
            "oanda.position.closed",
            symbol=symbol,
            instrument=instrument,
            long_fill=data.get("longOrderFillTransaction"),
            short_fill=data.get("shortOrderFillTransaction"),
        )

    async def stream_fills(self) -> AsyncIterator[Fill]:
        """Stream order fills in real-time using OANDA's transaction stream.

        OANDA streams all transactions (orders, fills, position changes, etc.).
        We filter for ORDER_FILL transactions.

        Yields:
            Fill objects as they occur
        """
        from src.brokers.oanda_streaming import OandaStreamingClient

        streaming = OandaStreamingClient(
            config=self.config,
            stream_client=self.stream_client,
        )

        async for fill in streaming.stream_fills():
            yield fill

    def _convert_order_type(self, order_type: OrderType) -> str:
        """Convert OrderType to OANDA format.

        Args:
            order_type: Order type

        Returns:
            OANDA order type string
        """
        mapping = {
            OrderType.MARKET: "MARKET",
            OrderType.LIMIT: "LIMIT",
            OrderType.STOP: "STOP",
            OrderType.STOP_LIMIT: "STOP",  # OANDA doesn't have STOP_LIMIT; use STOP
        }
        return mapping.get(order_type, "MARKET")

    def _parse_order_type(self, oanda_type: str) -> OrderType:
        """Parse OANDA order type to our OrderType.

        Args:
            oanda_type: OANDA order type string

        Returns:
            OrderType enum
        """
        mapping = {
            "MARKET": OrderType.MARKET,
            "LIMIT": OrderType.LIMIT,
            "STOP": OrderType.STOP,
            "MARKET_IF_TOUCHED": OrderType.STOP,
        }
        return mapping.get(oanda_type, OrderType.MARKET)

    async def close(self) -> None:
        """Close HTTP client connections."""
        await self.client.aclose()
        await self.stream_client.aclose()
        log.info("oanda.closed")

    async def __aenter__(self) -> OandaAdapter:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
