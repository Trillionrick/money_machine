"""Database schema for OANDA forex data storage.

This module defines TimescaleDB schema for storing:
- OHLCV candle data (hypertables for efficient time-series storage)
- Forex-specific metadata (spreads, swap rates)
- Transaction history
- Position snapshots

Uses TimescaleDB for:
- Automatic partitioning by time
- Efficient compression
- Continuous aggregates for downsampling
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

# SQL schema for TimescaleDB (PostgreSQL extension)

OANDA_CANDLES_TABLE = """
CREATE TABLE IF NOT EXISTS oanda_candles (
    time TIMESTAMPTZ NOT NULL,
    instrument VARCHAR(20) NOT NULL,
    granularity VARCHAR(10) NOT NULL,

    -- OHLCV data (using NUMERIC for precision)
    open NUMERIC(20, 10) NOT NULL,
    high NUMERIC(20, 10) NOT NULL,
    low NUMERIC(20, 10) NOT NULL,
    close NUMERIC(20, 10) NOT NULL,
    volume BIGINT NOT NULL,

    -- Bid/Ask data (forex-specific)
    bid_open NUMERIC(20, 10),
    bid_high NUMERIC(20, 10),
    bid_low NUMERIC(20, 10),
    bid_close NUMERIC(20, 10),
    ask_open NUMERIC(20, 10),
    ask_high NUMERIC(20, 10),
    ask_low NUMERIC(20, 10),
    ask_close NUMERIC(20, 10),

    -- Spread (difference between bid and ask)
    spread_avg NUMERIC(20, 10),
    spread_max NUMERIC(20, 10),

    -- Metadata
    complete BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (time, instrument, granularity)
);

