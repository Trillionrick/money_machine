# Grafana Complete Setup for DEX/Crypto Arbitrage System

Complete integration of Grafana monitoring stack with Database Observability, log aggregation, and alerting for your crypto arbitrage flash loan system.

## Architecture Overview

Your monitoring stack now includes:

1. **Grafana** (port 3000) - Visualization and alerting
2. **Prometheus** (port 9091) - Metrics collection and time-series database
3. **Loki** (port 3100) - Log aggregation and querying
4. **Promtail** - Log collection from application and Docker containers
5. **AlertManager** (port 9093) - Alert routing and notification management
6. **postgres_exporter** (port 9187) - TimescaleDB/PostgreSQL metrics
7. **TimescaleDB** (port 5433) - Time-series data storage with pg_stat_statements enabled

## Quick Start

### 1. Start the Complete Stack

```bash
# Copy environment template
cp .env.example .env

# Edit .env and configure:
# - DISCORD_WEBHOOK_URL (for alerts)
# - GRAFANA_PASSWORD (change from default!)
# - Other trading credentials

# Start all services
docker-compose up -d

# Verify all services are running
docker-compose ps

# Check logs
docker-compose logs -f grafana
docker-compose logs -f prometheus
docker-compose logs -f loki
```

### 2. Access Dashboards

- **Grafana**: http://localhost:3000
  - Username: `admin`
  - Password: Set via `GRAFANA_PASSWORD` in .env (default: `admin`)

- **Prometheus**: http://localhost:9091
- **AlertManager**: http://localhost:9093
- **Loki**: http://localhost:3100

### 3. Verify Data Sources

Grafana is pre-configured with three data sources:

1. **TimescaleDB** (PostgreSQL) - Default data source
   - Direct query access to arbitrage_opportunities table
   - Pre-configured views for metrics

2. **Prometheus** - Metrics data source
   - System metrics (CPU, memory, disk)
   - Application metrics from trading_app:9090
   - Database metrics from postgres_exporter:9187
   - Custom arbitrage metrics

3. **Loki** - Log data source
   - Application logs (structured JSON)
   - Docker container logs
   - Database logs

Navigate to **Configuration → Data Sources** to verify all are working.

## Pre-configured Dashboards

### 1. Arbitrage Monitoring (`arbitrage_monitoring.json`)

Real-time arbitrage performance dashboard showing:
- Opportunities detected (24h)
- Win rate percentage
- Total profit
- Average edge in basis points
- Top trading symbols
- Recent opportunities table
- Win rate trends over time

**Access**: Home → Dashboards → Arbitrage Monitoring

### 2. Database Observability (`database_observability.json`)

Complete database health and performance monitoring:
- Cache hit ratio
- Active connections
- Transaction rates
- Database size
- Slowest queries by total time
- Query performance statistics
- Arbitrage activity metrics
- Win rate by symbol

**Access**: Home → Dashboards → Database Observability - TimescaleDB

## Alerting Configuration

### Pre-configured Alert Rules

Located in `grafana/provisioning/alerting/arbitrage_alerts.yml`:

#### Critical Alerts (5-15min evaluation)
- **Low Win Rate**: Fires when win rate < 45% over 1 hour
- **Negative P&L**: Fires when hourly profit turns negative
- **System Down**: Fires when no activity detected for 5 minutes

#### Warning Alerts (10min evaluation)
- **High Gas Costs**: Gas costs consuming > 30% of profits
- **Low Execution Success**: Transaction success rate < 70%

#### Opportunity Alerts
- **No Opportunities**: No opportunities detected in 30 minutes
- **High Value Opportunity**: Potential profit > $100 detected

### Contact Points

Configured in `grafana/provisioning/alerting/contact_points.yml`:

1. **Discord Alerts** (Primary)
   - Uses `DISCORD_WEBHOOK_URL` from .env
   - Critical alerts: immediate notification
   - Warning alerts: grouped (10min interval)
   - Info alerts: high-value opportunities only

2. **Custom Webhook** (Optional)
   - Uses `GRAFANA_WEBHOOK_URL` from .env
   - POST requests with alert payload

