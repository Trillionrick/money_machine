# Grafana Alerting Setup Guide for Money Machine

Complete guide to set up monitoring and alerting for your crypto arbitrage system using Grafana, Prometheus, and TimescaleDB.

## Architecture Overview

Your monitoring stack:

```
Arbitrage System → FastAPI Metrics → Prometheus → Grafana → Alerts
                 ↓
              TimescaleDB → Grafana Dashboards
```

**Components:**
- **FastAPI Application** (port 8080): Exposes `/api/ai/metrics/prometheus` endpoint
- **Prometheus** (port 9091): Scrapes and stores metrics
- **Grafana** (port 3000): Dashboards and alerting
- **TimescaleDB** (port 5433): Time-series data storage
- **AlertManager** (port 9093): Alert routing and deduplication

## Quick Start

### 1. Verify Environment Variables

Edit your `.env` file to include:

```bash
# Grafana Configuration
GRAFANA_PASSWORD=your_secure_password_here

# Discord Webhook for Alerts
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN

# Optional: Custom webhook for testing (use webhook.site)
GRAFANA_WEBHOOK_URL=https://webhook.site/your-unique-id

# Optional: Email alerts
ALERT_EMAIL_ADDRESSES=your-email@example.com
```

**Getting a Discord Webhook:**
1. Go to your Discord server settings
2. Navigate to Integrations → Webhooks
3. Click "New Webhook"
4. Copy the webhook URL
5. Add it to your `.env` file

**Getting a Test Webhook (Webhook.site):**
1. Visit https://webhook.site
2. Copy "Your unique URL"
3. Add it to your `.env` as `GRAFANA_WEBHOOK_URL`

### 2. Start the Monitoring Stack

```bash
# Start all services
docker compose up -d

# Verify all services are running
docker compose ps

# Check logs
docker compose logs -f grafana
docker compose logs -f prometheus
docker compose logs -f trading_app
```

**Expected services:**
- ✅ trading_app (healthy)
- ✅ timescaledb (healthy)
- ✅ redis (healthy)
- ✅ grafana (running)
- ✅ prometheus (running)
- ✅ alertmanager (running)

### 3. Access Grafana

1. **Open Grafana**: http://localhost:3000
2. **Login credentials:**
   - Username: `admin`
   - Password: (from your `.env` file, default: `admin`)
3. **First login:** You may be prompted to change the password

### 4. Verify Data Sources

Navigate to **Configuration → Data Sources**:

1. **TimescaleDB** should show as default datasource
   - Test the connection (should show green checkmark)

2. **Add Prometheus datasource**:
   - Click "Add data source"
   - Select "Prometheus"
   - URL: `http://prometheus:9090`
   - Access: Server (default)
   - Click "Save & Test" (should show green checkmark)

### 5. View Your Dashboard

Navigate to **Dashboards → Browse → Arbitrage Monitoring**

You should see panels showing:
- Opportunities (24h)
- Win Rate
- Total Profit
- Average Edge
- Opportunities over time
- Top trading symbols
- Recent opportunities table

**If you see "No Data"**: Your application needs to run for a few minutes to collect data.

### 6. Set Up Contact Points (Following Grafana Tutorial)

#### Option A: Using Discord (Recommended)

1. Navigate to **Alerting → Contact points**
2. Click **+ Add contact point**
3. **Name:** `Discord Alerts`
4. **Integration:** Choose "Discord"
5. **Webhook URL:** Paste your Discord webhook URL
6. **Title:** `Arbitrage Alert`
7. **Message:** Use this template:
   ```
   {{ .CommonLabels.alertname }}

   {{ range .Alerts }}
   Status: {{ .Status }}
   Severity: {{ .Labels.severity }}

   {{ .Annotations.description }}
   {{ end }}
   ```
8. Click **Test** → **Send test notification**
9. Check your Discord channel for the test message
10. Click **Save contact point**

#### Option B: Using Webhook.site (For Testing)

1. Go to https://webhook.site and copy your unique URL
2. In Grafana: **Alerting → Contact points**
3. Click **+ Add contact point**
4. **Name:** `Webhook Test`
5. **Integration:** Choose "Webhook"
6. **URL:** Paste your webhook.site URL
7. **HTTP Method:** POST
8. Click **Test** → **Send test notification**
9. Check webhook.site to see the alert payload
10. Click **Save contact point**

### 7. Create Alert Rules (Following Grafana Tutorial)

