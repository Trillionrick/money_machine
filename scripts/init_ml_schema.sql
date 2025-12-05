-- ML Training Data Schema for Arbitrage System
-- Run with: psql -h localhost -p 5433 -U trading_user -d trading_db -f scripts/init_ml_schema.sql

-- Arbitrage opportunities table for ML training
CREATE TABLE IF NOT EXISTS arbitrage_opportunities (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol VARCHAR(20) NOT NULL,
    chain VARCHAR(20) NOT NULL DEFAULT 'ethereum',

    -- Prices
    cex_price DECIMAL(20, 8) NOT NULL,
    dex_price DECIMAL(20, 8) NOT NULL,
    edge_bps DECIMAL(10, 4) NOT NULL,

    -- Market conditions
    pool_liquidity_quote DECIMAL(20, 2),
    gas_price_gwei DECIMAL(10, 2) NOT NULL,
    hour_of_day INT NOT NULL,

    -- Slippage (for ML training)
    estimated_slippage_bps DECIMAL(10, 4) NOT NULL DEFAULT 50.0,
    actual_slippage_bps DECIMAL(10, 4),  -- NULL if not executed

    -- Execution details
    trade_size_quote DECIMAL(20, 2),
    hop_count INT DEFAULT 2,
    route_path TEXT,
    execution_path VARCHAR(20),  -- 'flash_loan' or 'regular'

    -- Outcome
    executed BOOLEAN DEFAULT FALSE,
    profitable BOOLEAN,
    profit_eth DECIMAL(20, 8),
    profit_quote DECIMAL(20, 2),
    gas_cost_eth DECIMAL(20, 8),

    -- Metadata
    ml_model_version VARCHAR(50),
    notes TEXT
);

-- Convert to hypertable for time-series optimization
SELECT create_hypertable('arbitrage_opportunities', 'timestamp',
    if_not_exists => TRUE,
    migrate_data => TRUE
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_arb_symbol_time ON arbitrage_opportunities (symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_arb_executed ON arbitrage_opportunities (executed, profitable) WHERE executed = TRUE;
CREATE INDEX IF NOT EXISTS idx_arb_chain ON arbitrage_opportunities (chain, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_arb_training ON arbitrage_opportunities (timestamp DESC)
    WHERE executed = TRUE AND actual_slippage_bps IS NOT NULL;

-- ML model performance tracking
CREATE TABLE IF NOT EXISTS ml_model_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,

    -- Performance metrics
    mae DECIMAL(10, 4),  -- Mean Absolute Error
    rmse DECIMAL(10, 4),  -- Root Mean Squared Error
    r2_score DECIMAL(10, 6),  -- R² coefficient

    -- Training stats
    training_samples INT,
    test_samples INT,
    training_duration_seconds INT,

    -- Metadata
    hyperparameters JSONB,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_ml_metrics_time ON ml_model_metrics (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ml_metrics_model ON ml_model_metrics (model_name, model_version, timestamp DESC);

-- View for easy ML training data access
CREATE OR REPLACE VIEW ml_training_data AS
SELECT
    timestamp,
    symbol,
    chain,
    edge_bps,
    trade_size_quote,
    pool_liquidity_quote,
    gas_price_gwei,
    hour_of_day,
    hop_count,
    CASE WHEN chain = 'polygon' THEN 1 ELSE 0 END as is_polygon,
    estimated_slippage_bps,
    actual_slippage_bps,
    profitable,
    profit_eth
FROM arbitrage_opportunities
WHERE executed = TRUE
  AND actual_slippage_bps IS NOT NULL
ORDER BY timestamp DESC;

COMMENT ON TABLE arbitrage_opportunities IS 'Tracks all detected arbitrage opportunities for ML training and analysis';
COMMENT ON TABLE ml_model_metrics IS 'Tracks ML model performance over time';
COMMENT ON VIEW ml_training_data IS 'Clean view of training data for ML models';
