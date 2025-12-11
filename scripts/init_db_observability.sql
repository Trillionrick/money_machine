-- Database Observability Setup for TimescaleDB
-- Enables pg_stat_statements and other monitoring extensions
-- This script runs automatically on TimescaleDB container initialization

-- Enable pg_stat_statements extension for query performance monitoring
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Verify pg_stat_statements is enabled
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'
    ) THEN
        RAISE EXCEPTION 'pg_stat_statements extension not found. Check shared_preload_libraries in postgresql.conf';
    END IF;
END $$;

-- Enable pg_stat_monitor if available (alternative to pg_stat_statements)
-- Note: This is optional and may not be available in all PostgreSQL distributions
-- CREATE EXTENSION IF NOT EXISTS pg_stat_monitor;

-- Create monitoring user for postgres_exporter (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'postgres_exporter') THEN
        CREATE USER postgres_exporter WITH PASSWORD 'exporter_pass_change_in_production';
    END IF;
END $$;

-- Grant necessary permissions to postgres_exporter user
GRANT pg_monitor TO postgres_exporter;
GRANT pg_read_all_stats TO postgres_exporter;
GRANT pg_read_all_settings TO postgres_exporter;

-- Grant connection to trading_db
GRANT CONNECT ON DATABASE trading_db TO postgres_exporter;

-- Grant usage on schema
GRANT USAGE ON SCHEMA public TO postgres_exporter;

-- Grant select on specific tables for custom queries
GRANT SELECT ON arbitrage_opportunities TO postgres_exporter;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO postgres_exporter;

-- Ensure future tables also grant permissions
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO postgres_exporter;

-- Grant access to pg_stat_statements
GRANT SELECT ON pg_stat_statements TO postgres_exporter;

-- Verify permissions
DO $$
DECLARE
    permission_check INT;
BEGIN
    SELECT COUNT(*)
    INTO permission_check
    FROM pg_stat_statements
    LIMIT 1;

    RAISE NOTICE 'pg_stat_statements is accessible. Database Observability setup complete!';
EXCEPTION
    WHEN OTHERS THEN
        RAISE WARNING 'Could not access pg_stat_statements: %', SQLERRM;
END $$;

-- Create view for easy monitoring of arbitrage metrics
CREATE OR REPLACE VIEW v_arbitrage_metrics_5m AS
SELECT
    COUNT(*) as total_opportunities,
    COUNT(*) FILTER (WHERE executed = TRUE) as executed_count,
    COUNT(*) FILTER (WHERE profitable = TRUE) as profitable_count,
    ROUND(AVG(edge_bps)::numeric, 2) as avg_edge_bps,
    ROUND(SUM(profit_quote)::numeric, 2) as total_profit,
    ROUND(AVG(gas_cost_quote)::numeric, 4) as avg_gas_cost
FROM arbitrage_opportunities
WHERE timestamp > NOW() - INTERVAL '5 minutes';

-- Grant access to the view
GRANT SELECT ON v_arbitrage_metrics_5m TO postgres_exporter;

-- Create view for win rate by symbol
CREATE OR REPLACE VIEW v_arbitrage_win_rate AS
SELECT
    symbol,
    COUNT(*) as total_trades,
    COUNT(*) FILTER (WHERE profitable = TRUE) as profitable_trades,
    ROUND(
        (COUNT(*) FILTER (WHERE profitable = TRUE)::FLOAT /
        NULLIF(COUNT(*) FILTER (WHERE executed = TRUE), 0))::numeric,
        4
    ) as win_rate,
    ROUND(AVG(edge_bps)::numeric, 2) as avg_edge_bps,
    ROUND(SUM(profit_quote)::numeric, 2) as total_profit
FROM arbitrage_opportunities
WHERE timestamp > NOW() - INTERVAL '1 hour'
AND executed = TRUE
GROUP BY symbol
ORDER BY total_trades DESC;

-- Grant access to the view
GRANT SELECT ON v_arbitrage_win_rate TO postgres_exporter;

-- Create view for system health monitoring
CREATE OR REPLACE VIEW v_system_health AS
SELECT
    -- Recent activity check
    CASE
        WHEN MAX(timestamp) > NOW() - INTERVAL '5 minutes' THEN 'healthy'
        WHEN MAX(timestamp) > NOW() - INTERVAL '15 minutes' THEN 'warning'
        ELSE 'critical'
    END as system_status,
    MAX(timestamp) as last_activity,
    EXTRACT(EPOCH FROM (NOW() - MAX(timestamp))) as seconds_since_last_activity,
    -- Metrics
    COUNT(*) FILTER (WHERE timestamp > NOW() - INTERVAL '1 hour') as opportunities_last_hour,
    COUNT(*) FILTER (WHERE executed = TRUE AND timestamp > NOW() - INTERVAL '1 hour') as executions_last_hour,
    -- Performance
    ROUND(
        (COUNT(*) FILTER (WHERE profitable = TRUE AND timestamp > NOW() - INTERVAL '1 hour')::FLOAT /
        NULLIF(COUNT(*) FILTER (WHERE executed = TRUE AND timestamp > NOW() - INTERVAL '1 hour'), 0))::numeric,
        4
    ) as win_rate_1h
FROM arbitrage_opportunities;

-- Grant access to the view
GRANT SELECT ON v_system_health TO postgres_exporter;

-- Increase track_activity_query_size for better query monitoring
-- Note: This requires PostgreSQL restart to take effect
-- Add to postgresql.conf: track_activity_query_size = 4096

-- Set up automatic statistics collection for better query planning
ALTER TABLE arbitrage_opportunities SET (autovacuum_analyze_scale_factor = 0.05);
ALTER TABLE arbitrage_opportunities SET (autovacuum_vacuum_scale_factor = 0.1);

-- Create index on timestamp for faster time-based queries (if not exists)
CREATE INDEX IF NOT EXISTS idx_arbitrage_opportunities_timestamp
ON arbitrage_opportunities (timestamp DESC);

-- Create index on executed + profitable for win rate queries
CREATE INDEX IF NOT EXISTS idx_arbitrage_opportunities_executed_profitable
ON arbitrage_opportunities (executed, profitable)
WHERE timestamp > NOW() - INTERVAL '7 days';

-- Create index on symbol for per-symbol metrics
CREATE INDEX IF NOT EXISTS idx_arbitrage_opportunities_symbol
ON arbitrage_opportunities (symbol, timestamp DESC);

-- Print success message
DO $$
BEGIN
    RAISE NOTICE '=================================================';
    RAISE NOTICE 'Database Observability setup completed successfully!';
    RAISE NOTICE '=================================================';
    RAISE NOTICE '';
    RAISE NOTICE 'Enabled extensions:';
    RAISE NOTICE '  - pg_stat_statements';
    RAISE NOTICE '';
    RAISE NOTICE 'Created users:';
    RAISE NOTICE '  - postgres_exporter (for metrics collection)';
    RAISE NOTICE '';
    RAISE NOTICE 'Created views:';
    RAISE NOTICE '  - v_arbitrage_metrics_5m';
    RAISE NOTICE '  - v_arbitrage_win_rate';
    RAISE NOTICE '  - v_system_health';
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '  1. Verify postgres_exporter can connect';
    RAISE NOTICE '  2. Check Prometheus targets at http://localhost:9091/targets';
    RAISE NOTICE '  3. View Grafana dashboards at http://localhost:3000';
    RAISE NOTICE '=================================================';
END $$;