#### Example: Low Win Rate Alert

1. Navigate to **Alerting → Alert rules**
2. Click **+ Create alert rule**
3. **Alert rule name:** `Low Win Rate Alert`
4. **Define query and alert condition:**

   **Section 1 - Set a query:**
   - Data source: `TimescaleDB`
   - Query:
     ```sql
     SELECT
       CAST(COUNT(*) FILTER (WHERE profitable = TRUE) AS FLOAT) /
       NULLIF(COUNT(*) FILTER (WHERE executed = TRUE), 0) as value
     FROM arbitrage_opportunities
     WHERE timestamp > NOW() - INTERVAL '1 hour'
     AND executed = TRUE
     ```

   **Section 2 - Set alert condition:**
   - Expression: `WHEN last() OF A IS BELOW 0.45`
   - This triggers when win rate drops below 45%

5. **Set evaluation behavior:**
   - Folder: Create new → `Arbitrage Alerts`
   - Evaluation group: Create new → `Performance Monitoring`
   - Evaluation interval: `1m` (check every minute)
   - Pending period: `5m` (alert after 5 minutes below threshold)

6. **Configure labels:**
   - Add label: `severity` = `critical`
   - Add label: `component` = `arbitrage`

7. **Add annotation:**
   - Description: `Win rate has fallen to {{ $values.B.Value }} - system performance degraded`

8. **Configure notifications:**
   - Contact point: Select `Discord Alerts`

9. Click **Save rule and exit**

#### Additional Critical Alerts to Create

**Alert 2: Negative P&L**
- Query: Sum of (profit_quote - gas_cost_quote) for last hour
- Condition: IS BELOW 0
- Severity: Critical
- Pending: 15m

**Alert 3: High Gas Costs**
- Query: (SUM gas_cost / SUM profit) for last hour
- Condition: IS ABOVE 0.30 (30%)
- Severity: Warning
- Pending: 10m

**Alert 4: System Down**
- Query: Count of records in last 5 minutes
- Condition: IS BELOW 1
- Severity: Critical
- Pending: 5m

**Alert 5: High Value Opportunity** (Info Alert)
- Query: MAX profit_quote in last 5 minutes
- Condition: IS ABOVE 100
- Severity: Info
- Pending: 0s (immediate notification)

### 8. Test Your Alerts

#### Method 1: Using Pre-configured Alerts

The system includes pre-configured alert rules in:
- `grafana/provisioning/alerting/arbitrage_alerts.yml`

These will be automatically loaded when Grafana starts.

#### Method 2: Manual Testing

**Test alert endpoint:**
```bash
curl http://localhost:8080/api/ai/alerts/test
```

This sends a test alert through your Discord webhook.

**Check Prometheus metrics:**
```bash
curl http://localhost:8080/api/ai/metrics/prometheus

# You should see metrics like:
# arbitrage_win_rate 0.0
# arbitrage_net_profit_usd 0.0
# arbitrage_executions_total 0
```

**Verify Prometheus is scraping:**
1. Open http://localhost:9091
2. Go to Status → Targets
3. Look for `trading_app` and `ai_metrics` targets
4. Status should be "UP"

#### Method 3: Trigger Real Alerts

Run your arbitrage system:
```bash
# Start the AI-integrated arbitrage runner
docker compose exec trading_app python run_ai_integrated_arbitrage.py
```

As the system runs, it will:
- Detect arbitrage opportunities
- Execute trades
- Record metrics
- Trigger alerts when thresholds are crossed

### 9. View Alert Status

**In Grafana:**
1. Navigate to **Alerting → Alert rules**
2. See list of all configured alerts
3. Click on any alert to see:
   - Current state (Normal, Pending, Firing)
   - Query results
   - Alert history
   - Silences

**Alert States:**
- 🟢 **Normal**: Condition not met
- 🟡 **Pending**: Condition met but within pending period
- 🔴 **Firing**: Alert actively firing
- 🔵 **NoData**: No data received

### 10. Create a Notification Policy

1. Navigate to **Alerting → Notification policies**
2. Click **+ New nested policy**
3. **Match labels:** `severity = critical`
4. **Contact point:** Discord Alerts
5. **Override grouping:** Group by `alertname`
6. **Override timing:**
   - Group wait: `0s` (immediate)
   - Group interval: `1m`
   - Repeat interval: `5m`
7. Click **Save policy**

