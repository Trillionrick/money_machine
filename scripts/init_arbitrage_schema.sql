-- Arbitrage Trading Database Schema
-- Extends OANDA schema with arbitrage-specific tables
-- ============================================================================

-- ============================================================================
-- ARBITRAGE OPPORTUNITIES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS arbitrage_opportunities (
    id SERIAL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Trading pair info
    symbol VARCHAR(20) NOT NULL,
    chain VARCHAR(20) NOT NULL,  -- ethereum, polygon, etc.

    -- Price data
    cex_price NUMERIC(20, 10) NOT NULL,
    dex_price NUMERIC(20, 10) NOT NULL,
    edge_bps NUMERIC(10, 2) NOT NULL,

    -- Market conditions
    pool_liquidity_quote NUMERIC(20, 4),
    gas_price_gwei NUMERIC(10, 2) NOT NULL,
    hour_of_day INT NOT NULL,

    -- Execution parameters
    estimated_slippage_bps NUMERIC(10, 4) NOT NULL,
    trade_size_quote NUMERIC(20, 4),
    hop_count INT DEFAULT 2,
    route_path TEXT,
    execution_path VARCHAR(20) DEFAULT 'regular',

    -- Execution results (updated after execution)
    executed BOOLEAN DEFAULT FALSE,
    actual_slippage_bps NUMERIC(10, 4),
    profitable BOOLEAN,
    profit_eth NUMERIC(20, 10),
    profit_quote NUMERIC(20, 4),
    gas_cost_eth NUMERIC(20, 10),

    -- ML model version
    ml_model_version VARCHAR(50),

    PRIMARY KEY (timestamp, id)
);

-- Create hypertable
SELECT create_hypertable(
    'arbitrage_opportunities',
    'timestamp',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);

-- Compression policy
ALTER TABLE arbitrage_opportunities SET (
    timescaledb.compress,
    timescaledb.compress_orderby = 'timestamp DESC',
    timescaledb.compress_segmentby = 'symbol, chain'
);