3. **Email Alerts** (Optional)
   - Requires SMTP configuration in grafana.ini
   - Uses `ALERT_EMAIL_ADDRESSES` from .env

### Setting Up Discord Alerts

1. In your Discord server, go to Server Settings → Integrations → Webhooks
2. Click "New Webhook"
3. Name it "Arbitrage Alerts"
4. Select channel for alerts
5. Copy webhook URL
6. Add to .env:
   ```bash
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook_id/your_webhook_token
   ```
7. Restart Grafana:
   ```bash
   docker-compose restart grafana
   ```

## Database Observability Deep Dive

### What's Enabled

The system automatically enables comprehensive database monitoring:

**PostgreSQL Extensions**:
- `pg_stat_statements` - Query performance tracking
- TimescaleDB hypertables for efficient time-series storage

**Monitoring User**:
- Username: `postgres_exporter`
- Password: `exporter_pass_change_in_production` (change in production!)
- Permissions: pg_monitor, pg_read_all_stats, pg_read_all_settings

**Custom Views**:
1. `v_arbitrage_metrics_5m` - 5-minute rolling metrics
2. `v_arbitrage_win_rate` - Win rate by symbol (1h window)
3. `v_system_health` - Overall system status

### Custom Metrics Collected

See `monitoring/postgres_exporter_queries.yaml` for full list:

**Arbitrage-Specific**:
- Recent opportunity count (5min window)
- Executed vs total opportunities
- Profitable trade count
- Average edge in basis points
- Total profit in USD
- Win rate per symbol
- Gas cost efficiency metrics
- Execution success rates
- Chain-specific performance
- Pool liquidity tracking

**Database Performance**:
- Top queries by total time
- Query execution statistics
- Connection counts by application
- Long-running query detection (>30s)
- TimescaleDB hypertable statistics

### Query Performance Analysis

Access slow query analysis:

**Via TimescaleDB Data Source**:
```sql
SELECT
  LEFT(query, 100) as query_snippet,
  calls,
  ROUND(total_exec_time / 1000, 2) as total_time_seconds,
  ROUND(mean_exec_time, 2) as mean_time_ms,
  ROUND(max_exec_time, 2) as max_time_ms
FROM pg_stat_statements
WHERE query NOT LIKE '%pg_stat_statements%'
ORDER BY total_exec_time DESC
LIMIT 20;
```

**Via Prometheus**:
```promql
pg_stat_statements_calls
pg_stat_statements_total_time_seconds
pg_stat_statements_mean_time_ms
```

## Log Aggregation with Loki

### What's Collected

**Application Logs** (`./logs/*.log`):
- Structured JSON logs from your trading application
- Automatic label extraction: level, logger, event, symbol
- Parsed fields: profit, edge_bps, gas_cost, tx_hash

**Docker Container Logs**:
- All containers in trading_network
- Labeled by: container, image, service
- Includes: trading_app, timescaledb, prometheus, grafana, redis

**Database Logs**:
- PostgreSQL activity logs
- Error logs and warnings
- Slow query logs

### Querying Logs in Grafana

Navigate to **Explore** and select **Loki** data source:

**Example queries**:
```logql
# All application logs
{job="trading_app"}

# Only errors
{job="trading_app", level="ERROR"}

# Profitable trades
{job="trading_app"} |= "profitable" | json

# Specific symbol
{job="trading_app", symbol="ETH/USDC"}

# Transaction hashes
{job="trading_app"} | json | tx_hash != ""

# Docker container logs
{job="docker_containers", service="timescaledb"}

# Rate of errors
rate({job="trading_app", level="ERROR"}[5m])
```

### Log Retention

Configured in `monitoring/loki-config.yaml`:
- **Retention period**: 31 days (744h)
- **Max ingestion rate**: 50 MB/s
- **Max burst**: 100 MB/s
- **Max query series**: 10,000
- **Split interval**: 24h for large queries

## Prometheus Metrics

### Application Metrics

Your trading app exposes metrics on port 9090:

