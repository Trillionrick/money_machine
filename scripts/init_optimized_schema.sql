-- Optimized PostgreSQL schema with native partitioning for time-series data
-- This gives us TimescaleDB-like performance without needing the extension

-- ===========================================================================
-- OANDA PRICING (Tick Data) - Partitioned by Day
-- ===========================================================================

-- Create parent table with partitioning
CREATE TABLE IF NOT EXISTS oanda_pricing (
    time TIMESTAMPTZ NOT NULL,
    instrument VARCHAR(20) NOT NULL,
    bid NUMERIC(20, 10) NOT NULL,
    ask NUMERIC(20, 10) NOT NULL,
    spread NUMERIC(20, 10) NOT NULL,
    bid_liquidity BIGINT,
    ask_liquidity BIGINT,
    tradeable BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (time);

-- Create partitions for current and next months (auto-create more as needed)
DO $$
DECLARE
    partition_date DATE;
    partition_name TEXT;
BEGIN
    -- Create daily partitions for the next 7 days
    FOR i IN 0..6 LOOP
        partition_date := CURRENT_DATE + i;
        partition_name := 'oanda_pricing_' || TO_CHAR(partition_date, 'YYYY_MM_DD');

        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF oanda_pricing
             FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            partition_date,
            partition_date + INTERVAL '1 day'
        );
    END LOOP;
END $$;

-- Indexes on partitioned table
CREATE INDEX IF NOT EXISTS idx_pricing_time ON oanda_pricing (time DESC);
CREATE INDEX IF NOT EXISTS idx_pricing_instrument ON oanda_pricing (instrument, time DESC);

-- ===========================================================================
-- OANDA CANDLES - Partitioned by Month
-- ===========================================================================

CREATE TABLE IF NOT EXISTS oanda_candles (
    time TIMESTAMPTZ NOT NULL,
    instrument VARCHAR(20) NOT NULL,
    granularity VARCHAR(10) NOT NULL,
    open NUMERIC(20, 10) NOT NULL,
    high NUMERIC(20, 10) NOT NULL,
    low NUMERIC(20, 10) NOT NULL,
    close NUMERIC(20, 10) NOT NULL,
    volume BIGINT NOT NULL,
    bid_open NUMERIC(20, 10),
    bid_high NUMERIC(20, 10),
    bid_low NUMERIC(20, 10),
    bid_close NUMERIC(20, 10),
    ask_open NUMERIC(20, 10),
    ask_high NUMERIC(20, 10),
    ask_low NUMERIC(20, 10),
    ask_close NUMERIC(20, 10),
    spread_avg NUMERIC(20, 10),
    spread_max NUMERIC(20, 10),
    complete BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (time);

-- Create monthly partitions
DO $$
DECLARE
    partition_date DATE;
    partition_name TEXT;
BEGIN
    -- Create partitions for current month and next 2 months
    FOR i IN 0..2 LOOP
        partition_date := DATE_TRUNC('month', CURRENT_DATE + (i || ' months')::INTERVAL)::DATE;
        partition_name := 'oanda_candles_' || TO_CHAR(partition_date, 'YYYY_MM');

        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF oanda_candles
             FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            partition_date,
            partition_date + INTERVAL '1 month'
        );
    END LOOP;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_candles_time ON oanda_candles (time DESC);
CREATE INDEX IF NOT EXISTS idx_candles_instrument ON oanda_candles (instrument, time DESC);
CREATE INDEX IF NOT EXISTS idx_candles_granularity ON oanda_candles (granularity, time DESC);

-- ===========================================================================
-- OANDA TRANSACTIONS
-- ===========================================================================

CREATE TABLE IF NOT EXISTS oanda_transactions (
    id VARCHAR(50) PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    account_id VARCHAR(50) NOT NULL,
    type VARCHAR(30) NOT NULL,
    instrument VARCHAR(20),
    units NUMERIC(20, 4),
    price NUMERIC(20, 10),
    pl NUMERIC(20, 4),
    financing NUMERIC(20, 4),
    commission NUMERIC(20, 4),
    order_id VARCHAR(50),
    trade_id VARCHAR(50),
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transactions_time ON oanda_transactions (time DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_instrument ON oanda_transactions (instrument, time DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON oanda_transactions (type);

-- ===========================================================================
-- MATERIALIZED VIEWS (Manual Aggregates)
-- ===========================================================================

-- Hourly aggregated candles from tick data
CREATE MATERIALIZED VIEW IF NOT EXISTS oanda_pricing_1h AS
SELECT
    DATE_TRUNC('hour', time) AS time,
    instrument,
    COUNT(*) AS tick_count,
    AVG(bid) AS avg_bid,
    AVG(ask) AS avg_ask,
    AVG(spread) AS avg_spread,
    MIN(bid) AS min_bid,
    MAX(ask) AS max_ask
FROM oanda_pricing
GROUP BY DATE_TRUNC('hour', time), instrument;

CREATE UNIQUE INDEX ON oanda_pricing_1h (time, instrument);

-- ===========================================================================
-- HELPER FUNCTIONS
-- ===========================================================================

-- Function to get latest price for an instrument
CREATE OR REPLACE FUNCTION get_latest_price(p_instrument VARCHAR)
RETURNS TABLE (
    time TIMESTAMPTZ,
    bid NUMERIC,
    ask NUMERIC,
    spread NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT p.time, p.bid, p.ask, p.spread
    FROM oanda_pricing p
    WHERE p.instrument = p_instrument
    ORDER BY p.time DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Function to auto-create new partitions
CREATE OR REPLACE FUNCTION create_partition_if_not_exists(
    table_name TEXT,
    partition_date DATE,
    partition_type TEXT DEFAULT 'day'
)
RETURNS VOID AS $$
DECLARE
    partition_name TEXT;
    start_date DATE;
    end_date DATE;
BEGIN
    partition_name := table_name || '_' || TO_CHAR(partition_date, 'YYYY_MM_DD');
    start_date := partition_date;

    IF partition_type = 'month' THEN
        partition_name := table_name || '_' || TO_CHAR(partition_date, 'YYYY_MM');
        start_date := DATE_TRUNC('month', partition_date)::DATE;
        end_date := start_date + INTERVAL '1 month';
    ELSE
        end_date := start_date + INTERVAL '1 day';
    END IF;

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I
         FOR VALUES FROM (%L) TO (%L)',
        partition_name, table_name, start_date, end_date
    );
END;
$$ LANGUAGE plpgsql;

-- ===========================================================================
-- MAINTENANCE
-- ===========================================================================

-- Enable auto-vacuum for better performance
ALTER TABLE oanda_pricing SET (
    autovacuum_vacuum_scale_factor = 0.1,
    autovacuum_analyze_scale_factor = 0.05
);

ALTER TABLE oanda_candles SET (
    autovacuum_vacuum_scale_factor = 0.1,
    autovacuum_analyze_scale_factor = 0.05
);

SELECT '✅ Optimized PostgreSQL schema created successfully!' as status;
SELECT '📊 Features: Time-based partitioning, materialized views, auto-maintenance' as features;
SELECT 'Tables: oanda_pricing (partitioned), oanda_candles (partitioned), oanda_transactions' as tables;