SELECT add_compression_policy(
    'arbitrage_opportunities',
    INTERVAL '30 days',
    if_not_exists => TRUE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_arb_opp_symbol_time
    ON arbitrage_opportunities (symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_arb_opp_executed
    ON arbitrage_opportunities (executed, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_arb_opp_profitable
    ON arbitrage_opportunities (profitable, timestamp DESC) WHERE executed = TRUE;
CREATE INDEX IF NOT EXISTS idx_arb_opp_edge
    ON arbitrage_opportunities (edge_bps DESC, timestamp DESC);

-- ============================================================================
-- MARKET VOLATILITY TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS market_volatility (
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    chain VARCHAR(20) NOT NULL,

    -- Volatility metrics
    price NUMERIC(20, 10) NOT NULL,
    returns_1m NUMERIC(10, 6),  -- 1-minute returns
    returns_5m NUMERIC(10, 6),  -- 5-minute returns
    returns_1h NUMERIC(10, 6),  -- 1-hour returns

    -- Rolling volatility (annualized)
    volatility_1h NUMERIC(10, 6),   -- 1-hour rolling volatility
    volatility_24h NUMERIC(10, 6),  -- 24-hour rolling volatility
    volatility_7d NUMERIC(10, 6),   -- 7-day rolling volatility

    -- Volume metrics
    volume_1h NUMERIC(20, 4),
    volume_24h NUMERIC(20, 4),

    -- Liquidity metrics
    bid_ask_spread_bps NUMERIC(10, 4),
    liquidity_depth NUMERIC(20, 4),

    PRIMARY KEY (timestamp, symbol, chain)
);

-- Create hypertable
SELECT create_hypertable(
    'market_volatility',
    'timestamp',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);

-- Compression
ALTER TABLE market_volatility SET (
    timescaledb.compress,
    timescaledb.compress_orderby = 'timestamp DESC',
    timescaledb.compress_segmentby = 'symbol, chain'
);

SELECT add_compression_policy(
    'market_volatility',
    INTERVAL '14 days',
    if_not_exists => TRUE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_vol_symbol_time
    ON market_volatility (symbol, chain, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_vol_volatility
    ON market_volatility (volatility_24h DESC, timestamp DESC);

-- ============================================================================
-- EXECUTION LOGS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS execution_logs (
    id SERIAL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Opportunity reference
    opportunity_id INT,

    -- Execution details
    symbol VARCHAR(20) NOT NULL,
    chain VARCHAR(20) NOT NULL,
    execution_type VARCHAR(30) NOT NULL,  -- flash_loan, regular, multi_hop

    -- Transaction details
    tx_hash VARCHAR(66),
    block_number BIGINT,
    gas_used BIGINT,
    gas_price_gwei NUMERIC(10, 2),

    -- Financial outcome
    success BOOLEAN NOT NULL,
    profit_eth NUMERIC(20, 10),
    profit_usd NUMERIC(20, 4),
    gas_cost_eth NUMERIC(20, 10),
    gas_cost_usd NUMERIC(20, 4),
    net_profit_usd NUMERIC(20, 4),

    -- Route details
    route_path TEXT,
    hop_count INT,

    -- Error info (if failed)
    error_message TEXT,
    error_code VARCHAR(50),

    -- AI decision data
    ai_confidence NUMERIC(5, 4),
    predicted_profit NUMERIC(20, 4),
    actual_slippage_bps NUMERIC(10, 4),

    PRIMARY KEY (timestamp, id)
);

-- Create hypertable
SELECT create_hypertable(
    'execution_logs',
    'timestamp',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);

-- Compression
ALTER TABLE execution_logs SET (
    timescaledb.compress,
    timescaledb.compress_orderby = 'timestamp DESC'
);

SELECT add_compression_policy(
    'execution_logs',
    INTERVAL '90 days',
    if_not_exists => TRUE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_exec_symbol_time
    ON execution_logs (symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_exec_success
    ON execution_logs (success, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_exec_tx_hash
    ON execution_logs (tx_hash) WHERE tx_hash IS NOT NULL;

-- ============================================================================
-- MODEL PERFORMANCE TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS model_performance (
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    model_name VARCHAR(50) NOT NULL,
    model_version VARCHAR(50) NOT NULL,

    -- Performance metrics
    accuracy NUMERIC(5, 4),
    precision_score NUMERIC(5, 4),
    recall NUMERIC(5, 4),
    f1_score NUMERIC(5, 4),

    -- Profit metrics
    avg_predicted_profit NUMERIC(20, 4),
    avg_actual_profit NUMERIC(20, 4),
    prediction_error_pct NUMERIC(10, 4),

    -- Sample size
    num_predictions INT NOT NULL,
    num_executions INT NOT NULL,

    -- Training info
    training_samples INT,
    training_duration_sec NUMERIC(10, 2),

    PRIMARY KEY (timestamp, model_name, model_version)
);

-- Create hypertable
SELECT create_hypertable(
    'model_performance',
    'timestamp',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '7 days'
);

-- Index
CREATE INDEX IF NOT EXISTS idx_model_perf_name
    ON model_performance (model_name, timestamp DESC);

-- ============================================================================
-- CONTINUOUS AGGREGATES (ML Training Data Views)
-- ============================================================================

-- ML training data view (executed opportunities only)
CREATE MATERIALIZED VIEW IF NOT EXISTS ml_training_data
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 minute', timestamp) AS timestamp,
    symbol,
    chain,
    edge_bps,
    pool_liquidity_quote,
    gas_price_gwei,
    hour_of_day,
    estimated_slippage_bps,
    actual_slippage_bps,
    profitable,
    profit_quote,
    gas_cost_eth,
    hop_count,
    execution_path
FROM arbitrage_opportunities
WHERE executed = TRUE
GROUP BY
    time_bucket('1 minute', timestamp),
    symbol, chain, edge_bps, pool_liquidity_quote,
    gas_price_gwei, hour_of_day, estimated_slippage_bps,
    actual_slippage_bps, profitable, profit_quote,
    gas_cost_eth, hop_count, execution_path;

-- Refresh policy (update every 5 minutes)
SELECT add_continuous_aggregate_policy(
    'ml_training_data',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists => TRUE
);

-- Hourly performance aggregate
CREATE MATERIALIZED VIEW IF NOT EXISTS hourly_performance
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp) AS timestamp,
    symbol,
    chain,
    COUNT(*) AS opportunity_count,
    COUNT(*) FILTER (WHERE executed = TRUE) AS execution_count,
    COUNT(*) FILTER (WHERE profitable = TRUE) AS profitable_count,
    AVG(edge_bps) AS avg_edge_bps,
    AVG(profit_quote) FILTER (WHERE executed = TRUE) AS avg_profit,
    SUM(profit_quote) FILTER (WHERE executed = TRUE) AS total_profit,
    AVG(gas_cost_eth) FILTER (WHERE executed = TRUE) AS avg_gas_cost
FROM arbitrage_opportunities
GROUP BY time_bucket('1 hour', timestamp), symbol, chain;

-- Refresh policy
SELECT add_continuous_aggregate_policy(
    'hourly_performance',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Daily profitability summary
CREATE MATERIALIZED VIEW IF NOT EXISTS daily_profitability
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', timestamp) AS date,
    symbol,
    chain,
    COUNT(*) FILTER (WHERE executed = TRUE) AS trades,
    COUNT(*) FILTER (WHERE profitable = TRUE) AS wins,
    CAST(COUNT(*) FILTER (WHERE profitable = TRUE) AS NUMERIC) /
        NULLIF(COUNT(*) FILTER (WHERE executed = TRUE), 0) AS win_rate,
    SUM(profit_quote) FILTER (WHERE executed = TRUE) AS gross_profit,
    SUM(gas_cost_eth * 3000) FILTER (WHERE executed = TRUE) AS total_gas_cost_usd,  -- Approximate
    SUM(profit_quote - COALESCE(gas_cost_eth * 3000, 0)) FILTER (WHERE executed = TRUE) AS net_profit
FROM arbitrage_opportunities
GROUP BY time_bucket('1 day', timestamp), symbol, chain;

-- Refresh policy
SELECT add_continuous_aggregate_policy(
    'daily_profitability',
    start_offset => INTERVAL '30 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Get latest volatility for a symbol
CREATE OR REPLACE FUNCTION get_latest_volatility(p_symbol VARCHAR, p_chain VARCHAR)
RETURNS TABLE (
    volatility_1h NUMERIC,
    volatility_24h NUMERIC,
    volatility_7d NUMERIC,
    last_update TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        mv.volatility_1h,
        mv.volatility_24h,
        mv.volatility_7d,
        mv.timestamp
    FROM market_volatility mv
    WHERE mv.symbol = p_symbol
      AND mv.chain = p_chain
    ORDER BY mv.timestamp DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Get performance stats for a symbol
CREATE OR REPLACE FUNCTION get_symbol_performance(
    p_symbol VARCHAR,
    p_days INT DEFAULT 7
)
RETURNS TABLE (
    total_opportunities BIGINT,
    total_executions BIGINT,
    win_rate NUMERIC,
    avg_profit NUMERIC,
    total_profit NUMERIC,
    avg_edge_bps NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*)::BIGINT AS total_opportunities,
        COUNT(*) FILTER (WHERE executed = TRUE)::BIGINT AS total_executions,
        CAST(COUNT(*) FILTER (WHERE profitable = TRUE) AS NUMERIC) /
            NULLIF(COUNT(*) FILTER (WHERE executed = TRUE), 0) AS win_rate,
        AVG(profit_quote) FILTER (WHERE executed = TRUE) AS avg_profit,
        SUM(profit_quote) FILTER (WHERE executed = TRUE) AS total_profit,
        AVG(edge_bps) AS avg_edge_bps
    FROM arbitrage_opportunities
    WHERE symbol = p_symbol
      AND timestamp > NOW() - (p_days || ' days')::INTERVAL;
END;
$$ LANGUAGE plpgsql;

-- Get model accuracy
CREATE OR REPLACE FUNCTION get_model_accuracy(
    p_model_name VARCHAR,
    p_days INT DEFAULT 7
)
RETURNS TABLE (
    avg_accuracy NUMERIC,
    total_predictions BIGINT,
    latest_version VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        AVG(accuracy) AS avg_accuracy,
        SUM(num_predictions)::BIGINT AS total_predictions,
        (SELECT model_version
         FROM model_performance
         WHERE model_name = p_model_name
         ORDER BY timestamp DESC
         LIMIT 1) AS latest_version
    FROM model_performance
    WHERE model_name = p_model_name
      AND timestamp > NOW() - (p_days || ' days')::INTERVAL;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- GRANT PERMISSIONS
-- ============================================================================

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO trading_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO trading_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO trading_user;

-- ============================================================================
-- COMPLETION MESSAGE
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE '✅ Arbitrage database schema initialized successfully!';
    RAISE NOTICE '📊 Tables created: arbitrage_opportunities, market_volatility, execution_logs, model_performance';
    RAISE NOTICE '📈 Continuous aggregates: ml_training_data, hourly_performance, daily_profitability';
    RAISE NOTICE '🗜️  Compression policies: Enabled for all tables';
    RAISE NOTICE '🔧 Helper functions: get_latest_volatility(), get_symbol_performance(), get_model_accuracy()';
    RAISE NOTICE '';
    RAISE NOTICE 'Ready for production data collection!';
END $$;
