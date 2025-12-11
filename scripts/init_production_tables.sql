-- Production Trading System Database Schema
-- Initializes tables for transaction logging, monitoring, and analytics

-- Enable TimescaleDB extension if not already enabled
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================================
-- TRANSACTION LOGGING TABLES
-- ============================================================================

-- Trade execution log
CREATE TABLE IF NOT EXISTS trade_executions (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    trade_id VARCHAR(100) UNIQUE NOT NULL,

    -- Trade details
    action VARCHAR(20) NOT NULL,  -- 'BUY', 'SELL', 'FLASH_LOAN_ARB', etc.
    token_in VARCHAR(50),
    token_out VARCHAR(50),
    amount_in NUMERIC(30, 18),
    amount_out NUMERIC(30, 18),

    -- Execution details
    tx_hash VARCHAR(100),
    block_number BIGINT,
    gas_used BIGINT,
    gas_price_gwei NUMERIC(10, 2),
    gas_cost_eth NUMERIC(18, 8),

    -- Profit/Loss
    expected_profit_eth NUMERIC(18, 8),
    actual_profit_eth NUMERIC(18, 8),
    profit_usd NUMERIC(18, 2),
    slippage_bps NUMERIC(10, 4),

    -- AI Decision
    ai_confidence NUMERIC(5, 4),
    ai_decision_id VARCHAR(100),
    strategy_name VARCHAR(100),

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',  -- PENDING, SUCCESS, FAILED, REVERTED
    error_message TEXT,

    -- Metadata
    metadata JSONB,

    -- Indexes
    INDEX idx_timestamp (timestamp DESC),
    INDEX idx_status (status),
    INDEX idx_tx_hash (tx_hash),
    INDEX idx_strategy (strategy_name)
);

-- Convert to TimescaleDB hypertable
SELECT create_hypertable('trade_executions', 'timestamp', if_not_exists => TRUE);

-- AI Decisions log
CREATE TABLE IF NOT EXISTS ai_decisions (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decision_id VARCHAR(100) UNIQUE NOT NULL,

    -- Decision details
    opportunity_type VARCHAR(50) NOT NULL,
    action VARCHAR(20) NOT NULL,
    confidence NUMERIC(5, 4) NOT NULL,
    expected_profit_eth NUMERIC(18, 8),

    -- Risk assessment
    risk_score NUMERIC(5, 4),
    position_size_eth NUMERIC(18, 8),

    -- Validation
    passed_safety_checks BOOLEAN DEFAULT FALSE,
    failed_checks TEXT[],

    -- Execution
    executed BOOLEAN DEFAULT FALSE,
    execution_timestamp TIMESTAMPTZ,
    trade_id VARCHAR(100) REFERENCES trade_executions(trade_id),

    -- AI Model info
    model_version VARCHAR(50),
    features JSONB,

    -- Metadata
    metadata JSONB,

    -- Indexes
    INDEX idx_decision_timestamp (timestamp DESC),
    INDEX idx_executed (executed),
    INDEX idx_confidence (confidence DESC)
);

-- Convert to TimescaleDB hypertable
SELECT create_hypertable('ai_decisions', 'timestamp', if_not_exists => TRUE);

-- ============================================================================
-- CIRCUIT BREAKER & SAFETY LOGS
-- ============================================================================

-- Circuit breaker events
CREATE TABLE IF NOT EXISTS circuit_breaker_events (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Event details
    breaker_type VARCHAR(50) NOT NULL,  -- WIN_RATE, DRAWDOWN, GAS_COST, etc.
    triggered BOOLEAN DEFAULT TRUE,
    severity VARCHAR(20) NOT NULL,  -- WARNING, CRITICAL, EMERGENCY

    -- Metrics at time of trigger
    current_value NUMERIC(18, 8),
    threshold_value NUMERIC(18, 8),

    -- Actions taken
    action_taken VARCHAR(100),
    trading_halted BOOLEAN DEFAULT FALSE,

    -- Resolution
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,

    -- Metadata
    metadata JSONB,

    -- Indexes
    INDEX idx_breaker_timestamp (timestamp DESC),
    INDEX idx_breaker_type (breaker_type),
    INDEX idx_resolved (resolved)
);

-- Convert to TimescaleDB hypertable
SELECT create_hypertable('circuit_breaker_events', 'timestamp', if_not_exists => TRUE);

-- Safety validation log
CREATE TABLE IF NOT EXISTS safety_validations (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Associated decision/trade
    decision_id VARCHAR(100),
    trade_id VARCHAR(100),

    -- Validation results
    check_name VARCHAR(100) NOT NULL,
    passed BOOLEAN NOT NULL,
    value_checked NUMERIC(30, 18),
    threshold NUMERIC(30, 18),

    -- Details
    message TEXT,
    metadata JSONB,

    -- Indexes
    INDEX idx_validation_timestamp (timestamp DESC),
    INDEX idx_check_name (check_name),
    INDEX idx_passed (passed)
);

-- Convert to TimescaleDB hypertable
SELECT create_hypertable('safety_validations', 'timestamp', if_not_exists => TRUE);

-- ============================================================================
-- PERFORMANCE METRICS TABLES
-- ============================================================================

