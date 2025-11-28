-- OANDA Trading Database Initialization Script
-- This script is automatically run when TimescaleDB container starts
-- ============================================================================

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================================
-- OANDA CANDLES TABLE
-- ============================================================================
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

-- ============================================================================
-- OANDA TRANSACTIONS TABLE
-- ============================================================================
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

-- ============================================================================
-- OANDA POSITIONS TABLE
-- ============================================================================
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

-- ============================================================================
-- OANDA PRICING TABLE (Tick Data)
-- ============================================================================
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

-- ============================================================================
-- OANDA INSTRUMENTS TABLE
-- ============================================================================
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

-- ============================================================================
-- CONTINUOUS AGGREGATES (Materialized Views for Downsampling)
-- ============================================================================

-- 1-hour aggregate from minute candles
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

-- 1-day aggregate from hourly candles
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

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function to get latest candle for an instrument
CREATE OR REPLACE FUNCTION get_latest_candle(p_instrument VARCHAR, p_granularity VARCHAR)
RETURNS TABLE (
    time TIMESTAMPTZ,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT c.time, c.open, c.high, c.low, c.close, c.volume
    FROM oanda_candles c
    WHERE c.instrument = p_instrument
      AND c.granularity = p_granularity
      AND c.complete = true
    ORDER BY c.time DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Function to get current spread for an instrument
CREATE OR REPLACE FUNCTION get_current_spread(p_instrument VARCHAR)
RETURNS NUMERIC AS $$
DECLARE
    v_spread NUMERIC;
BEGIN
    SELECT spread INTO v_spread
    FROM oanda_pricing
    WHERE instrument = p_instrument
    ORDER BY time DESC
    LIMIT 1;

    RETURN COALESCE(v_spread, 0);
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- GRANT PERMISSIONS
-- ============================================================================

-- Grant permissions to trading_user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO trading_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO trading_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO trading_user;

-- ============================================================================
-- INITIAL DATA
-- ============================================================================

-- Insert common forex instruments metadata
INSERT INTO oanda_instruments (
    instrument, display_name, type, pip_location, display_precision,
    trade_units_precision, margin_rate, minimum_trade_size,
    maximum_order_units, maximum_position_size
) VALUES
    ('EUR_USD', 'EUR/USD', 'CURRENCY', -4, 5, 0, 0.0333, 1, 100000000, 100000000),
    ('GBP_USD', 'GBP/USD', 'CURRENCY', -4, 5, 0, 0.0333, 1, 100000000, 100000000),
    ('USD_JPY', 'USD/JPY', 'CURRENCY', -2, 3, 0, 0.0400, 1, 100000000, 100000000),
    ('AUD_USD', 'AUD/USD', 'CURRENCY', -4, 5, 0, 0.0333, 1, 100000000, 100000000),
    ('USD_CAD', 'USD/CAD', 'CURRENCY', -4, 5, 0, 0.0333, 1, 100000000, 100000000),
    ('USD_CHF', 'USD/CHF', 'CURRENCY', -4, 5, 0, 0.0333, 1, 100000000, 100000000),
    ('NZD_USD', 'NZD/USD', 'CURRENCY', -4, 5, 0, 0.0333, 1, 100000000, 100000000),
    ('EUR_GBP', 'EUR/GBP', 'CURRENCY', -4, 5, 0, 0.0333, 1, 100000000, 100000000),
    ('EUR_JPY', 'EUR/JPY', 'CURRENCY', -2, 3, 0, 0.0400, 1, 100000000, 100000000),
    ('GBP_JPY', 'GBP/JPY', 'CURRENCY', -2, 3, 0, 0.0400, 1, 100000000, 100000000),
    ('XAU_USD', 'Gold', 'METAL', -2, 2, 0, 0.0500, 1, 10000, 10000),
    ('XAG_USD', 'Silver', 'METAL', -3, 3, 0, 0.0500, 1, 100000, 100000)
ON CONFLICT (instrument) DO NOTHING;

-- ============================================================================
-- COMPLETION MESSAGE
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE '✅ OANDA database schema initialized successfully!';
    RAISE NOTICE '📊 Tables created: oanda_candles, oanda_transactions, oanda_positions, oanda_pricing, oanda_instruments';
    RAISE NOTICE '📈 Continuous aggregates: oanda_candles_1h, oanda_candles_1d';
    RAISE NOTICE '🗜️  Compression policies: Enabled for candles (7d) and pricing (1d)';
    RAISE NOTICE '🔧 Helper functions: get_latest_candle(), get_current_spread()';
    RAISE NOTICE '';
    RAISE NOTICE 'Database: trading_db';
    RAISE NOTICE 'User: trading_user';
    RAISE NOTICE 'Port: 5433';
    RAISE NOTICE '';
    RAISE NOTICE 'Connect with: psql -h localhost -p 5433 -U trading_user -d trading_db';
END $$;