**Endpoints**:
- `http://trading_app:9090/metrics` - Main application metrics
- `http://trading_app:8080/api/ai/metrics/prometheus` - AI system metrics

**Scrape Configuration**:
```yaml
# Application metrics (10s interval)
- job_name: 'trading_app'
  static_configs:
    - targets: ['trading_app:9090']

# AI metrics (30s interval)
- job_name: 'ai_metrics'
  static_configs:
    - targets: ['trading_app:8080']
  metrics_path: '/api/ai/metrics/prometheus'
```

### Custom Arbitrage Metrics

Exposed by postgres_exporter from custom queries:

```promql
# Opportunities detected (5min)
arbitrage_opportunities_recent_count

# Executed count (5min)
arbitrage_opportunities_executed_count

# Profitable count (5min)
arbitrage_opportunities_profitable_count

# Average edge (basis points)
arbitrage_opportunities_avg_edge_bps

# Total profit (USD, 5min)
arbitrage_opportunities_total_profit_5m

# Win rate by symbol
arbitrage_win_rate_by_symbol_win_rate{symbol="ETH/USDC"}

# Gas efficiency
arbitrage_gas_efficiency_gas_to_profit_ratio
```

### Database Metrics

Standard postgres_exporter metrics:

```promql
# Connection count
pg_stat_activity_count{datname="trading_db"}

# Transaction rate
rate(pg_stat_database_xact_commit{datname="trading_db"}[5m])

# Cache hit ratio
pg_stat_database_blks_hit / (pg_stat_database_blks_hit + pg_stat_database_blks_read)

# Database size
pg_database_size_bytes{datname="trading_db"}
```

## Advanced Configuration

### Creating Custom Dashboards

1. Navigate to **Dashboards → New Dashboard**
2. Add Panel
3. Select data source (TimescaleDB, Prometheus, or Loki)
4. Build your query
5. Configure visualization
6. Save dashboard

**Example: CEX-DEX Price Spread Panel**:
```sql
-- TimescaleDB query
SELECT
  time_bucket('1 minute', timestamp) AS time,
  symbol,
  AVG(edge_bps) as avg_spread
FROM arbitrage_opportunities
WHERE $__timeFilter(timestamp)
GROUP BY time, symbol
ORDER BY time;
```

### Custom Alert Rules

Create new alerts via UI:

1. **Alerting → Alert rules → New alert rule**
2. Name your rule
3. Select data source
4. Define condition (e.g., profit < 0)
5. Set evaluation interval
6. Assign contact point
7. Add labels and annotations
8. Save

**Example: Flash Loan Failure Alert**:
```sql
SELECT COUNT(*) as failed_flash_loans
FROM arbitrage_opportunities
WHERE timestamp > NOW() - INTERVAL '15 minutes'
AND executed = TRUE
AND tx_hash IS NULL
AND edge_bps > 50
```
Condition: `failed_flash_loans > 3`

### Modifying Retention Policies

**Prometheus** (`monitoring/prometheus.yml`):
```yaml
command:
  - '--storage.tsdb.retention.time=30d'  # Change retention
  - '--storage.tsdb.retention.size=50GB'  # Add size limit
```

**Loki** (`monitoring/loki-config.yaml`):
```yaml
limits_config:
  retention_period: 744h  # Change from 31 days
```

**TimescaleDB**:
```sql
-- Set retention policy on hypertable
SELECT add_retention_policy('arbitrage_opportunities', INTERVAL '90 days');
```

## Troubleshooting

### Grafana Can't Connect to Data Source

**Check data source configuration**:
```bash
# Test TimescaleDB connection
docker exec -it trading_timescaledb psql -U trading_user -d trading_db -c "SELECT 1;"

# Test Prometheus
curl http://localhost:9091/-/healthy

# Test Loki
curl http://localhost:3100/ready
```

**Verify network connectivity**:
```bash
# From Grafana container
docker exec -it trading_grafana wget -O- http://timescaledb:5432
docker exec -it trading_grafana wget -O- http://prometheus:9090/-/healthy
docker exec -it trading_grafana wget -O- http://loki:3100/ready
```

