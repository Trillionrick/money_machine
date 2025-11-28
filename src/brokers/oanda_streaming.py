"""OANDA v20 streaming API client for real-time prices and transaction events.

OANDA's streaming API provides:
- Real-time pricing updates (bid/ask spreads, no order book)
- Transaction events (orders, fills, position changes)
- Heartbeat messages for connection health monitoring
- Automatic reconnection on disconnect

Streaming endpoints are separate from REST API.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import httpx
import orjson
import structlog

from src.brokers.oanda_config import (
    OandaConfig,
    denormalize_instrument_name,
)
from src.core.execution import Fill, Side
from src.core.types import Symbol

log = structlog.get_logger()


class ReconnectStrategy:
    """Exponential backoff strategy for stream reconnection.

    Follows the same pattern as AlpacaSSEClient reconnection.
    """

    def __init__(
        self,
        *,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        factor: float = 2.0,
    ) -> None:
        """Initialize reconnection strategy.

        Args:
            base_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds
            factor: Exponential backoff factor
        """
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.factor = factor
        self._current_delay = base_delay
        self._attempts = 0

    def reset(self) -> None:
        """Reset backoff state after successful connection."""
        self._current_delay = self.base_delay
        self._attempts = 0

    async def wait(self) -> None:
        """Wait with exponential backoff before reconnecting."""
        await asyncio.sleep(self._current_delay)
        self._attempts += 1
        self._current_delay = min(
            self._current_delay * self.factor,
            self.max_delay,
        )
        log.info(
            "oanda.reconnect.backoff",
            attempt=self._attempts,
            delay=self._current_delay,
        )


class OandaStreamingClient:
    """Client for OANDA's streaming API.

    Handles:
    - Real-time pricing stream (bid/ask updates)
    - Transaction stream (fills, orders, positions)
    - Heartbeat monitoring
    - Automatic reconnection with exponential backoff
    - Deduplication of events during reconnects
    """

    def __init__(
        self,
        config: OandaConfig,
        stream_client: httpx.AsyncClient,
    ) -> None:
        """Initialize streaming client.

        Args:
            config: OANDA configuration
            stream_client: HTTP client configured for streaming
        """
        self.config = config
        self.client = stream_client
        self.account_id = config.oanda_account_id

        # Deduplication tracking
        self._seen_transaction_ids: set[str] = set()
        self._max_seen_size = 10000  # Prevent unbounded growth

        # Heartbeat tracking
        self._last_heartbeat = time.time()
        self._heartbeat_timeout = config.streaming_heartbeat_interval * 3

    async def stream_prices(
        self,
        instruments: list[str],
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream real-time price updates for instruments.

        OANDA streams bid/ask spreads (no order book depth).
        Updates sent at ~250ms intervals or on price change.

        Args:
            instruments: List of OANDA instruments (e.g., ["EUR_USD", "GBP_USD"])

        Yields:
            Price update dictionaries with:
            - type: "PRICE" or "HEARTBEAT"
            - instrument: Instrument name
            - time: Unix timestamp
            - bids: List of bid prices
            - asks: List of ask prices
            - closeoutBid: Bid price for closing long
            - closeoutAsk: Ask price for closing short
        """
        reconnect = ReconnectStrategy(
            base_delay=self.config.streaming_reconnect_delay,
            max_delay=self.config.streaming_max_reconnect_delay,
        )

        instruments_param = ",".join(instruments)

        while True:
            try:
                log.info(
                    "oanda.stream.prices.connecting",
                    instruments=instruments_param,
                )

                async with self.client.stream(
                    "GET",
                    f"/v3/accounts/{self.account_id}/pricing/stream",
                    params={"instruments": instruments_param},
                ) as response:
                    response.raise_for_status()

                    # Successfully connected - reset backoff
                    reconnect.reset()
                    self._last_heartbeat = time.time()

                    log.info(
                        "oanda.stream.prices.connected",
                        instruments=instruments_param,
                    )

                    # Read streaming lines
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue

                        try:
                            data = orjson.loads(line)
                            msg_type = data.get("type")

                            if msg_type == "HEARTBEAT":
                                self._last_heartbeat = time.time()
                                log.debug("oanda.stream.heartbeat")
                                yield data

                            elif msg_type == "PRICE":
                                self._last_heartbeat = time.time()

                                # Check for stale connection
                                if self._is_heartbeat_stale():
                                    log.warning("oanda.stream.heartbeat_stale")
                                    break  # Reconnect

                                yield data

                        except Exception:
                            log.exception("oanda.stream.parse_error", line=line)

            except httpx.HTTPStatusError as e:
                log.error(
                    "oanda.stream.http_error",
                    status=e.response.status_code,
                    error=str(e),
                )
                await reconnect.wait()

            except Exception:
                log.exception("oanda.stream.error")
                await reconnect.wait()

    async def stream_transactions(self) -> AsyncIterator[dict[str, Any]]:
        """Stream transaction events (orders, fills, position changes).

        OANDA streams ALL account transactions in real-time.
        This includes:
        - ORDER_FILL: Order executions
        - MARKET_ORDER: New market orders
        - LIMIT_ORDER: New limit orders
        - STOP_ORDER: New stop orders
        - ORDER_CANCEL: Order cancellations
        - TRADE_CLOSE: Position closures

        Yields:
            Transaction event dictionaries
        """
        reconnect = ReconnectStrategy(
            base_delay=self.config.streaming_reconnect_delay,
            max_delay=self.config.streaming_max_reconnect_delay,
        )

        while True:
            try:
                log.info("oanda.stream.transactions.connecting")

                async with self.client.stream(
                    "GET",
                    f"/v3/accounts/{self.account_id}/transactions/stream",
                ) as response:
                    response.raise_for_status()

                    # Successfully connected
                    reconnect.reset()
                    self._last_heartbeat = time.time()

                    log.info("oanda.stream.transactions.connected")

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue

                        try:
                            data = orjson.loads(line)
                            msg_type = data.get("type")

                            if msg_type == "HEARTBEAT":
                                self._last_heartbeat = time.time()
                                log.debug("oanda.stream.heartbeat")
                                continue

                            # Deduplicate transactions by ID
                            tx_id = data.get("id")
                            if tx_id and tx_id in self._seen_transaction_ids:
                                log.debug(
                                    "oanda.stream.duplicate_transaction",
                                    tx_id=tx_id,
                                )
                                continue

                            if tx_id:
                                self._seen_transaction_ids.add(tx_id)
                                # Prevent unbounded growth
                                if len(self._seen_transaction_ids) > self._max_seen_size:
                                    # Remove oldest half
                                    keep = list(self._seen_transaction_ids)[
                                        self._max_seen_size // 2 :
                                    ]
                                    self._seen_transaction_ids = set(keep)

                            self._last_heartbeat = time.time()
                            yield data

                        except Exception:
                            log.exception("oanda.stream.parse_error", line=line)

            except httpx.HTTPStatusError as e:
                log.error(
                    "oanda.stream.http_error",
                    status=e.response.status_code,
                    error=str(e),
                )
                await reconnect.wait()

            except Exception:
                log.exception("oanda.stream.error")
                await reconnect.wait()

    async def stream_fills(self) -> AsyncIterator[Fill]:
        """Stream order fills by filtering transaction stream.

        Yields:
            Fill objects as orders execute
        """
        async for tx in self.stream_transactions():
            tx_type = tx.get("type")

            if tx_type == "ORDER_FILL":
                # Convert OANDA ORDER_FILL to our Fill type
                fill = self._transaction_to_fill(tx)
                if fill:
                    yield fill

    def _transaction_to_fill(self, tx: dict[str, Any]) -> Fill | None:
        """Convert OANDA ORDER_FILL transaction to Fill.

        Args:
            tx: OANDA transaction dictionary

        Returns:
            Fill object or None if conversion fails
        """
        try:
            instrument = tx.get("instrument", "")
            symbol = denormalize_instrument_name(instrument)

            # Parse units (signed) to side + quantity
            units = Decimal(tx.get("units", "0"))
            side = Side.BUY if units > 0 else Side.SELL
            quantity = abs(float(units))

            # Parse price
            price = float(tx.get("price", "0"))

            # Parse timestamp (OANDA uses Unix timestamps if Accept-Datetime-Format: UNIX)
            timestamp_str = tx.get("time", "0")
            # OANDA returns decimal seconds, we need nanoseconds
            timestamp = int(float(timestamp_str) * 1_000_000_000)

            # Parse fee/commission
            # OANDA doesn't charge commission (spread-based), but may have financing
            financing = float(tx.get("financing", "0"))

            # Order ID from related order transaction
            order_id = tx.get("orderID", tx.get("id", ""))

            return Fill(
                order_id=order_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                timestamp=timestamp,
                fee=abs(financing),  # Financing can be positive or negative
            )

        except Exception:
            log.exception("oanda.fill_conversion_error", transaction=tx)
            return None

    def _is_heartbeat_stale(self) -> bool:
        """Check if heartbeat is stale (connection may be dead).

        Returns:
            True if no heartbeat received within timeout period
        """
        return (time.time() - self._last_heartbeat) > self._heartbeat_timeout


async def fetch_missing_prices(
    client: httpx.AsyncClient,
    account_id: str,
    instruments: list[str],
) -> dict[str, dict[str, Any]]:
    """Fetch current prices via REST API to fill gaps after reconnect.

    When streaming disconnects and reconnects, there may be price gaps.
    This fetches the latest prices via REST to ensure continuity.

    Args:
        client: HTTP client
        account_id: OANDA account ID
        instruments: List of instruments to fetch

    Returns:
        Dictionary mapping instrument -> price data
    """
    instruments_param = ",".join(instruments)

    try:
        response = await client.get(
            f"/v3/accounts/{account_id}/pricing",
            params={"instruments": instruments_param},
        )
        response.raise_for_status()
        data = response.json()

        prices: dict[str, dict[str, Any]] = {}
        for price_data in data.get("prices", []):
            instrument = price_data.get("instrument", "")
            prices[instrument] = price_data

        log.info("oanda.prices.fetched_gap_fill", instruments=len(prices))
        return prices

    except Exception:
        log.exception("oanda.prices.fetch_error")
        return {}
