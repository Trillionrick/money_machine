-- Basic PostgreSQL schema for OANDA data (without TimescaleDB features)
-- This is a simplified version that works with regular PostgreSQL

-- Create pricing table
CREATE TABLE IF NOT EXISTS oanda_pricing (
    time TIMESTAMPTZ NOT NULL,
    instrument VARCHAR(20) NOT NULL,
    bid NUMERIC(20, 10) NOT NULL,
    ask NUMERIC(20, 10) NOT NULL,
    spread NUMERIC(20, 10) NOT NULL,
    bid_liquidity BIGINT,
    ask_liquidity BIGINT,
    tradeable BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (time, instrument)
);

CREATE INDEX IF NOT EXISTS idx_oanda_pricing_instrument ON oanda_pricing (instrument, time DESC);

-- Create candles table
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
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (time, instrument, granularity)
);

CREATE INDEX IF NOT EXISTS idx_oanda_candles_instrument ON oanda_candles (instrument, time DESC);
CREATE INDEX IF NOT EXISTS idx_oanda_candles_granularity ON oanda_candles (granularity, time DESC);

-- Create transactions table
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

CREATE INDEX IF NOT EXISTS idx_oanda_transactions_time ON oanda_transactions (time DESC);
CREATE INDEX IF NOT EXISTS idx_oanda_transactions_instrument ON oanda_transactions (instrument, time DESC);
CREATE INDEX IF NOT EXISTS idx_oanda_transactions_type ON oanda_transactions (type, time DESC);

-- Success message
SELECT 'PostgreSQL schema created successfully!' as status;
SELECT 'Tables: oanda_pricing, oanda_candles, oanda_transactions' as info;