### No Metrics from postgres_exporter

**Check postgres_exporter logs**:
```bash
docker-compose logs postgres_exporter
```

**Common issues**:
1. TimescaleDB not ready → Wait for health check
2. pg_stat_statements not enabled → Check docker-compose command
3. Connection string incorrect → Verify DATA_SOURCE_NAME

**Manual test**:
```bash
# Check if metrics endpoint is working
curl http://localhost:9187/metrics
```

### Alerts Not Firing

**Check alert rule state**:
- Navigate to **Alerting → Alert rules**
- Look for rule status (Normal, Pending, Alerting)
- Check "Last evaluation" timestamp

**Verify contact point**:
- **Alerting → Contact points**
- Click "Test" button to send test alert
- Check Discord webhook is valid

**Review notification policy**:
- **Alerting → Notification policies**
- Verify matchers are correct
- Check repeat intervals

### Loki Not Receiving Logs

**Check Promtail status**:
```bash
docker-compose logs promtail

# Verify Promtail can reach Loki
docker exec -it trading_promtail wget -O- http://loki:3100/ready
```

**Verify log file permissions**:
```bash
# Check logs directory
ls -la ./logs/

# Ensure readable by Promtail (runs as root in container)
chmod -R 644 ./logs/*.log
```

**Test log ingestion**:
```bash
# Send test log to Loki
curl -X POST "http://localhost:3100/loki/api/v1/push" \
  -H "Content-Type: application/json" \
  -d '{"streams": [{"stream": {"job": "test"}, "values": [["'$(date +%s)000000000'", "test message"]]}]}'
```

### Database Performance Issues

**Check pg_stat_statements**:
```sql
-- Verify extension is enabled
SELECT * FROM pg_extension WHERE extname = 'pg_stat_statements';

-- Check if queries are being tracked
SELECT COUNT(*) FROM pg_stat_statements;
```

**Reset query statistics** (if needed):
```sql
-- Warning: This clears all historical query stats
SELECT pg_stat_statements_reset();
```

**Analyze slow queries**:
```sql
-- Find queries with high mean execution time
SELECT
  LEFT(query, 80) as query,
  calls,
  mean_exec_time,
  max_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

## Production Hardening

### Security Checklist

- [ ] Change default Grafana password (set `GRAFANA_PASSWORD` in .env)
- [ ] Change TimescaleDB password (update `POSTGRES_PASSWORD` in docker-compose.yml)
- [ ] Change postgres_exporter password (update in docker-compose.yml and init script)
- [ ] Restrict Grafana access via reverse proxy (nginx, Caddy, Traefik)
- [ ] Enable HTTPS for Grafana (mount TLS certs)
- [ ] Configure firewall rules (only expose necessary ports)
- [ ] Use secrets management (Docker Secrets, HashiCorp Vault)
- [ ] Enable Grafana audit logging
- [ ] Restrict Prometheus/Loki access to internal network only

### Resource Optimization

**For production workloads**, adjust docker-compose resource limits:

```yaml
# Example: High-frequency trading setup
grafana:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 2G

prometheus:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 4G

loki:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 2G
```

### Backup Strategy

**Grafana dashboards and alerts**:
```bash
# Backup Grafana database
docker exec trading_grafana sqlite3 /var/lib/grafana/grafana.db ".backup /var/lib/grafana/backup.db"
docker cp trading_grafana:/var/lib/grafana/backup.db ./backups/grafana-$(date +%Y%m%d).db

