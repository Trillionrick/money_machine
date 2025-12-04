# Forex Data Collection Guide

Complete guide for collecting real-time and historical forex price data from OANDA.

---

## 🎯 **What Gets Collected**

### **Real-Time Data** (Streaming)
- ✅ **Tick Prices** - Bid/Ask updates every ~250ms
- ✅ **10 Major Pairs**: EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, USD/CHF, NZD/USD, EUR/GBP, EUR/JPY, GBP/JPY
- ✅ **Spreads** - Calculated automatically
- ✅ **Liquidity** - Bid/Ask depth when available

### **Historical Data** (Periodic Fetch)
- ✅ **1-Hour Candles** - Last 50 hours for all pairs (every 15 min)
- ✅ **5-Minute Candles** - Last 100 candles for top 3 pairs (every 15 min)
- ✅ **OHLCV + Bid/Ask** - Complete price data

### **Storage**
- ✅ **TimescaleDB** - Optimized time-series database
- ✅ **Automatic Compression** - Tick data compressed after 1 day, candles after 7 days
- ✅ **Continuous Aggregates** - Auto-downsampling to 1h and 1d candles

---

## 🚀 **Quick Start**

### **Prerequisites**

1. ✅ TimescaleDB running
2. ✅ OANDA credentials in `.env`
3. ✅ Database schema initialized

```bash
# Check prerequisites
docker ps | grep timescaledb  # Should show running container
grep OANDA_API_TOKEN .env     # Should show your token
python scripts/verify_db_setup.py  # Should pass all checks
```

### **Start Data Collection**

```bash
# From project root
cd /mnt/c/Users/catty/Desktop/money_machine

# Start collector (runs in background)
bash scripts/start_data_collection.sh

# Output:
# ✅ Data collector started!
#    PID: 12345
#    Log: logs/forex_collector_20250126_120000.log
```

### **Monitor Collection**

```bash
# View real-time stats
bash scripts/monitor_collection.sh

# View live logs
tail -f logs/forex_collector_*.log

# Check latest prices
docker exec trading_timescaledb psql -U trading_user -d trading_db -c "
  SELECT time, instrument, bid, ask, spread
  FROM oanda_pricing
  ORDER BY time DESC
  LIMIT 10;
"
```

### **Stop Collection**

```bash
# Graceful shutdown
bash scripts/stop_data_collection.sh
```

---

## 📊 **Monitoring Dashboard**

### **Real-Time Statistics**

The collector prints statistics every minute:

```
collector_statistics uptime_minutes=15 prices_received=3420 prices_stored=3420
  candles_stored=150 errors=0 prices_per_minute=228.0
  last_price=2025-01-26T12:15:30.123456+00:00
```

### **Key Metrics**

- **prices_per_minute**: Should be ~200-300 for 10 instruments
- **errors**: Should be 0 or very low
- **last_price**: Should be within last few seconds

### **Database Queries**

```sql
-- Total tick data
SELECT COUNT(*) FROM oanda_pricing;

-- Data by instrument
SELECT instrument, COUNT(*) as tick_count
FROM oanda_pricing
GROUP BY instrument
ORDER BY tick_count DESC;

-- Latest prices per instrument
SELECT DISTINCT ON (instrument)
    instrument,
    time,
    bid,
    ask,
    spread
FROM oanda_pricing
ORDER BY instrument, time DESC;

-- Hourly volume
SELECT
    time_bucket('1 hour', time) as hour,
    COUNT(*) as tick_count
FROM oanda_pricing
WHERE time >= NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour DESC;

-- Database growth rate
SELECT
    pg_size_pretty(pg_database_size('trading_db')) as current_size,
    pg_size_pretty(pg_database_size('trading_db') / EXTRACT(epoch FROM (NOW() - (
        SELECT MIN(created_at) FROM oanda_pricing
    ))) * 86400) as daily_growth_estimate;
```

---

## 🔧 **Configuration**

### **Customize Instruments**

Edit `src/data_collection/forex_collector.py`:

```python
# Around line 35
self.instruments = [
    "EUR_USD",
    "GBP_USD",
    "USD_JPY",
    # Add more pairs:
    "EUR_CHF",
    "AUD_NZD",
    "XAU_USD",  # Gold
]
```

### **Adjust Fetch Frequency**