-- Portfolio snapshots (hourly)
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Portfolio value
    total_value_eth NUMERIC(18, 8) NOT NULL,
    total_value_usd NUMERIC(18, 2),

    -- Performance metrics
    hourly_pnl_eth NUMERIC(18, 8),
    daily_pnl_eth NUMERIC(18, 8),
    total_pnl_eth NUMERIC(18, 8),

    -- Position details
    positions JSONB,
    cash_balance_eth NUMERIC(18, 8),

    -- Risk metrics
    current_drawdown_pct NUMERIC(10, 4),
    max_drawdown_pct NUMERIC(10, 4),
    sharpe_ratio NUMERIC(10, 4),

    -- Metadata
    metadata JSONB,

    -- Indexes
    INDEX idx_portfolio_timestamp (timestamp DESC)
);

-- Convert to TimescaleDB hypertable with 1-hour chunks
SELECT create_hypertable('portfolio_snapshots', 'timestamp',
                        chunk_time_interval => INTERVAL '1 hour',
                        if_not_exists => TRUE);

-- Trading session summaries
CREATE TABLE IF NOT EXISTS trading_sessions (
    id BIGSERIAL PRIMARY KEY,
    session_start TIMESTAMPTZ NOT NULL,
    session_end TIMESTAMPTZ,

    -- Session stats
    total_trades INTEGER DEFAULT 0,
    successful_trades INTEGER DEFAULT 0,
    failed_trades INTEGER DEFAULT 0,
    win_rate NUMERIC(5, 2),

    -- P&L
    total_pnl_eth NUMERIC(18, 8),
    total_pnl_usd NUMERIC(18, 2),
    largest_win_eth NUMERIC(18, 8),
    largest_loss_eth NUMERIC(18, 8),

    -- AI performance
    ai_decisions_made INTEGER DEFAULT 0,
    ai_decisions_executed INTEGER DEFAULT 0,
    avg_confidence NUMERIC(5, 4),

    -- Gas costs
    total_gas_eth NUMERIC(18, 8),
    avg_gas_gwei NUMERIC(10, 2),

    -- Metadata
    metadata JSONB,

    -- Indexes
    INDEX idx_session_start (session_start DESC),
    INDEX idx_session_end (session_end DESC)
);

-- ============================================================================
-- VIEWS FOR ANALYTICS
-- ============================================================================

-- Recent profitable trades view
CREATE OR REPLACE VIEW recent_profitable_trades AS
SELECT
    timestamp,
    trade_id,
    action,
    token_in,
    token_out,
    actual_profit_eth,
    profit_usd,
    ai_confidence,
    gas_cost_eth,
    tx_hash
FROM trade_executions
WHERE status = 'SUCCESS'
  AND actual_profit_eth > 0
ORDER BY timestamp DESC
LIMIT 100;

-- Daily performance summary view
CREATE OR REPLACE VIEW daily_performance AS
SELECT
    DATE(timestamp) as date,
    COUNT(*) as total_trades,
    COUNT(*) FILTER (WHERE status = 'SUCCESS') as successful_trades,
    COUNT(*) FILTER (WHERE actual_profit_eth > 0) as profitable_trades,
    SUM(actual_profit_eth) as total_profit_eth,
    SUM(profit_usd) as total_profit_usd,
    AVG(ai_confidence) as avg_confidence,
    SUM(gas_cost_eth) as total_gas_eth
FROM trade_executions
WHERE timestamp >= NOW() - INTERVAL '30 days'
GROUP BY DATE(timestamp)
ORDER BY date DESC;

-- Active circuit breakers view
CREATE OR REPLACE VIEW active_circuit_breakers AS
SELECT
    breaker_type,
    timestamp,
    current_value,
    threshold_value,
    severity,
    action_taken
FROM circuit_breaker_events
WHERE triggered = TRUE
  AND resolved = FALSE
ORDER BY timestamp DESC;

-- ============================================================================
-- CONTINUOUS AGGREGATES (TimescaleDB feature)
-- ============================================================================

-- Hourly trading summary
CREATE MATERIALIZED VIEW IF NOT EXISTS hourly_trading_summary
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp) AS hour,
    COUNT(*) as trade_count,
    COUNT(*) FILTER (WHERE status = 'SUCCESS') as successful_count,
    SUM(actual_profit_eth) as total_profit_eth,
    AVG(ai_confidence) as avg_confidence,
    SUM(gas_cost_eth) as total_gas_eth
FROM trade_executions
GROUP BY hour;

-- Refresh policy for hourly summary (refresh every hour)
SELECT add_continuous_aggregate_policy('hourly_trading_summary',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE);

-- ============================================================================
-- RETENTION POLICIES (TimescaleDB feature)
-- ============================================================================

-- Keep detailed trade data for 90 days, then compress
SELECT add_compression_policy('trade_executions',
    INTERVAL '7 days',
    if_not_exists => TRUE);

SELECT add_retention_policy('trade_executions',
    INTERVAL '90 days',
    if_not_exists => TRUE);

-- Keep AI decisions for 60 days
SELECT add_retention_policy('ai_decisions',
    INTERVAL '60 days',
    if_not_exists => TRUE);

-- Keep circuit breaker events for 30 days
SELECT add_retention_policy('circuit_breaker_events',
    INTERVAL '30 days',
    if_not_exists => TRUE);

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
    RAISE NOTICE 'Production trading database schema initialized successfully!';
    RAISE NOTICE 'Tables created: trade_executions, ai_decisions, circuit_breaker_events, safety_validations, portfolio_snapshots, trading_sessions';
    RAISE NOTICE 'Views created: recent_profitable_trades, daily_performance, active_circuit_breakers';
    RAISE NOTICE 'Continuous aggregates: hourly_trading_summary';
    RAISE NOTICE 'Retention policies applied for data lifecycle management';
END $$;
