# Grafana Alerting Quick Reference Card

## 🚀 Quick Start (5 Minutes)

```bash
# 1. Set up Discord webhook in .env
echo "DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN" >> .env

# 2. Start all services
docker compose up -d

# 3. Verify setup
python test_grafana_metrics.py

# 4. Access Grafana
open http://localhost:3000
# Login: admin / (check .env for password)
```

## 📊 Key URLs

| Service | URL | Purpose |
|---------|-----|---------|
| Grafana | http://localhost:3000 | Dashboards & Alerts |
| Prometheus | http://localhost:9091 | Metrics Database |
| Application | http://localhost:8080 | Trading Bot |
| Metrics Endpoint | http://localhost:8080/api/ai/metrics/prometheus | Raw Metrics |
| AlertManager | http://localhost:9093 | Alert Routing |

## 🎯 Alert Rule Templates

### Critical: Low Win Rate
```sql
-- Query
SELECT
  CAST(COUNT(*) FILTER (WHERE profitable = TRUE) AS FLOAT) /
  NULLIF(COUNT(*) FILTER (WHERE executed = TRUE), 0) as value
FROM arbitrage_opportunities
WHERE timestamp > NOW() - INTERVAL '1 hour'
AND executed = TRUE

-- Condition: IS BELOW 0.45
-- Pending: 5m
-- Severity: critical
```

### Critical: Negative P&L
```sql
-- Query
SELECT
  COALESCE(SUM(profit_quote) - SUM(gas_cost_quote), 0) as value
FROM arbitrage_opportunities
WHERE timestamp > NOW() - INTERVAL '1 hour'
AND executed = TRUE

-- Condition: IS BELOW 0
-- Pending: 15m
-- Severity: critical
```

### Warning: High Gas Costs
```sql
-- Query
SELECT
  CAST(SUM(gas_cost_quote) AS FLOAT) /
  NULLIF(SUM(profit_quote), 0) as value
FROM arbitrage_opportunities
WHERE timestamp > NOW() - INTERVAL '1 hour'
AND executed = TRUE
AND profitable = TRUE

-- Condition: IS ABOVE 0.30
-- Pending: 10m
-- Severity: warning
```

### Info: High Value Opportunity
```sql
-- Query
SELECT MAX(profit_quote) as value
FROM arbitrage_opportunities
WHERE timestamp > NOW() - INTERVAL '5 minutes'
AND edge_bps > 100

-- Condition: IS ABOVE 100
-- Pending: 0s
-- Severity: info
```

## 🔔 Discord Message Template

```
{{ .CommonLabels.alertname }}

{{ range .Alerts }}
**Status:** {{ .Status }}
**Severity:** {{ .Labels.severity }}
**Component:** {{ .Labels.component }}

{{ .Annotations.description }}

{{ end }}
```

## 🛠️ Common Commands

### Check Service Status
```bash
docker compose ps
docker compose logs -f grafana
docker compose logs -f prometheus
docker compose logs -f trading_app
```

### Test Endpoints
```bash
# Test application health
curl http://localhost:8080/api/ai/health

# View Prometheus metrics
curl http://localhost:8080/api/ai/metrics/prometheus

# Test Discord webhook
curl http://localhost:8080/api/ai/alerts/test

# Check Prometheus targets
curl http://localhost:9091/api/v1/targets
```

### Database Queries
```bash
# Connect to TimescaleDB
docker compose exec timescaledb psql -U trading_user -d trading_db

# Count opportunities
SELECT COUNT(*) FROM arbitrage_opportunities;

# Check recent activity
SELECT COUNT(*) FROM arbitrage_opportunities
WHERE timestamp > NOW() - INTERVAL '1 hour';

# View recent opportunities
SELECT timestamp, symbol, edge_bps, profit_quote, executed
FROM arbitrage_opportunities
ORDER BY timestamp DESC
LIMIT 10;
```

### Restart Services
```bash
# Restart specific service
docker compose restart grafana
docker compose restart prometheus
docker compose restart trading_app

# Restart all
docker compose restart

# Full rebuild
docker compose down
docker compose up -d --build
```

## 📈 Key Metrics

| Metric | Good Value | Alert Threshold |
|--------|------------|-----------------|
| Win Rate | > 55% | < 45% |
| Success Rate | > 80% | < 70% |
| Gas Cost % | < 20% | > 30% |
| Net Profit | Positive | Negative |
| Sharpe Ratio | > 1.0 | < 0.5 |

