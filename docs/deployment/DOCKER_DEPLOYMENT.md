# 🐳 Docker Compose Deployment Guide

Complete guide for deploying the AI Trading System using Docker Compose with production-grade infrastructure.

---

## 🎯 What's Included

Your `docker-compose.yml` now includes:

### Core Services:
- ✅ **Trading App** - AI-powered flash loan arbitrage system
- ✅ **TimescaleDB** - High-performance time-series database
- ✅ **Redis** - Caching and pub/sub messaging
- ✅ **MLflow** - ML model tracking and versioning

### Monitoring & Alerting:
- ✅ **Grafana** - Visual dashboards and monitoring
- ✅ **Prometheus** - Metrics collection and storage
- ✅ **AlertManager** - Alert routing and notification

### Production Features:
- ✅ Production safety limits built-in
- ✅ Discord webhook alerts configured
- ✅ Health checks for all services
- ✅ Resource limits for stability
- ✅ Automatic restarts on failure
- ✅ Data persistence with volumes

---

## 🚀 Quick Start

### 1. Prerequisites

```bash
# Docker & Docker Compose installed
docker --version  # Should be 20.10+
docker compose version  # Should be 2.0+
```

### 2. Deploy Everything

```bash
cd /mnt/c/Users/catty/Desktop/money_machine

# Start all services
docker compose up -d

# View logs
docker compose logs -f trading_app
```

### 3. Verify Deployment

```bash
# Check all services are running
docker compose ps

# Should show 7 services running:
# ✅ trading_app
# ✅ timescaledb
# ✅ redis
# ✅ mlflow
# ✅ grafana
# ✅ prometheus
# ✅ alertmanager
```

### 4. Access Services

| Service | URL | Purpose |
|---------|-----|---------|
| **Trading API** | http://localhost:8080/docs | Interactive API docs |
| **Grafana** | http://localhost:3000 | Monitoring dashboards |
| **Prometheus** | http://localhost:9091 | Metrics explorer |
| **MLflow** | http://localhost:5000 | ML model tracking |
| **AlertManager** | http://localhost:9093 | Alert management |

**Grafana Login:**
- Username: `admin`
- Password: `admin` (change on first login)

---

## 📊 Service Architecture

```
┌─────────────────────────────────────────────────────┐
│              Client / User / Discord                 │
└───────────────────┬─────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────┐
│           Trading App (Port 8080)                    │
│  ┌──────────────────────────────────────────────┐  │
│  │ • Production Safety Layer                     │  │
│  │ • Transaction Logger                          │  │
│  │ • Alert System                                │  │
│  │ • AI Decision Engine                          │  │
│  │ • Flash Loan Executor                         │  │
│  └──────────────────────────────────────────────┘  │
└─────┬──────────┬──────────┬──────────┬─────────────┘
      │          │          │          │
      ▼          ▼          ▼          ▼
┌──────────┐ ┌────────┐ ┌─────────┐ ┌──────────┐
│TimescaleDB│ │ Redis  │ │ MLflow  │ │Prometheus│
│  (5433)   │ │ (6379) │ │ (5000)  │ │  (9091)  │
└──────────┘ └────────┘ └─────────┘ └──────────┘
      │                                     │
      │                                     ▼
      │                              ┌─────────────┐
      │                              │ Grafana     │
      │                              │ (3000)      │
      └─────────────────────────────►│ Dashboards  │
                                     └─────────────┘
```

---

## 🛡️ Production Safety Configuration

All safety limits are pre-configured in `docker-compose.yml`:

### Position Limits:
```yaml
MAX_POSITION_SIZE_ETH=2.0      # Max 2 ETH per trade
MAX_LOSS_PER_TRADE_ETH=0.1     # Max 0.1 ETH loss per trade
```

### Loss Limits:
```yaml
MAX_HOURLY_LOSS_ETH=0.3        # Stop at -0.3 ETH hourly
MAX_DAILY_LOSS_ETH=1.0         # Stop at -1.0 ETH daily
MAX_TOTAL_DRAWDOWN_ETH=5.0     # Emergency stop at -5.0 ETH
```

