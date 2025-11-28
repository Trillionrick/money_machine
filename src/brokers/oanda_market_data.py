"""OANDA v20 market data client for historical candles and pricing.

Provides:
- Historical OHLCV candle data
- Pagination for large historical ranges (5000 candle limit per request)
- Multiple timeframes (S5, M1, M5, H1, D, etc.)
- Weekend gap handling (forex markets close Fri 17:00 ET, reopen Sun 17:00 ET)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any

import httpx
import structlog

from src.brokers.oanda_config import (
    OandaConfig,
    denormalize_instrument_name,
    normalize_instrument_name,
)

log = structlog.get_logger()


class CandleGranularity(StrEnum):
    """OANDA candle granularities (timeframes).

    OANDA uses abbreviated format:
    - S = seconds
    - M = minutes
    - H = hours
    - D = day
    - W = week
    - M (trailing) = month
    """

    S5 = "S5"  # 5 seconds
    S10 = "S10"  # 10 seconds
    S15 = "S15"  # 15 seconds
    S30 = "S30"  # 30 seconds
    M1 = "M1"  # 1 minute
    M2 = "M2"  # 2 minutes
    M4 = "M4"  # 4 minutes
    M5 = "M5"  # 5 minutes
    M10 = "M10"  # 10 minutes
    M15 = "M15"  # 15 minutes
    M30 = "M30"  # 30 minutes
    H1 = "H1"  # 1 hour
    H2 = "H2"  # 2 hours
    H3 = "H3"  # 3 hours
    H4 = "H4"  # 4 hours
    H6 = "H6"  # 6 hours
    H8 = "H8"  # 8 hours
    H12 = "H12"  # 12 hours
    D = "D"  # 1 day
    W = "W"  # 1 week
    M = "M"  # 1 month


class PriceComponent(StrEnum):
    """Price component for candles.

    OANDA provides separate OHLC for mid, bid, and ask.
    """

    MID = "M"  # Midpoint between bid and ask (default)
    BID = "B"  # Bid prices
    ASK = "A"  # Ask prices
    BA = "BA"  # Both bid and ask
    MBA = "MBA"  # Mid, bid, and ask


class OandaMarketData:
    """Client for OANDA market data (candles, pricing).

    Handles:
    - Historical candle fetching with pagination
    - Multiple price components (mid/bid/ask)
    - Weekend gap detection and handling
    - Alignment for daily candles (17:00 ET)
    """

    def __init__(
        self,
        config: OandaConfig,
        client: httpx.AsyncClient,
    ) -> None:
        """Initialize market data client.

        Args:
            config: OANDA configuration
            client: HTTP client for REST API
        """
        self.config = config
        self.client = client
        self.account_id = config.oanda_account_id
        self.max_candles = config.max_candles_per_request

    async def get_candles(
        self,
        instrument: str,
        *,
        granularity: CandleGranularity = CandleGranularity.H1,
        count: int | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        price: PriceComponent = PriceComponent.MID,
        smooth: bool = False,
        include_first: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch historical candles for an instrument.

        OANDA limits responses to 5000 candles per request.
        For larger ranges, use get_candles_paginated().

        Args:
            instrument: OANDA instrument (e.g., "EUR_USD")
            granularity: Candle timeframe
            count: Number of candles (max 5000)
            from_time: Start time (UTC datetime)
            to_time: End time (UTC datetime)
            price: Price component (mid/bid/ask)
            smooth: Whether to smooth candles
            include_first: Include first query candle

        Returns:
            List of candle dictionaries with OHLCV data

        Raises:
            ValueError: If invalid parameters
        """
        # Normalize instrument format
        instrument = normalize_instrument_name(instrument)

        # Build query parameters
        params: dict[str, Any] = {
            "granularity": granularity.value,
            "price": price.value,
        }

        # OANDA requires either count OR from/to (not both)
        if count is not None:
            if count > self.max_candles:
                log.warning(
                    "oanda.candles.count_limited",
                    requested=count,
                    max=self.max_candles,
                )
                count = self.max_candles
            params["count"] = count
        else:
            if from_time:
                params["from"] = self._datetime_to_rfc3339(from_time)
            if to_time:
                params["to"] = self._datetime_to_rfc3339(to_time)

        if smooth:
            params["smooth"] = "true"

        if not include_first:
            params["includeFirst"] = "false"

        # Fetch candles
        try:
            response = await self.client.get(
                f"/v3/instruments/{instrument}/candles",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            candles = data.get("candles", [])

            log.info(
                "oanda.candles.fetched",
                instrument=instrument,
                granularity=granularity.value,
                count=len(candles),
            )

            return candles

        except httpx.HTTPStatusError as e:
            log.error(
                "oanda.candles.error",
                status=e.response.status_code,
                error=str(e),
                instrument=instrument,
            )
            raise

    async def get_candles_paginated(
        self,
        instrument: str,
        *,
        granularity: CandleGranularity = CandleGranularity.H1,
        from_time: datetime,
        to_time: datetime,
        price: PriceComponent = PriceComponent.MID,
    ) -> list[dict[str, Any]]:
        """Fetch candles with automatic pagination for large time ranges.

        OANDA limits responses to 5000 candles. This method automatically
        paginates to fetch the entire range.

        Args:
            instrument: OANDA instrument (e.g., "EUR_USD")
            granularity: Candle timeframe
            from_time: Start time (UTC datetime)
            to_time: End time (UTC datetime)
            price: Price component (mid/bid/ask)

        Returns:
            List of all candles in range (can be >5000)
        """
        all_candles: list[dict[str, Any]] = []
        current_from = from_time

        while current_from < to_time:
            # Fetch batch
            candles = await self.get_candles(
                instrument,
                granularity=granularity,
                from_time=current_from,
                to_time=to_time,
                price=price,
                include_first=len(all_candles) == 0,  # Only include first on first batch
            )

            if not candles:
                break

            all_candles.extend(candles)

            # Update from_time for next batch
            last_candle = candles[-1]
            last_time_str = last_candle.get("time", "")
            current_from = self._rfc3339_to_datetime(last_time_str)

            # If we got fewer than max, we're done
            if len(candles) < self.max_candles:
                break

            # Small delay to avoid rate limits
            await asyncio.sleep(0.1)

        log.info(
            "oanda.candles.paginated",
            instrument=instrument,
            granularity=granularity.value,
            total_candles=len(all_candles),
            from_time=from_time.isoformat(),
            to_time=to_time.isoformat(),
        )

        return all_candles

    async def get_latest_candles(
        self,
        instrument: str,
        *,
        granularity: CandleGranularity = CandleGranularity.H1,
        count: int = 100,
        price: PriceComponent = PriceComponent.MID,
    ) -> list[dict[str, Any]]:
        """Fetch most recent candles for an instrument.

        Convenience method for getting latest N candles.

        Args:
            instrument: OANDA instrument (e.g., "EUR_USD")
            granularity: Candle timeframe
            count: Number of recent candles (max 5000)
            price: Price component (mid/bid/ask)

        Returns:
            List of recent candles
        """
        return await self.get_candles(
            instrument,
            granularity=granularity,
            count=count,
            price=price,
        )

    def normalize_candles(
        self,
        candles: list[dict[str, Any]],
        price_component: PriceComponent = PriceComponent.MID,
    ) -> list[dict[str, Any]]:
        """Normalize OANDA candle format to standard OHLCV.

        OANDA returns nested structures with mid/bid/ask components.
        This extracts the specified component and flattens the structure.

        Args:
            candles: Raw OANDA candles
            price_component: Which price to extract (mid/bid/ask)

        Returns:
            Normalized candles with flat OHLCV structure
        """
        normalized = []

        for candle in candles:
            if not candle.get("complete", False):
                # Skip incomplete candles (current forming candle)
                continue

            # Extract price component
            price_key = price_component.value.lower()
            if price_key not in candle:
                log.warning(
                    "oanda.candles.missing_component",
                    component=price_key,
                    available=list(candle.keys()),
                )
                continue

            price_data = candle[price_key]

            normalized.append(
                {
                    "time": candle["time"],
                    "volume": int(candle.get("volume", 0)),
                    "open": Decimal(price_data["o"]),
                    "high": Decimal(price_data["h"]),
                    "low": Decimal(price_data["l"]),
                    "close": Decimal(price_data["c"]),
                }
            )

        return normalized

    def detect_weekend_gaps(
        self,
        candles: list[dict[str, Any]],
        granularity: CandleGranularity,
    ) -> list[tuple[datetime, datetime]]:
        """Detect weekend gaps in candle data.

        Forex markets close Friday 17:00 ET and reopen Sunday 17:00 ET.
        This identifies gaps longer than expected for the granularity.

        Args:
            candles: Normalized candles
            granularity: Candle timeframe

        Returns:
            List of (gap_start, gap_end) datetime tuples
        """
        gaps: list[tuple[datetime, datetime]] = []

        # Calculate expected time between candles
        expected_delta = self._granularity_to_seconds(granularity)

        for i in range(len(candles) - 1):
            current_time = self._rfc3339_to_datetime(candles[i]["time"])
            next_time = self._rfc3339_to_datetime(candles[i + 1]["time"])

            delta = (next_time - current_time).total_seconds()

            # If gap is significantly larger than expected, it's likely a weekend
            if delta > expected_delta * 2:
                gaps.append((current_time, next_time))
                log.debug(
                    "oanda.weekend_gap_detected",
                    gap_start=current_time.isoformat(),
                    gap_end=next_time.isoformat(),
                    gap_hours=delta / 3600,
                )

        return gaps

    def _granularity_to_seconds(self, granularity: CandleGranularity) -> int:
        """Convert granularity to seconds.

        Args:
            granularity: Candle timeframe

        Returns:
            Number of seconds per candle
        """
        mapping = {
            CandleGranularity.S5: 5,
            CandleGranularity.S10: 10,
            CandleGranularity.S15: 15,
            CandleGranularity.S30: 30,
            CandleGranularity.M1: 60,
            CandleGranularity.M2: 120,
            CandleGranularity.M4: 240,
            CandleGranularity.M5: 300,
            CandleGranularity.M10: 600,
            CandleGranularity.M15: 900,
            CandleGranularity.M30: 1800,
            CandleGranularity.H1: 3600,
            CandleGranularity.H2: 7200,
            CandleGranularity.H3: 10800,
            CandleGranularity.H4: 14400,
            CandleGranularity.H6: 21600,
            CandleGranularity.H8: 28800,
            CandleGranularity.H12: 43200,
            CandleGranularity.D: 86400,
            CandleGranularity.W: 604800,
            CandleGranularity.M: 2592000,  # Approximate
        }
        return mapping.get(granularity, 3600)

    def _datetime_to_rfc3339(self, dt: datetime) -> str:
        """Convert datetime to RFC3339 format for OANDA API.

        Args:
            dt: Datetime (will be converted to UTC)

        Returns:
            RFC3339 formatted string
        """
        # Ensure UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        return dt.isoformat().replace("+00:00", "Z")

    def _rfc3339_to_datetime(self, rfc3339: str) -> datetime:
        """Convert RFC3339 string to datetime.

        Args:
            rfc3339: RFC3339 formatted string

        Returns:
            UTC datetime
        """
        # Handle OANDA's format (ending in Z or +00:00)
        if rfc3339.endswith("Z"):
            rfc3339 = rfc3339[:-1] + "+00:00"

        return datetime.fromisoformat(rfc3339).astimezone(timezone.utc)