## 🔍 Troubleshooting

### No Data in Dashboard
1. Check if application is running: `docker compose ps trading_app`
2. View application logs: `docker compose logs -f trading_app`
3. Verify database has data: `docker compose exec timescaledb psql -U trading_user -d trading_db -c "SELECT COUNT(*) FROM arbitrage_opportunities;"`

### Alerts Not Firing
1. Check alert rule state in Grafana UI
2. Verify query returns data
3. Check notification policies match alert labels
4. Test contact point manually

### Prometheus Not Scraping
1. Check targets: http://localhost:9091/targets
2. Verify metrics endpoint: `curl http://localhost:8080/api/ai/metrics/prometheus`
3. Review Prometheus logs: `docker compose logs prometheus`

### Discord Webhook Failed
1. Test webhook directly:
   ```bash
   curl -X POST YOUR_WEBHOOK_URL \
     -H "Content-Type: application/json" \
     -d '{"content": "Test"}'
   ```
2. Verify URL has no extra spaces
3. Check Grafana contact point configuration

## 📁 Important Files

```
money_machine/
├── grafana/
│   ├── provisioning/
│   │   ├── alerting/
│   │   │   ├── arbitrage_alerts.yml      # Pre-configured alert rules
│   │   │   └── contact_points.yml         # Contact point configs
│   │   ├── dashboards/
│   │   │   └── dashboards.yml             # Dashboard provisioning
│   │   └── datasources/
│   │       └── timescaledb.yml            # TimescaleDB datasource
│   └── dashboards/
│       └── arbitrage_monitoring.json      # Main dashboard
├── monitoring/
│   ├── prometheus.yml                     # Prometheus config
│   └── alertmanager.yml                   # AlertManager config
├── test_grafana_metrics.py                # Setup verification script
└── GRAFANA_ALERTING_SETUP.md             # Full setup guide
```

## 🎨 Severity Levels

| Level | Color | Use Case | Response Time |
|-------|-------|----------|---------------|
| 🔴 Critical | Red | System down, major losses | Immediate |
| 🟡 Warning | Yellow | Performance degraded | < 1 hour |
| 🔵 Info | Blue | FYI, opportunities | When convenient |

## 💡 Pro Tips

1. **Start with pre-configured alerts**: They're in `grafana/provisioning/alerting/arbitrage_alerts.yml`
2. **Use Webhook.site for testing**: https://webhook.site - great for debugging alert payloads
3. **Set pending periods**: Prevent alerts from flapping on temporary issues
4. **Group related alerts**: Reduce notification spam
5. **Test before production**: Use `test_grafana_metrics.py` to verify everything works

## 🆘 Emergency Actions

### System is Losing Money
```bash
# Stop trading immediately
docker compose stop trading_app

# Check what happened
docker compose logs trading_app | grep -i error

# Review recent trades
docker compose exec timescaledb psql -U trading_user -d trading_db \
  -c "SELECT * FROM arbitrage_opportunities WHERE executed = TRUE ORDER BY timestamp DESC LIMIT 20;"
```

### Too Many Failed Executions
```bash
# Check gas prices
curl http://localhost:8080/api/ai/health | jq .

# Review execution errors
docker compose logs trading_app | grep -i "execution failed"

# Temporarily disable AI system
curl -X POST http://localhost:8080/api/ai/disable
```

### Database Full
```bash
# Check database size
docker compose exec timescaledb psql -U trading_user -d trading_db \
  -c "SELECT pg_size_pretty(pg_database_size('trading_db'));"

# Enable compression (if not already enabled)
docker compose exec timescaledb psql -U trading_user -d trading_db \
  -c "SELECT add_compression_policy('arbitrage_opportunities', INTERVAL '7 days');"
```

## 📚 Additional Resources

- **Full Setup Guide**: `GRAFANA_ALERTING_SETUP.md`
- **Grafana Tutorial**: https://grafana.com/tutorials/alerting-get-started/
- **Prometheus Docs**: https://prometheus.io/docs/
- **TimescaleDB Docs**: https://docs.timescale.com/

---

**Need help?** Run `python test_grafana_metrics.py` to diagnose issues.