### Execution Limits:
```yaml
MAX_GAS_PRICE_GWEI=300         # Skip trades if gas > 300 gwei
MAX_TRADES_PER_HOUR=10         # Rate limit: 10 trades/hour
MAX_TRADES_PER_DAY=50          # Rate limit: 50 trades/day
MIN_PROFIT_AFTER_GAS_ETH=0.01  # Only execute if profit > 0.01 ETH
```

---

## 📱 Alerts & Notifications

### Discord Integration:

Your Discord webhook is already configured! You'll receive notifications for:

- 💰 **Profitable trades** - Instant notification with profit amount
- ❌ **Losing trades** - Alert with loss details
- ⚠️ **Circuit breakers** - Warning when safety limits trigger
- 🚨 **Emergency shutdown** - Critical alert for system halt
- 📊 **Daily summary** - End-of-day performance report

### Test Discord Alerts:

```bash
docker compose exec trading_app python -c "
from src.ai.alert_system import AlertSystem
alert = AlertSystem()
alert.send_test_alert()
"
```

---

## 📈 Monitoring & Dashboards

### Grafana Dashboards:

After logging into Grafana (http://localhost:3000):

1. **Trading Performance Dashboard**
   - Real-time P&L
   - Win rate trends
   - Trade execution timeline

2. **AI Decision Dashboard**
   - AI confidence distribution
   - Decision execution rate
   - Model performance metrics

3. **System Health Dashboard**
   - Circuit breaker status
   - API latency
   - Database performance

### Prometheus Metrics:

Access metrics at http://localhost:9091 to query:

```promql
# Total trades today
sum(increase(trades_total[24h]))

# Current win rate
rate(winning_trades[1h]) / rate(total_trades[1h])

# Average profit per trade
avg(profit_eth)
```

---

## 🔧 Common Operations

### View Logs:

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f trading_app
docker compose logs -f timescaledb

# Last 100 lines
docker compose logs --tail=100 trading_app
```

### Restart Services:

```bash
# Restart everything
docker compose restart

# Restart specific service
docker compose restart trading_app
```

### Stop Trading:

```bash
# Stop trading (keeps databases running)
docker compose stop trading_app

# Stop everything
docker compose down

# Stop and remove volumes (⚠️ deletes all data)
docker compose down -v
```

### Update Configuration:

```bash
# Edit .env file
nano .env

# Restart to apply changes
docker compose restart trading_app
```

### Database Access:

```bash
# Connect to TimescaleDB
docker compose exec timescaledb psql -U trading_user -d trading_db

# Run queries
SELECT * FROM trade_executions ORDER BY timestamp DESC LIMIT 10;
SELECT * FROM daily_performance;
SELECT * FROM active_circuit_breakers;

# Exit
\q
```

### Redis Access:

```bash
# Connect to Redis
docker compose exec redis redis-cli

# Check cached data
KEYS *
GET some_key

# Exit
exit
```

---

## 🔍 Health Checks

### Check Service Health:

```bash
# Trading app health
curl http://localhost:8080/api/ai/health | jq .

# Database health
docker compose exec timescaledb pg_isready

# Redis health
docker compose exec redis redis-cli ping
```

### Check Trading Status:

```bash
# AI system status
curl http://localhost:8080/api/ai/status | jq .

# Recent trades
curl http://localhost:8080/api/ai/decisions/latest | jq .

# Performance metrics
curl http://localhost:8080/api/ai/metrics | jq .summary
```

---

## 🚨 Emergency Procedures

### Immediate Stop Trading:

```bash
# Disable AI (keeps services running)
curl -X POST http://localhost:8080/api/ai/disable

# Or stop the container
docker compose stop trading_app
```

### View Circuit Breaker Status:

```bash
# Check active circuit breakers
docker compose exec timescaledb psql -U trading_user -d trading_db -c "
SELECT * FROM active_circuit_breakers;
"
```

### Export Trade History:

```bash
# Export last 100 trades to CSV
docker compose exec timescaledb psql -U trading_user -d trading_db -c "
COPY (SELECT * FROM trade_executions ORDER BY timestamp DESC LIMIT 100)
TO '/tmp/trades.csv' CSV HEADER;
"

# Copy from container to host
docker cp trading_timescaledb:/tmp/trades.csv ./trades_backup.csv
```

---

## 📦 Data Backup

### Backup Database:

```bash
# Create backup
docker compose exec timescaledb pg_dump -U trading_user trading_db > backup_$(date +%Y%m%d).sql

# Restore from backup
docker compose exec -T timescaledb psql -U trading_user trading_db < backup_20250106.sql
```

### Backup Volumes:

```bash
# Backup all volumes
docker run --rm -v money_machine_timescaledb_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/db_backup_$(date +%Y%m%d).tar.gz -C /data .

# Restore volume
docker run --rm -v money_machine_timescaledb_data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/db_backup_20250106.tar.gz -C /data
```

---

## 🎯 Performance Tuning

### Resource Limits:

Current limits (can be adjusted in `docker-compose.yml`):

| Service | CPUs | Memory |
|---------|------|--------|
| Trading App | 2-4 cores | 4-8 GB |
| TimescaleDB | 1-2 cores | 2-4 GB |
| Redis | 0.5-1 core | 1-2 GB |
| Prometheus | 1 core | 2 GB |
| Grafana | 1 core | 1 GB |

### Database Optimization:

```sql
-- Connect to database
docker compose exec timescaledb psql -U trading_user -d trading_db

-- Check table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Vacuum and analyze
VACUUM ANALYZE;
```

---

## 🐛 Troubleshooting

### Container Won't Start:

```bash
# Check logs
docker compose logs trading_app

# Check configuration
docker compose config

# Rebuild container
docker compose build --no-cache trading_app
docker compose up -d trading_app
```

### Database Connection Issues:

```bash
# Check if database is ready
docker compose exec timescaledb pg_isready -U trading_user

# Check connections
docker compose exec timescaledb psql -U trading_user -d trading_db -c "
SELECT count(*) FROM pg_stat_activity WHERE datname = 'trading_db';
"
```

### High Memory Usage:

```bash
# Check resource usage
docker stats

# Restart services
docker compose restart
```

---

## 🔐 Security Best Practices

### Change Default Passwords:

1. Edit `docker-compose.yml`:
   ```yaml
   POSTGRES_PASSWORD: YOUR_SECURE_PASSWORD_HERE
   ```

2. Update connection strings with new password

3. Restart services:
   ```bash
   docker compose down
   docker compose up -d
   ```

### Secure Grafana:

```bash
# Change admin password (first login)
# Navigate to http://localhost:3000
# Default: admin/admin
# Set strong password when prompted
```

### Protect Private Keys:

```bash
# Ensure .env has restricted permissions
chmod 600 .env

# Never commit .env to git
echo ".env" >> .gitignore
```

---

## 📝 Maintenance Schedule

### Daily:
- ✅ Check dashboard for anomalies
- ✅ Review Discord alerts
- ✅ Verify all services running: `docker compose ps`

### Weekly:
- ✅ Review win rate and performance
- ✅ Check database size
- ✅ Backup trade history
- ✅ Update ML models if needed

### Monthly:
- ✅ Full database backup
- ✅ Review and adjust safety limits
- ✅ Analyze performance trends
- ✅ Update Docker images: `docker compose pull`

---

## 🚀 Scaling & Optimization

### Horizontal Scaling:

```yaml
# Scale trading app to multiple instances
docker compose up -d --scale trading_app=3
```

### Load Balancing:

Add NGINX as reverse proxy:

```yaml
services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - trading_app
```

---

## 📞 Support & Resources

- **API Documentation**: http://localhost:8080/docs
- **Production Guide**: `PRODUCTION_DEPLOYMENT_GUIDE.md`
- **Quick Reference**: `QUICK_REFERENCE.md`

---

## ✅ Deployment Checklist

Before going live:

- [ ] All environment variables set in `.env`
- [ ] Discord webhook tested and working
- [ ] Database initialized successfully
- [ ] All services healthy: `docker compose ps`
- [ ] Safety limits configured appropriately
- [ ] Monitoring dashboards accessible
- [ ] Backup strategy in place
- [ ] Emergency procedures understood

---

**Your Docker Compose setup is production-ready! 🎉**

Start trading:
```bash
docker compose up -d
```

Monitor:
```bash
./scripts/live_monitor.sh
```

Good luck! 🚀💰
