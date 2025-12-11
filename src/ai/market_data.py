"""Market data collection and volatility calculation.

Provides:
- Real-time volatility calculation (1h, 24h, 7d windows)
- Historical price tracking
- Volume and liquidity metrics
- Integration with TimescaleDB for persistence
"""

from __future__ import annotations

import asyncio
import os
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import asyncpg
import numpy as np
import structlog

if TYPE_CHECKING:
    from decimal import Decimal

log = structlog.get_logger()


@dataclass
class VolatilityMetrics:
    """Volatility and market metrics for a symbol."""

    symbol: str
    chain: str
    timestamp: datetime

    # Current price
    price: float

    # Returns (log returns)
    returns_1m: float | None = None
    returns_5m: float | None = None
    returns_1h: float | None = None

    # Annualized volatility
    volatility_1h: float | None = None
    volatility_24h: float | None = None
    volatility_7d: float | None = None

    # Volume metrics
    volume_1h: float | None = None
    volume_24h: float | None = None

    # Liquidity
    bid_ask_spread_bps: float | None = None
    liquidity_depth: float | None = None


class PriceBuffer:
    """Thread-safe circular buffer for price history."""

    def __init__(self, maxlen: int = 10080):  # 7 days at 1-minute granularity
        """Initialize price buffer.

        Args:
            maxlen: Maximum number of price points to store
        """
        self.prices: deque[tuple[datetime, float]] = deque(maxlen=maxlen)
        self.volumes: deque[tuple[datetime, float]] = deque(maxlen=maxlen)

    def add(self, timestamp: datetime, price: float, volume: float = 0.0) -> None:
        """Add new price point."""
        self.prices.append((timestamp, price))
        self.volumes.append((timestamp, volume))

    def get_prices_since(self, lookback: timedelta) -> list[tuple[datetime, float]]:
        """Get all prices since lookback period."""
        cutoff = datetime.utcnow() - lookback
        return [(ts, price) for ts, price in self.prices if ts >= cutoff]

    def get_volumes_since(self, lookback: timedelta) -> list[tuple[datetime, float]]:
        """Get all volumes since lookback period."""
        cutoff = datetime.utcnow() - lookback
        return [(ts, vol) for ts, vol in self.volumes if ts >= cutoff]

    def calculate_returns(self, lookback: timedelta) -> list[float]:
        """Calculate log returns for lookback period."""
        prices_window = self.get_prices_since(lookback)
        if len(prices_window) < 2:
            return []

        prices_only = [p for _, p in prices_window]
        returns = [
            np.log(prices_only[i] / prices_only[i - 1])
            for i in range(1, len(prices_only))
        ]
        return returns

    def calculate_volatility(self, lookback: timedelta, annualization_factor: float) -> float | None:
        """Calculate annualized volatility for lookback period.

        Args:
            lookback: Time window to calculate over
            annualization_factor: Multiply by this to annualize (e.g., sqrt(365*24*60) for 1-min data)

        Returns:
            Annualized volatility or None if insufficient data
        """
        returns = self.calculate_returns(lookback)
        if len(returns) < 10:  # Need minimum sample size
            return None

        # Calculate standard deviation of returns
        std_dev = float(np.std(returns, ddof=1))

        # Annualize
        annualized_vol = std_dev * np.sqrt(annualization_factor)

        return annualized_vol

    def get_latest_price(self) -> float | None:
        """Get most recent price."""
        if not self.prices:
            return None
        return self.prices[-1][1]

    def get_price_change_pct(self, lookback: timedelta) -> float | None:
        """Get percentage price change over lookback period."""
        prices_window = self.get_prices_since(lookback)
        if len(prices_window) < 2:
            return None

        first_price = prices_window[0][1]
        last_price = prices_window[-1][1]

        return ((last_price - first_price) / first_price) * 100