# Or use provisioning (recommended - already configured)
# All dashboards and alerts are in ./grafana/provisioning/
```

**Prometheus data**:
```bash
# Snapshot Prometheus data
docker exec trading_prometheus promtool tsdb snapshot /prometheus
docker cp trading_prometheus:/prometheus/snapshots/XXXXXXX ./backups/prometheus-$(date +%Y%m%d)
```

**Loki data**:
```bash
# Backup Loki chunks (if using local storage)
docker cp trading_loki:/loki/chunks ./backups/loki-chunks-$(date +%Y%m%d)
```

**TimescaleDB**:
```bash
# Full database backup
docker exec trading_timescaledb pg_dump -U trading_user -d trading_db -F c -f /tmp/backup.dump
docker cp trading_timescaledb:/tmp/backup.dump ./backups/timescaledb-$(date +%Y%m%d).dump
```

## Integration with Existing System

### Application Metrics Instrumentation

Your Python trading application should expose metrics via Prometheus client:

```python
from prometheus_client import Counter, Gauge, Histogram, start_http_server

# Define metrics
arbitrage_opportunities_total = Counter(
    'arbitrage_opportunities_total',
    'Total arbitrage opportunities detected',
    ['symbol', 'chain']
)

current_win_rate = Gauge(
    'arbitrage_win_rate',
    'Current win rate percentage',
    ['symbol']
)

gas_cost_histogram = Histogram(
    'arbitrage_gas_cost_usd',
    'Gas cost distribution in USD',
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0]
)

# Start metrics server on port 9090
start_http_server(9090)

# Instrument your code
arbitrage_opportunities_total.labels(
    symbol='ETH/USDC',
    chain='ethereum'
).inc()

current_win_rate.labels(symbol='ETH/USDC').set(0.65)
gas_cost_histogram.observe(0.23)
```

### Structured Logging

Ensure your application logs are JSON-formatted for Loki:

```python
import structlog

# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()

# Log with structured fields
logger.info(
    "arbitrage_opportunity_detected",
    symbol="ETH/USDC",
    edge_bps=45.2,
    profit_usd=123.45,
    gas_cost_usd=8.50,
    pool_liquidity_usd=500000
)

# Log trades
logger.info(
    "trade_executed",
    symbol="ETH/USDC",
    profitable=True,
    tx_hash="0x1234...abcd",
    profit_usd=114.95,
    gas_cost_usd=8.50
)
```

### Database Schema Requirements

The alert rules expect this schema:

```sql
CREATE TABLE arbitrage_opportunities (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    chain VARCHAR(20),
    edge_bps NUMERIC(10, 2),
    pool_liquidity_quote NUMERIC(20, 2),
    executed BOOLEAN DEFAULT FALSE,
    profitable BOOLEAN DEFAULT FALSE,
    profit_quote NUMERIC(20, 4),
    gas_cost_quote NUMERIC(20, 6),
    tx_hash VARCHAR(66)
);

-- Convert to hypertable for time-series performance
SELECT create_hypertable('arbitrage_opportunities', 'timestamp');
```

## Next Steps

1. **Customize Dashboards**: Modify existing dashboards or create new ones for your specific KPIs
2. **Tune Alert Thresholds**: Adjust alert rules based on your risk tolerance
3. **Add Custom Metrics**: Instrument additional application metrics
4. **Set Up Backup Automation**: Schedule regular backups of Grafana, Prometheus, and TimescaleDB
5. **Monitor Resource Usage**: Track container resource consumption and adjust limits
6. **Explore Advanced Features**:
   - Grafana alerting with silences and maintenance windows
   - Loki pattern detection for anomaly detection
   - Prometheus recording rules for pre-computed metrics
   - TimescaleDB continuous aggregates for real-time analytics

## Additional Resources

- **Grafana Documentation**: https://grafana.com/docs/grafana/latest/
- **Prometheus Query Language**: https://prometheus.io/docs/prometheus/latest/querying/basics/
- **LogQL (Loki Query Language)**: https://grafana.com/docs/loki/latest/logql/
- **TimescaleDB Best Practices**: https://docs.timescale.com/timescaledb/latest/how-to-guides/
- **postgres_exporter Metrics**: https://github.com/prometheus-community/postgres_exporter

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review container logs: `docker-compose logs <service>`
3. Verify configuration files in `./monitoring/` and `./grafana/provisioning/`
4. Test data source connectivity from Grafana UI
5. Consult official documentation links above

---

**Status**: ✅ Complete Integration
**Version**: 1.0
**Last Updated**: 2025-12-09