Edit `src/data_collection/forex_collector.py`:

```python
# In periodic_candle_fetch() method
await asyncio.sleep(900)  # Change 900 to desired seconds
```

### **Change Database Connection**

Edit both:
- `src/data_collection/forex_collector.py` (line ~60)
- `scripts/start_data_collection.sh`

```python
self.db_pool = await asyncpg.create_pool(
    host="localhost",
    port=5433,  # Change if needed
    user="trading_user",
    password="your_password",  # Update
    database="trading_db",
)
```

---

## 🐧 **Run as System Service** (Linux/WSL2)

### **Install as systemd Service**

```bash
# 1. Edit service file with your username
sed -i 's/youruser/YOUR_USERNAME/' scripts/forex-collector.service

# 2. Copy to systemd directory
sudo cp scripts/forex-collector.service /etc/systemd/system/

# 3. Reload systemd
sudo systemctl daemon-reload

# 4. Enable auto-start on boot
sudo systemctl enable forex-collector

# 5. Start service
sudo systemctl start forex-collector

# 6. Check status
sudo systemctl status forex-collector
```

### **Manage Service**

```bash
# Start
sudo systemctl start forex-collector

# Stop
sudo systemctl stop forex-collector

# Restart
sudo systemctl restart forex-collector

# View logs
journalctl -u forex-collector -f

# Disable auto-start
sudo systemctl disable forex-collector
```

---

## 📈 **Data Analysis Examples**

### **Calculate Average Spreads**

```sql
SELECT
    instrument,
    AVG(spread) as avg_spread,
    MIN(spread) as min_spread,
    MAX(spread) as max_spread,
    STDDEV(spread) as spread_volatility
FROM oanda_pricing
WHERE time >= NOW() - INTERVAL '1 hour'
GROUP BY instrument
ORDER BY avg_spread DESC;
```

### **Identify Trading Hours**

```sql
SELECT
    EXTRACT(HOUR FROM time) as hour,
    COUNT(*) as tick_count,
    AVG(spread) as avg_spread
FROM oanda_pricing
WHERE instrument = 'EUR_USD'
  AND time >= NOW() - INTERVAL '7 days'
GROUP BY hour
ORDER BY hour;
```

### **Detect Price Gaps**

```sql
WITH price_lags AS (
    SELECT
        time,
        instrument,
        bid,
        LAG(bid) OVER (PARTITION BY instrument ORDER BY time) as prev_bid,
        LAG(time) OVER (PARTITION BY instrument ORDER BY time) as prev_time
    FROM oanda_pricing
    WHERE time >= NOW() - INTERVAL '1 day'
)
SELECT
    instrument,
    time,
    prev_time,
    EXTRACT(EPOCH FROM (time - prev_time)) as gap_seconds,
    ABS(bid - prev_bid) as price_change
FROM price_lags
WHERE EXTRACT(EPOCH FROM (time - prev_time)) > 60  -- Gaps > 1 minute
ORDER BY gap_seconds DESC
LIMIT 10;
```

### **Export to CSV**

```bash
# Export last 24 hours of EUR/USD ticks
docker exec trading_timescaledb psql -U trading_user -d trading_db -c "
  COPY (
    SELECT time, bid, ask, spread
    FROM oanda_pricing
    WHERE instrument = 'EUR_USD'
      AND time >= NOW() - INTERVAL '24 hours'
    ORDER BY time
  ) TO STDOUT WITH CSV HEADER
" > eur_usd_ticks.csv

# Export hourly candles
docker exec trading_timescaledb psql -U trading_user -d trading_db -c "
  COPY (
    SELECT time, instrument, open, high, low, close, volume
    FROM oanda_candles
    WHERE granularity = 'H1'
      AND time >= NOW() - INTERVAL '30 days'
    ORDER BY instrument, time
  ) TO STDOUT WITH CSV HEADER
" > forex_candles_30d.csv
```

---

## 🚨 **Troubleshooting**

### **Collector Won't Start**

**Problem**: Error when starting collector

**Check**:
```bash
# 1. Is TimescaleDB running?
docker ps | grep timescaledb

# 2. Can connect to database?
docker exec trading_timescaledb pg_isready -U trading_user

# 3. Are OANDA credentials valid?
python -c "
from src.brokers.oanda_config import OandaConfig
config = OandaConfig.from_env()
print(f'Token: {config.oanda_token.get_secret_value()[:10]}...')
print(f'Account: {config.oanda_account_id}')
"

# 4. Check logs
tail -50 logs/forex_collector_*.log
```