-- Create hypertable for time-series optimization
SELECT create_hypertable(
    'oanda_candles',
    'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);

-- Add compression policy (compress data older than 7 days)
ALTER TABLE oanda_candles SET (
    timescaledb.compress,
    timescaledb.compress_orderby = 'time DESC',
    timescaledb.compress_segmentby = 'instrument, granularity'
);

SELECT add_compression_policy(
    'oanda_candles',
    INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Indexes for fast querying
CREATE INDEX IF NOT EXISTS idx_oanda_candles_instrument_time
    ON oanda_candles (instrument, time DESC);
CREATE INDEX IF NOT EXISTS idx_oanda_candles_granularity
    ON oanda_candles (granularity, time DESC);
"""

OANDA_TRANSACTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS oanda_transactions (
    id VARCHAR(50) PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    account_id VARCHAR(50) NOT NULL,

    -- Transaction type
    type VARCHAR(30) NOT NULL,

    -- Order/Trade info
    instrument VARCHAR(20),
    units NUMERIC(20, 4),
    price NUMERIC(20, 10),

    -- P&L
    pl NUMERIC(20, 4),
    financing NUMERIC(20, 4),
    commission NUMERIC(20, 4),

    -- Related IDs
    order_id VARCHAR(50),
    trade_id VARCHAR(50),

    -- Full transaction data (JSONB for flexibility)
    data JSONB NOT NULL,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create hypertable
SELECT create_hypertable(
    'oanda_transactions',
    'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_oanda_transactions_type
    ON oanda_transactions (type, time DESC);
CREATE INDEX IF NOT EXISTS idx_oanda_transactions_instrument
    ON oanda_transactions (instrument, time DESC);
CREATE INDEX IF NOT EXISTS idx_oanda_transactions_account
    ON oanda_transactions (account_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_oanda_transactions_order
    ON oanda_transactions (order_id);
CREATE INDEX IF NOT EXISTS idx_oanda_transactions_trade
    ON oanda_transactions (trade_id);

-- GIN index for JSONB queries
CREATE INDEX IF NOT EXISTS idx_oanda_transactions_data
    ON oanda_transactions USING GIN (data);
"""

OANDA_POSITIONS_TABLE = """
CREATE TABLE IF NOT EXISTS oanda_positions (
    time TIMESTAMPTZ NOT NULL,
    account_id VARCHAR(50) NOT NULL,
    instrument VARCHAR(20) NOT NULL,

    -- Position data
    long_units NUMERIC(20, 4) NOT NULL DEFAULT 0,
    long_avg_price NUMERIC(20, 10),
    long_unrealized_pl NUMERIC(20, 4),

    short_units NUMERIC(20, 4) NOT NULL DEFAULT 0,
    short_avg_price NUMERIC(20, 10),
    short_unrealized_pl NUMERIC(20, 4),

    -- Net position
    net_units NUMERIC(20, 4) NOT NULL,

    -- Margin requirements
    margin_used NUMERIC(20, 4),

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (time, account_id, instrument)
);

-- Create hypertable
SELECT create_hypertable(
    'oanda_positions',
    'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 hour'
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_oanda_positions_instrument
    ON oanda_positions (instrument, time DESC);
CREATE INDEX IF NOT EXISTS idx_oanda_positions_account
    ON oanda_positions (account_id, time DESC);
"""

OANDA_PRICING_TABLE = """
CREATE TABLE IF NOT EXISTS oanda_pricing (
    time TIMESTAMPTZ NOT NULL,
    instrument VARCHAR(20) NOT NULL,

    -- Bid/Ask ticks
    bid NUMERIC(20, 10) NOT NULL,
    ask NUMERIC(20, 10) NOT NULL,

    -- Spread
    spread NUMERIC(20, 10) NOT NULL,

    -- Liquidity (if available)
    bid_liquidity BIGINT,
    ask_liquidity BIGINT,

    -- Metadata
    tradeable BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (time, instrument)
);

-- Create hypertable (smaller chunks for tick data)
SELECT create_hypertable(
    'oanda_pricing',
    'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 hour'
);

-- Compression for tick data (aggressive compression after 1 day)
ALTER TABLE oanda_pricing SET (
    timescaledb.compress,
    timescaledb.compress_orderby = 'time DESC',
    timescaledb.compress_segmentby = 'instrument'
);

SELECT add_compression_policy(
    'oanda_pricing',
    INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Index
CREATE INDEX IF NOT EXISTS idx_oanda_pricing_instrument
    ON oanda_pricing (instrument, time DESC);
"""

OANDA_INSTRUMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS oanda_instruments (
    instrument VARCHAR(20) PRIMARY KEY,
    display_name VARCHAR(50) NOT NULL,

    -- Instrument type
    type VARCHAR(20) NOT NULL,

    -- Precision
    pip_location INT NOT NULL,
    display_precision INT NOT NULL,
    trade_units_precision INT NOT NULL,

    -- Margin requirements
    margin_rate NUMERIC(10, 6) NOT NULL,

    -- Trading constraints
    minimum_trade_size NUMERIC(20, 4) NOT NULL,
    maximum_order_units NUMERIC(20, 4) NOT NULL,
    maximum_position_size NUMERIC(20, 4) NOT NULL,

    -- Financing
    financing_days_of_week JSONB,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index
CREATE INDEX IF NOT EXISTS idx_oanda_instruments_type
    ON oanda_instruments (type);
"""

# Continuous aggregates for downsampling (materialized views)
OANDA_CANDLES_1H_AGG = """
CREATE MATERIALIZED VIEW IF NOT EXISTS oanda_candles_1h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS time,
    instrument,
    FIRST(open, time) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, time) AS close,
    SUM(volume) AS volume,
    AVG(spread_avg) AS spread_avg
FROM oanda_candles
WHERE granularity IN ('M1', 'M5', 'M15')
GROUP BY time_bucket('1 hour', time), instrument;

-- Refresh policy (update every 10 minutes)
SELECT add_continuous_aggregate_policy(
    'oanda_candles_1h',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '10 minutes',
    schedule_interval => INTERVAL '10 minutes',
    if_not_exists => TRUE
);
"""

OANDA_CANDLES_1D_AGG = """
CREATE MATERIALIZED VIEW IF NOT EXISTS oanda_candles_1d
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS time,
    instrument,
    FIRST(open, time) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, time) AS close,
    SUM(volume) AS volume,
    AVG(spread_avg) AS spread_avg
FROM oanda_candles
WHERE granularity IN ('H1', 'H4')
GROUP BY time_bucket('1 day', time), instrument;

-- Refresh policy
SELECT add_continuous_aggregate_policy(
    'oanda_candles_1d',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);
"""

# Complete schema initialization
ALL_SCHEMAS = [
    OANDA_CANDLES_TABLE,
    OANDA_TRANSACTIONS_TABLE,
    OANDA_POSITIONS_TABLE,
    OANDA_PRICING_TABLE,
    OANDA_INSTRUMENTS_TABLE,
    OANDA_CANDLES_1H_AGG,
    OANDA_CANDLES_1D_AGG,
]


def get_create_schema_sql() -> str:
    """Get complete SQL for creating OANDA schema.

    Returns:
        SQL string to execute
    """
    return "\n\n".join(ALL_SCHEMAS)


# Python models for type safety (optional, for ORM-less approach)


class OandaCandle:
    """Python representation of OANDA candle row."""

    def __init__(
        self,
        *,
        time: datetime,
        instrument: str,
        granularity: str,
        open: Decimal,
        high: Decimal,
        low: Decimal,
        close: Decimal,
        volume: int,
        bid_open: Decimal | None = None,
        bid_high: Decimal | None = None,
        bid_low: Decimal | None = None,
        bid_close: Decimal | None = None,
        ask_open: Decimal | None = None,
        ask_high: Decimal | None = None,
        ask_low: Decimal | None = None,
        ask_close: Decimal | None = None,
        spread_avg: Decimal | None = None,
        spread_max: Decimal | None = None,
        complete: bool = False,
    ) -> None:
        """Initialize candle."""
        self.time = time
        self.instrument = instrument
        self.granularity = granularity
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.bid_open = bid_open
        self.bid_high = bid_high
        self.bid_low = bid_low
        self.bid_close = bid_close
        self.ask_open = ask_open
        self.ask_high = ask_high
        self.ask_low = ask_low
        self.ask_close = ask_close
        self.spread_avg = spread_avg
        self.spread_max = spread_max
        self.complete = complete

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "time": self.time,
            "instrument": self.instrument,
            "granularity": self.granularity,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "bid_open": self.bid_open,
            "bid_high": self.bid_high,
            "bid_low": self.bid_low,
            "bid_close": self.bid_close,
            "ask_open": self.ask_open,
            "ask_high": self.ask_high,
            "ask_low": self.ask_low,
            "ask_close": self.ask_close,
            "spread_avg": self.spread_avg,
            "spread_max": self.spread_max,
            "complete": self.complete,
        }