This ensures critical alerts are sent immediately with minimal grouping delay.

## Monitoring Your System

### Key Metrics to Watch

**Performance Metrics:**
- `arbitrage_win_rate`: Should stay above 0.45 (45%)
- `arbitrage_sharpe_ratio`: Higher is better (>1.0 is good)
- `arbitrage_avg_edge_bps`: Average profit edge in basis points

**Execution Metrics:**
- `arbitrage_success_rate`: Should stay above 0.70 (70%)
- `arbitrage_net_profit_usd`: Total profit minus gas costs
- `arbitrage_avg_execution_time_ms`: Latency matters in arbitrage

**Opportunity Metrics:**
- `arbitrage_conversion_rate`: Percentage of opportunities executed
- `arbitrage_opportunities_detected_total`: Detection pipeline health
- `arbitrage_avg_opportunity_quality`: Quality of detected opportunities

### Dashboard Customization

**Add a new panel:**
1. Open your dashboard
2. Click **Add panel** (top right)
3. Select **TimescaleDB** as data source
4. Write your SQL query
5. Choose visualization type
6. Click **Apply**

**Example queries:**

**Profit over time:**
```sql
SELECT
  time_bucket('1 hour', timestamp) AS time,
  SUM(profit_quote - gas_cost_quote) as net_profit
FROM arbitrage_opportunities
WHERE executed = TRUE
AND timestamp > NOW() - INTERVAL '24 hours'
GROUP BY time
ORDER BY time
```

**Top profitable pairs:**
```sql
SELECT
  symbol,
  COUNT(*) as trades,
  SUM(profit_quote) as total_profit
FROM arbitrage_opportunities
WHERE executed = TRUE
AND profitable = TRUE
AND timestamp > NOW() - INTERVAL '24 hours'
GROUP BY symbol
ORDER BY total_profit DESC
LIMIT 10
```

**Gas efficiency by chain:**
```sql
SELECT
  chain,
  AVG(gas_cost_quote / NULLIF(profit_quote, 0)) as gas_efficiency
FROM arbitrage_opportunities
WHERE executed = TRUE
AND profitable = TRUE
AND timestamp > NOW() - INTERVAL '24 hours'
GROUP BY chain
ORDER BY gas_efficiency ASC
```

## Advanced Configuration

### Prometheus Alert Rules

Create `monitoring/alerts/arbitrage_rules.yml`:

```yaml
groups:
  - name: arbitrage_prometheus_alerts
    interval: 30s
    rules:
      - alert: HighFailureRate
        expr: |
          (
            rate(arbitrage_executions_failed_total[5m]) /
            rate(arbitrage_executions_total[5m])
          ) > 0.3
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High execution failure rate"
          description: "More than 30% of executions are failing"

      - alert: NoOpportunitiesDetected
        expr: |
          rate(arbitrage_opportunities_detected_total[10m]) == 0
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "No opportunities detected"
          description: "No arbitrage opportunities found in 10 minutes"
```

Add to `monitoring/prometheus.yml`:
```yaml
rule_files:
  - "alerts/arbitrage_rules.yml"
```

### Multiple Alert Channels

**Slack Integration:**
1. Create a Slack incoming webhook
2. Add contact point in Grafana
3. Select "Slack" integration
4. Paste webhook URL
5. Customize message format

**Telegram Integration:**
1. Create a Telegram bot via @BotFather
2. Get bot token and chat ID
3. Add contact point in Grafana
4. Select "Telegram" integration
5. Configure bot token and chat ID

**PagerDuty Integration:**
1. Get PagerDuty integration key
2. Add contact point in Grafana
3. Select "PagerDuty" integration
4. Enter integration key
5. Set up routing rules for critical alerts

### Alert Silences

**Silence alerts during maintenance:**
1. Navigate to **Alerting → Silences**
2. Click **+ Add silence**
3. **Matchers:** Select labels to match
   - Example: `severity = warning`
4. **Duration:** Set maintenance window
5. **Comment:** Explain why alerts are silenced
6. Click **Create**

## Troubleshooting

### No Data in Dashboards

**Check TimescaleDB:**
```bash
# Connect to database
docker compose exec timescaledb psql -U trading_user -d trading_db

# Check if table exists
\dt arbitrage_opportunities

# Check row count
SELECT COUNT(*) FROM arbitrage_opportunities;

# Check recent records
SELECT * FROM arbitrage_opportunities ORDER BY timestamp DESC LIMIT 5;
```