class MarketDataCollector:
    """Collects and calculates market data metrics.

    Features:
    - Real-time volatility calculation
    - Price and volume tracking
    - TimescaleDB persistence
    - Multi-chain support
    """

    def __init__(self):
        """Initialize market data collector."""
        self.pool: asyncpg.Pool | None = None
        self.db_url = self._build_db_url()

        # Per-symbol price buffers
        self.buffers: dict[tuple[str, str], PriceBuffer] = {}

        # Annualization factors (for 1-minute data)
        self.ANNUALIZATION_FACTORS = {
            "1h": 60,  # 60 minutes
            "24h": 60 * 24,  # 1440 minutes
            "7d": 60 * 24 * 7,  # 10080 minutes
        }

        log.info("market_data.initialized")

    def _build_db_url(self) -> str:
        """Build PostgreSQL connection URL from environment."""
        host = os.getenv("TIMESCALE_HOST", "localhost")
        port = os.getenv("TIMESCALE_PORT", "5433")
        user = os.getenv("TIMESCALE_USER", "trading_user")
        password = os.getenv("TIMESCALE_PASSWORD", "trading_pass_change_in_production")
        database = os.getenv("TIMESCALE_DB", "trading_db")

        return f"postgresql://{user}:{password}@{host}:{port}/{database}"

    async def connect(self) -> None:
        """Create connection pool to TimescaleDB."""
        if self.pool is None:
            try:
                self.pool = await asyncpg.create_pool(
                    self.db_url,
                    min_size=2,
                    max_size=10,
                    command_timeout=60,
                )
                log.info("market_data.connected")
            except Exception as e:
                log.warning("market_data.connect_failed", error=str(e))

    async def close(self) -> None:
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            log.info("market_data.closed")

    def _get_buffer(self, symbol: str, chain: str) -> PriceBuffer:
        """Get or create price buffer for symbol."""
        key = (symbol, chain)
        if key not in self.buffers:
            self.buffers[key] = PriceBuffer()
        return self.buffers[key]

    async def record_price(
        self,
        symbol: str,
        chain: str,
        price: float,
        volume: float = 0.0,
        bid_ask_spread_bps: float | None = None,
        liquidity_depth: float | None = None,
    ) -> VolatilityMetrics:
        """Record new price and calculate volatility metrics.

        Args:
            symbol: Trading symbol (e.g., "ETH/USDC")
            chain: Blockchain (e.g., "ethereum", "polygon")
            price: Current price
            volume: Trading volume
            bid_ask_spread_bps: Bid-ask spread in basis points
            liquidity_depth: Available liquidity

        Returns:
            Calculated volatility metrics
        """
        timestamp = datetime.utcnow()
        buffer = self._get_buffer(symbol, chain)

        # Add to buffer
        buffer.add(timestamp, price, volume)

        # Calculate returns
        returns_1m = self._calculate_return(buffer, timedelta(minutes=1))
        returns_5m = self._calculate_return(buffer, timedelta(minutes=5))
        returns_1h = self._calculate_return(buffer, timedelta(hours=1))

        # Calculate volatilities
        vol_1h = buffer.calculate_volatility(
            timedelta(hours=1),
            self.ANNUALIZATION_FACTORS["1h"],
        )
        vol_24h = buffer.calculate_volatility(
            timedelta(hours=24),
            self.ANNUALIZATION_FACTORS["24h"],
        )
        vol_7d = buffer.calculate_volatility(
            timedelta(days=7),
            self.ANNUALIZATION_FACTORS["7d"],
        )

        # Calculate volume sums
        volume_1h = self._sum_volume(buffer, timedelta(hours=1))
        volume_24h = self._sum_volume(buffer, timedelta(hours=24))

        # Create metrics object
        metrics = VolatilityMetrics(
            symbol=symbol,
            chain=chain,
            timestamp=timestamp,
            price=price,
            returns_1m=returns_1m,
            returns_5m=returns_5m,
            returns_1h=returns_1h,
            volatility_1h=vol_1h,
            volatility_24h=vol_24h,
            volatility_7d=vol_7d,
            volume_1h=volume_1h,
            volume_24h=volume_24h,
            bid_ask_spread_bps=bid_ask_spread_bps,
            liquidity_depth=liquidity_depth,
        )

        # Persist to database (async, don't wait)
        asyncio.create_task(self._persist_metrics(metrics))

        return metrics

    def _calculate_return(self, buffer: PriceBuffer, lookback: timedelta) -> float | None:
        """Calculate percentage return over lookback period."""
        return buffer.get_price_change_pct(lookback)

    def _sum_volume(self, buffer: PriceBuffer, lookback: timedelta) -> float | None:
        """Sum volume over lookback period."""
        volumes = buffer.get_volumes_since(lookback)
        if not volumes:
            return None
        return sum(vol for _, vol in volumes)

    async def _persist_metrics(self, metrics: VolatilityMetrics) -> None:
        """Persist volatility metrics to TimescaleDB."""
        if not self.pool:
            await self.connect()

        if not self.pool:
            log.warning("market_data.no_connection")
            return

        try:
            await self.pool.execute(
                """
                INSERT INTO market_volatility (
                    timestamp, symbol, chain, price,
                    returns_1m, returns_5m, returns_1h,
                    volatility_1h, volatility_24h, volatility_7d,
                    volume_1h, volume_24h,
                    bid_ask_spread_bps, liquidity_depth
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
                )
                """,
                metrics.timestamp,
                metrics.symbol,
                metrics.chain,
                metrics.price,
                metrics.returns_1m,
                metrics.returns_5m,
                metrics.returns_1h,
                metrics.volatility_1h,
                metrics.volatility_24h,
                metrics.volatility_7d,
                metrics.volume_1h,
                metrics.volume_24h,
                metrics.bid_ask_spread_bps,
                metrics.liquidity_depth,
            )

            log.debug(
                "market_data.persisted",
                symbol=metrics.symbol,
                vol_24h=metrics.volatility_24h,
            )

        except Exception as e:
            log.warning("market_data.persist_failed", error=str(e), symbol=metrics.symbol)

    async def get_latest_volatility(
        self, symbol: str, chain: str
    ) -> VolatilityMetrics | None:
        """Get latest volatility metrics from database.

        Args:
            symbol: Trading symbol
            chain: Blockchain

        Returns:
            Latest volatility metrics or None
        """
        if not self.pool:
            await self.connect()

        if not self.pool:
            return None

        try:
            row = await self.pool.fetchrow(
                """
                SELECT * FROM market_volatility
                WHERE symbol = $1 AND chain = $2
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                symbol,
                chain,
            )

            if not row:
                return None

            return VolatilityMetrics(
                symbol=row["symbol"],
                chain=row["chain"],
                timestamp=row["timestamp"],
                price=float(row["price"]),
                returns_1m=float(row["returns_1m"]) if row["returns_1m"] else None,
                returns_5m=float(row["returns_5m"]) if row["returns_5m"] else None,
                returns_1h=float(row["returns_1h"]) if row["returns_1h"] else None,
                volatility_1h=float(row["volatility_1h"]) if row["volatility_1h"] else None,
                volatility_24h=float(row["volatility_24h"]) if row["volatility_24h"] else None,
                volatility_7d=float(row["volatility_7d"]) if row["volatility_7d"] else None,
                volume_1h=float(row["volume_1h"]) if row["volume_1h"] else None,
                volume_24h=float(row["volume_24h"]) if row["volume_24h"] else None,
                bid_ask_spread_bps=float(row["bid_ask_spread_bps"])
                if row["bid_ask_spread_bps"]
                else None,
                liquidity_depth=float(row["liquidity_depth"])
                if row["liquidity_depth"]
                else None,
            )

        except Exception as e:
            log.warning("market_data.fetch_failed", error=str(e), symbol=symbol)
            return None

    def get_current_volatility_from_buffer(
        self, symbol: str, chain: str
    ) -> dict[str, float | None]:
        """Get current volatility from in-memory buffer (no DB query).

        Args:
            symbol: Trading symbol
            chain: Blockchain

        Returns:
            Dict with volatility metrics
        """
        buffer = self._get_buffer(symbol, chain)

        vol_1h = buffer.calculate_volatility(
            timedelta(hours=1),
            self.ANNUALIZATION_FACTORS["1h"],
        )
        vol_24h = buffer.calculate_volatility(
            timedelta(hours=24),
            self.ANNUALIZATION_FACTORS["24h"],
        )
        vol_7d = buffer.calculate_volatility(
            timedelta(days=7),
            self.ANNUALIZATION_FACTORS["7d"],
        )

        return {
            "volatility_1h": vol_1h,
            "volatility_24h": vol_24h,
            "volatility_7d": vol_7d,
            "latest_price": buffer.get_latest_price(),
        }

    async def load_historical_data(
        self, symbol: str, chain: str, days: int = 7
    ) -> None:
        """Load historical data from database into buffer.

        Useful for initializing buffers on startup.

        Args:
            symbol: Trading symbol
            chain: Blockchain
            days: Number of days to load
        """
        if not self.pool:
            await self.connect()

        if not self.pool:
            log.warning("market_data.no_connection")
            return

        try:
            rows = await self.pool.fetch(
                """
                SELECT timestamp, price FROM market_volatility
                WHERE symbol = $1 AND chain = $2
                  AND timestamp > NOW() - $3::INTERVAL
                ORDER BY timestamp ASC
                """,
                symbol,
                chain,
                f"{days} days",
            )

            if not rows:
                log.info("market_data.no_historical_data", symbol=symbol, chain=chain)
                return

            buffer = self._get_buffer(symbol, chain)
            for row in rows:
                buffer.add(row["timestamp"], float(row["price"]))

            log.info(
                "market_data.historical_loaded",
                symbol=symbol,
                chain=chain,
                points=len(rows),
            )

        except Exception as e:
            log.warning("market_data.load_failed", error=str(e), symbol=symbol)


# Global singleton instance
_collector: MarketDataCollector | None = None


def get_market_data_collector() -> MarketDataCollector:
    """Get global MarketDataCollector instance."""
    global _collector
    if _collector is None:
        _collector = MarketDataCollector()
    return _collector
