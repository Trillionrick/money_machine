# Grafana Quick Start Checklist

Complete monitoring stack for your crypto arbitrage system - get up and running in 5 minutes.

🚀 Quick Setup (5 Minutes)

1. Configure Environment

bash
# Copy template
cp .env.example .env

# Edit .env - MINIMUM required:
nano .env


Required settings:
bash
GRAFANA_PASSWORD=change_me_now           # Your Grafana password
DISCORD_WEBHOOK_URL=https://discord...   # Discord webhook for alerts (optional)


2. Start the Stack

bash
# Start all monitoring services
docker-compose up -d

# Wait 30 seconds for services to initialize
sleep 30

# Verify everything is running
docker-compose ps


Expected output (all services should show "Up" status):

trading_app              Up      8080/tcp, 9090/tcp
trading_grafana          Up      3000/tcp
trading_prometheus       Up      9091/tcp
trading_loki             Up      3100/tcp
trading_promtail         Up
trading_alertmanager     Up      9093/tcp
trading_postgres_exporter Up     9187/tcp
trading_timescaledb      Up      5432/tcp


3. Access Grafana

Open browser: http://localhost:3000

Login:
- Username: `admin`
- Password: (from your `GRAFANA_PASSWORD` in .env)

4. Verify Data Sources

Navigate to: Configuration (⚙️) → Data Sources

Should see 3 data sources with green checkmarks:
- ✅ TimescaleDB (PostgreSQL)
- ✅ Prometheus
- ✅ Loki

If any are red, click on them and hit "Test" to see error message.

5. Open Dashboards

Navigate to: Dashboards (📊) → Browse

You should see:
- Arbitrage Monitoring - Real-time trading performance
- Database Observability - TimescaleDB - Database health and query performance

Click on each to verify data is flowing.

✅ Verification Checklist

Run these checks to confirm everything works:

Database Observability Enabled
bash
# Verify pg_stat_statements is working
docker exec trading_timescaledb psql -U trading_user -d trading_db -c "SELECT COUNT(*) FROM pg_stat_statements;"

Expected: Returns a number (likely 50-200 queries tracked)

Prometheus Scraping Metrics
bash
# Check Prometheus targets
curl -s http://localhost:9091/api/v1/targets | grep '"health":"up"' | wc -l

Expected: At least 4 targets up (trading_app, prometheus, timescaledb, ai_metrics)

Loki Receiving Logs
bash
# Query Loki for recent logs
curl -s "http://localhost:3100/loki/api/v1/query" --data-urlencode 'query={job="trading_app"}' | grep -o '"values":\[\[' | wc -l

Expected: Returns 1 (logs are present)

AlertManager Configured
bash
# Check AlertManager status
curl -s http://localhost:9093/api/v2/status | grep '"cluster":{"status":"ready"}'

Expected: Returns JSON with "ready" status

Custom Metrics Working
bash
# Check postgres_exporter custom metrics
curl -s http://localhost:9187/metrics | grep arbitrage_opportunities

Expected: Shows multiple metrics like `arbitrage_opportunities_recent_count`

📊 Quick Dashboard Tour

Arbitrage Monitoring Dashboard

Top Row Stats (5 second refresh):
- Opportunities (24h): Total opportunities detected
- Win Rate (24h): Profitable trades / executed trades
- Total Profit (24h): USD profit after gas costs
- Average Edge (24h): Mean spread in basis points

Time Series Graphs:
- Opportunities Over Time: Hourly bucketed opportunity count
- Win Rate Over Time: Rolling win rate percentage

Tables:
- Recent Opportunities: Last 50 opportunities with details
- Top Symbols: Most active trading pairs

Database Observability Dashboard

Health Indicators:
- Cache Hit Ratio: Should be > 95% (green)
- Active Connections: Current DB connections
- Transaction Rate: Commits per second
- Database Size: Total storage used

Performance Analysis:
- Slowest Queries by Total Time: Top 20 resource-intensive queries
- Connection Pool Status: Active vs idle connections

Arbitrage Metrics from DB:
- Recent Activity (5min window): Opportunities, executions, profitability
- Win Rate by Symbol: Per-pair performance

🔔 Alert Configuration

Current Alert Rules

Critical Alerts (immediate Discord notification):
- Low Win Rate: < 45% over 1 hour → Check strategy
- Negative P&L: Losing money → Review gas costs
- System Down: No activity for 5 minutes → Check trading_app container

Warning Alerts (10-minute grouped notifications):
- High Gas Costs: > 30% of profits → Wait for lower gas or increase edge threshold
- Low Execution Success: < 70% success rate → Check RPC endpoints

