"""Real-time SSE streaming for Alpaca events.

Provides low-latency event streams for:
- Trade events (fills, order status changes)
- Account status updates
- Non-trade activities (dividends, splits, etc.)

Uses Alpaca's SSE API for push-based updates instead of polling.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog
from httpx_sse import aconnect_sse

from src.core.execution import Fill, Side

log = structlog.get_logger()


class ReconnectStrategy:
    """Exponential backoff reconnection strategy.

    Example:
        >>> strategy = ReconnectStrategy()
        >>> while True:
        ...     try:
        ...         await connect()
        ...         strategy.reset()  # Success!
        ...     except Exception:
        ...         await strategy.wait()  # Exponential backoff
    """

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        factor: float = 2.0,
    ) -> None:
        """Initialize reconnection strategy.

        Args:
            base_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds
            factor: Multiplication factor for each retry
        """
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.factor = factor
        self.attempts = 0

    async def wait(self) -> None:
        """Wait with exponential backoff based on attempts."""
        delay = min(self.base_delay * (self.factor**self.attempts), self.max_delay)
        self.attempts += 1
        log.info(
            "reconnect.waiting",
            delay=delay,
            attempts=self.attempts,
        )
        await asyncio.sleep(delay)

    def reset(self) -> None:
        """Reset backoff counter after successful connection."""
        if self.attempts > 0:
            log.info("reconnect.reset", previous_attempts=self.attempts)
        self.attempts = 0


class AlpacaSSEClient:
    """Client for Alpaca's Server-Sent Events API.

    Example:
        >>> client = AlpacaSSEClient(api_key="...", api_secret="...", paper=True)
        >>> async for event in client.stream_trade_events():
        ...     print(f"Event: {event['event']} for {event['order']['symbol']}")
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        paper: bool = True,
    ) -> None:
        """Initialize SSE client.

        Args:
            api_key: Alpaca API key
            api_secret: Alpaca API secret
            paper: Use paper trading endpoint
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.paper = paper

        # Base URL for SSE endpoints
        if paper:
            self.base_url = "https://broker-api.sandbox.alpaca.markets"
        else:
            self.base_url = "https://broker-api.alpaca.markets"

        # Headers for authentication
        self.headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
        }

        log.info("alpaca_sse.initialized", paper=paper, base_url=self.base_url)

    async def stream_trade_events(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream trade events (fills, order status changes) in real-time.

        Args:
            since: Start from this timestamp (RFC3339 format) or ULID
            until: End at this timestamp (RFC3339 format) or ULID

        Yields:
            Trade event dictionaries with structure:
                {
                    "event_id": "01HCMKNJK1Y0R7VF6Q6CAC3SH7",
                    "event": "fill",  # or "new", "canceled", etc.
                    "at": "2023-10-13T13:30:00.673857Z",
                    "order": {...},  # Full order object
                    "price": "181.36",
                    "qty": "0.05513895",
                    ...
                }
        """
        # Use v2beta1 endpoint for ULID support
        url = f"{self.base_url}/v2beta1/events/trades"

        # Build query params
        params = {}
        if since:
            params["since"] = since
        if until:
            params["until"] = until

        log.info("alpaca_sse.connecting", url=url, params=params)

        try:
            async with httpx.AsyncClient() as client:
                async with aconnect_sse(
                    client,
                    "GET",
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=None,  # Keep connection open indefinitely
                ) as event_source:
                    log.info("alpaca_sse.connected")

                    async for sse in event_source.aiter_sse():
                        # Skip heartbeat messages
                        if not sse.data or sse.data.strip() == "":
                            continue

                        # Skip comment messages (start with :)
                        if sse.data.startswith(":"):
                            log.debug("alpaca_sse.comment", message=sse.data)
                            continue

                        try:
                            # Parse JSON event
                            event = json.loads(sse.data)
                            yield event

                        except json.JSONDecodeError:
                            log.warning(
                                "alpaca_sse.invalid_json",
                                data=sse.data[:100],
                            )
                            continue

        except httpx.HTTPError as e:
            log.error("alpaca_sse.connection_error", error=str(e))
            raise
        except Exception:
            log.exception("alpaca_sse.unexpected_error")
            raise

    async def stream_account_status(
        self,
        *,
        since: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream account status change events.

        Args:
            since: Start from this timestamp or ULID

        Yields:
            Account status events with structure:
                {
                    "account_id": "...",
                    "event_id": "01HCMKXS94ST351NFGEZR57EHV",
                    "at": "2023-10-13T13:34:29.668043Z",
                    "status_from": "APPROVED",
                    "status_to": "ACTIVE",
                    ...
                }
        """
        url = f"{self.base_url}/v1/events/accounts/status"
        params = {"since_ulid": since} if since else {}

        log.info("alpaca_sse.connecting_account_status", url=url)

        async with httpx.AsyncClient() as client:
            async with aconnect_sse(
                client,
                "GET",
                url,
                headers=self.headers,
                params=params,
                timeout=None,
            ) as event_source:
                async for sse in event_source.aiter_sse():
                    if not sse.data or sse.data.strip() == "" or sse.data.startswith(":"):
                        continue

                    try:
                        event = json.loads(sse.data)
                        yield event
                    except json.JSONDecodeError:
                        continue

    async def stream_nta_events(
        self,
        *,
        since: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream non-trade activity events (dividends, splits, etc.).

        Args:
            since: Start from this timestamp or ULID

        Yields:
            NTA events (DIV, SPLIT, etc.)
        """
        url = f"{self.base_url}/v1/events/nta"
        params = {"since_ulid": since} if since else {}

        log.info("alpaca_sse.connecting_nta", url=url)

        async with httpx.AsyncClient() as client:
            async with aconnect_sse(
                client,
                "GET",
                url,
                headers=self.headers,
                params=params,
                timeout=None,
            ) as event_source:
                async for sse in event_source.aiter_sse():
                    if not sse.data or sse.data.strip() == "" or sse.data.startswith(":"):
                        continue

                    try:
                        event = json.loads(sse.data)
                        yield event
                    except json.JSONDecodeError:
                        continue


async def convert_trade_event_to_fill(event: dict[str, Any]) -> Fill | None:
    """Convert Alpaca trade event to Fill object.

    Args:
        event: Trade event from SSE stream

    Returns:
        Fill object if event is a fill, None otherwise
    """
    # Only process fill events
    if event.get("event") != "fill":
        return None

    order = event.get("order", {})
    symbol = order.get("symbol")
    if not symbol:
        return None

    # Parse quantities and prices
    try:
        qty = float(event.get("qty", 0))
        price = float(event.get("price", 0))
        position_qty = float(event.get("position_qty", 0))

        # Determine side from order
        side_str = order.get("side", "").lower()
        side = Side.BUY if side_str == "buy" else Side.SELL

        # Parse timestamp
        filled_at = order.get("filled_at")
        if filled_at:
            from datetime import datetime

            dt = datetime.fromisoformat(filled_at.replace("Z", "+00:00"))
            timestamp = int(dt.timestamp() * 1e9)
        else:
            timestamp = time.time_ns()

        # Create fill
        fill = Fill(
            order_id=order.get("id", ""),
            symbol=symbol,
            side=side,
            quantity=qty,
            price=price,
            timestamp=timestamp,
            fee=0.0,  # Alpaca is commission-free
        )

        return fill

    except (ValueError, TypeError) as e:
        log.warning("alpaca_sse.fill_conversion_error", error=str(e), event=event)
        return None