---

### **No Data Being Collected**

**Problem**: Collector running but no data in database

**Check**:
```bash
# 1. Check collector logs for errors
tail -100 logs/forex_collector_*.log | grep -i error

# 2. Verify OANDA connection
python -c "
import asyncio
from src.brokers.oanda_config import OandaConfig
from src.brokers.oanda_adapter import OandaAdapter

async def test():
    config = OandaConfig.from_env()
    async with OandaAdapter(config) as adapter:
        account = await adapter.get_account()
        print(f'Connected! Balance: {account[\"balance\"]}')

asyncio.run(test())
"

# 3. Check if prices are being received
grep "prices_received" logs/forex_collector_*.log | tail -5
```

---

### **High Error Rate**

**Problem**: Many errors in collector statistics

**Solutions**:

1. **Network Issues**
   ```bash
   # Check internet connection
   ping api-fxpractice.oanda.com
   ```

2. **Rate Limiting**
   - OANDA may be rate limiting your requests
   - Reduce fetch frequency in `periodic_candle_fetch()`

3. **Database Connection Pool Exhausted**
   ```python
   # In forex_collector.py, increase pool size
   self.db_pool = await asyncpg.create_pool(
       ...,
       min_size=5,  # Increase from 2
       max_size=20,  # Increase from 10
   )
   ```

---

### **Collector Crashes**

**Problem**: Collector stops unexpectedly

**Check**:
```bash
# View error logs
tail -100 logs/forex_collector_*.log

# Check system resources
free -h  # Memory
df -h    # Disk space

# Check if Docker container restarted
docker logs trading_timescaledb | tail -50
```

**Solution**: Use systemd service for automatic restart

---

### **Weekend Data Gaps**

**Problem**: No data during weekends

**This is normal!** Forex markets close:
- **Close**: Friday 17:00 ET (22:00 UTC)
- **Open**: Sunday 17:00 ET (22:00 UTC)

The collector will automatically reconnect when markets reopen.

---

## 📊 **Performance Benchmarks**

Expected performance on typical hardware:

| Metric | Expected Value |
|--------|----------------|
| Tick rate | 200-300 ticks/min (10 instruments) |
| Database writes | 3-5 ticks/sec |
| Memory usage | 50-100 MB |
| CPU usage | 1-5% |
| Storage growth | ~100 MB/day (before compression) |
| Storage (compressed) | ~10 MB/day (90% compression) |

---

## 🎯 **Next Steps**

Once data is collecting:

1. ✅ **Wait 1 hour** - Let data accumulate
2. ✅ **Run Analytics** - Test SQL queries above
3. ✅ **Build Dashboards** - Use Grafana (included in docker-compose)
4. ✅ **Backtest Strategies** - Use historical candle data
5. ✅ **Live Trading** - Connect strategies to real-time stream

---

## 📚 **Resources**

- **Collector Code**: `src/data_collection/forex_collector.py`
- **Start Script**: `scripts/start_data_collection.sh`
- **Monitor Script**: `scripts/monitor_collection.sh`
- **OANDA Integration**: `documentation/oanda_integration_guide.md`
- **Database Schema**: `scripts/init_oanda_schema.sql`

---

## 💾 **Backup & Maintenance**

### **Daily Backups**

```bash
# Add to crontab
0 2 * * * docker exec trading_timescaledb pg_dump -U trading_user trading_db | gzip > /backups/trading_db_$(date +\%Y\%m\%d).sql.gz
```

### **Vacuum Database** (Weekly)

```sql
-- Run in psql
VACUUM ANALYZE oanda_pricing;
VACUUM ANALYZE oanda_candles;
```

### **Monitor Disk Usage**

```bash
# Check database size
docker exec trading_timescaledb psql -U trading_user -d trading_db -c "
  SELECT pg_size_pretty(pg_database_size('trading_db'));
"

# Check table sizes
docker exec trading_timescaledb psql -U trading_user -d trading_db -c "
  SELECT
      schemaname,
      tablename,
      pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
  FROM pg_tables
  WHERE schemaname = 'public'
  ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

---

Happy collecting! 📊🚀