Info Alerts (opportunity notifications):
- High Value Opportunity: Potential profit > $100 → Manual review possible

Setting Up Discord Alerts

1. In Discord: Server Settings → Integrations → Webhooks → New Webhook
2. Name: "Arbitrage Alerts"
3. Select channel (e.g., #trading-alerts)
4. Copy webhook URL
5. Add to `.env`:
   bash
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/123456789/xxxxx
   
6. Restart Grafana:
   bash
   docker-compose restart grafana
   
7. Test alert: Alerting → Contact points → Discord Alerts → Test

🔍 Quick Troubleshooting

Problem: Grafana shows "No data"

Check data flow:
bash
# 1. Is TimescaleDB accepting connections?
docker exec trading_timescaledb pg_isready

# 2. Does arbitrage table have data?
docker exec trading_timescaledb psql -U trading_user -d trading_db -c "SELECT COUNT(*) FROM arbitrage_opportunities;"

# 3. Is trading_app running?
docker-compose logs -f --tail=50 trading_app


Problem: Alerts not firing

Verify AlertManager:
bash
# Check alert rules are loaded
curl -s http://localhost:9091/api/v1/rules | grep arbitrage

# Check AlertManager has alerts
curl -s http://localhost:9093/api/v2/alerts


Problem: Postgres exporter errors

Check credentials:
bash
# Test connection string
docker exec trading_postgres_exporter env | grep DATA_SOURCE_NAME

# Verify connection works
docker exec trading_timescaledb psql "postgresql://trading_user:trading_pass_change_in_production@localhost:5432/trading_db" -c "SELECT 1;"


Problem: Loki not showing logs

Check Promtail:
bash
# View Promtail logs
docker-compose logs promtail | tail -50

# Verify log files exist and are readable
ls -lah ./logs/


📝 Quick Configuration Changes

Change Alert Thresholds

Edit `grafana/provisioning/alerting/arbitrage_alerts.yml`:

yaml
# Example: Change low win rate threshold from 45% to 40%
- evaluator:
    params:
      - 0.40  # Was 0.45
    type: lt


Restart Grafana: `docker-compose restart grafana`

Add Custom Metrics

Edit `monitoring/postgres_exporter_queries.yaml`:

yaml
my_custom_metric:
  query: |
    SELECT
      symbol,
      COUNT(*) as my_count
    FROM arbitrage_opportunities
    WHERE timestamp > NOW() - INTERVAL '1 hour'
    GROUP BY symbol
  metrics:
    - symbol:
        usage: "LABEL"
    - my_count:
        usage: "GAUGE"


Restart postgres_exporter: `docker-compose restart postgres_exporter`

Adjust Log Retention

Edit `monitoring/loki-config.yaml`:

yaml
limits_config:
  retention_period: 1440h  # Change from 744h (31 days) to 1440h (60 days)


Restart Loki: `docker-compose restart loki`

🎯 What to Monitor First

Day 1-3: System Health
- Monitor "Arbitrage Monitoring" dashboard
- Watch for Critical alerts in Discord
- Verify win rate stays > 45%
- Check gas costs don't exceed 30% of profits

Week 1: Performance Tuning
- Review "Database Observability" dashboard
- Identify slow queries (> 100ms mean time)
- Check database cache hit ratio (aim for > 95%)
- Optimize indexes if needed

Week 2+: Strategy Optimization
- Analyze win rate by symbol (focus on high-win-rate pairs)
- Compare edge_bps vs profitability
- Review gas efficiency trends
- Adjust min_profit_threshold based on data

📚 Learn More

Full documentation: `GRAFANA_SETUP_COMPLETE.md`

Key files:
- Docker setup: `docker-compose.yml`
- Prometheus config: `monitoring/prometheus.yml`
- Loki config: `monitoring/loki-config.yaml`
- Custom DB metrics: `monitoring/postgres_exporter_queries.yaml`
- Alert rules: `grafana/provisioning/alerting/arbitrage_alerts.yml`
- Contact points: `grafana/provisioning/alerting/contact_points.yml`

🆘 Getting Help

Check logs:
bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f grafana
docker-compose logs -f prometheus
docker-compose logs -f postgres_exporter


Restart services:
bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart grafana


Full reset (if needed):
bash
# WARNING: This deletes all monitoring data!
docker-compose down -v
docker-compose up -d


---

Setup Time: ~5 minutes
Status: ✅ Production Ready
Last Updated: 2025-12-09