**Check Application:**
```bash
# View application logs
docker compose logs -f trading_app

# Check if application is running
docker compose ps trading_app

# Restart if needed
docker compose restart trading_app
```

### Prometheus Not Scraping

**Check Prometheus targets:**
1. Open http://localhost:9091/targets
2. Look for errors on targets
3. Check if endpoints are reachable

**Test metrics endpoint:**
```bash
# From host
curl http://localhost:8080/api/ai/metrics/prometheus

# From within Docker network
docker compose exec prometheus wget -qO- http://trading_app:8080/api/ai/metrics/prometheus
```

**Check Prometheus config:**
```bash
# View Prometheus logs
docker compose logs prometheus

# Restart Prometheus
docker compose restart prometheus
```

### Alerts Not Firing

**Check alert rule state:**
1. Go to **Alerting → Alert rules**
2. Click on the alert
3. View **Query** tab to see current values
4. Check **State** tab for evaluation history

**Check notification policies:**
1. Go to **Alerting → Notification policies**
2. Verify your alert labels match a policy route
3. Check if alerts are being silenced

**Test contact point:**
1. Go to **Alerting → Contact points**
2. Click on your contact point
3. Click **Test** → **Send test notification**
4. Verify you receive the notification

### Discord Webhook Not Working

**Verify webhook URL:**
```bash
# Test webhook manually
curl -X POST https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_TOKEN \
  -H "Content-Type: application/json" \
  -d '{"content": "Test message from curl"}'
```

**Check Grafana logs:**
```bash
docker compose logs grafana | grep -i webhook
```

**Verify webhook URL in Grafana:**
1. Alerting → Contact points
2. Click on Discord contact point
3. Verify webhook URL is correct (no extra spaces)
4. Click Test and check Discord

## Best Practices

### Alert Fatigue Prevention

1. **Set appropriate thresholds**: Don't alert on every minor fluctuation
2. **Use pending periods**: Give time for transient issues to resolve
3. **Group related alerts**: Prevent duplicate notifications
4. **Set repeat intervals**: Don't spam the same alert constantly
5. **Use severity levels**: Critical → immediate, Warning → delayed, Info → optional

### Performance Optimization

**Dashboard refresh rates:**
- Real-time monitoring: 5-10 seconds
- Historical analysis: 30-60 seconds
- Long-term trends: 5 minutes

**Prometheus retention:**
```yaml
# In docker-compose.yml, add to prometheus command:
- '--storage.tsdb.retention.time=30d'
- '--storage.tsdb.retention.size=10GB'
```

**TimescaleDB compression:**
```sql
-- Enable compression on arbitrage_opportunities
SELECT add_compression_policy('arbitrage_opportunities', INTERVAL '7 days');
```

### Security Considerations

1. **Change default passwords:**
   ```bash
   # Update .env with strong passwords
   GRAFANA_PASSWORD=your_strong_password_here
   ```

2. **Restrict Grafana access:**
   - Use reverse proxy with authentication
   - Enable HTTPS
   - Configure firewall rules

3. **Secure webhooks:**
   - Use HTTPS endpoints only
   - Rotate webhook URLs periodically
   - Monitor webhook logs for unauthorized access

4. **Database security:**
   - Change default TimescaleDB password
   - Limit network access
   - Enable SSL connections

## Next Steps

1. **Customize dashboards** for your specific trading pairs
2. **Add more alert rules** based on your risk tolerance
3. **Set up alerting escalation** for critical issues
4. **Create custom metrics** for advanced strategies
5. **Integrate with your trading journal** for comprehensive analysis
6. **Set up automated backtesting** alerts
7. **Monitor ML model performance** with dedicated dashboards

## Resources

- **Grafana Documentation**: https://grafana.com/docs/
- **Prometheus Documentation**: https://prometheus.io/docs/
- **TimescaleDB Documentation**: https://docs.timescale.com/
- **Discord Webhooks**: https://discord.com/developers/docs/resources/webhook
- **Webhook.site**: https://webhook.site (for testing)

## Support

For issues specific to this setup:
1. Check logs: `docker compose logs -f`
2. Verify services: `docker compose ps`
3. Test endpoints manually with curl
4. Review Grafana alert rule query results
5. Check Discord webhook with direct curl test

Your arbitrage system is now fully monitored with real-time alerting! 🚀
