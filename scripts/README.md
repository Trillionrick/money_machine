# TimescaleDB Setup Scripts

This directory contains scripts for setting up and managing the TimescaleDB database for OANDA forex trading data.

## Scripts

1. **init_oanda_schema.sql** - Database schema initialization (auto-run by Docker)
2. **verify_db_setup.py** - Verify database setup and schema
3. **fetch_initial_data.py** - Fetch historical forex data from OANDA

## Quick Start

### 1. Start TimescaleDB

```bash
# From project root
docker-compose up -d timescaledb

# Wait for database to initialize (30 seconds)
sleep 30
```

### 2. Verify Setup

```bash
# Install asyncpg if needed
pip install asyncpg

# Run verification
python scripts/verify_db_setup.py
```

### 3. Fetch Initial Data

```bash
# Make sure .env has OANDA credentials
python scripts/fetch_initial_data.py
```

## Database Connection

- **Host**: localhost
- **Port**: 5433
- **Database**: trading_db
- **User**: trading_user
- **Password**: trading_pass_change_in_production

### Connect with psql

```bash
psql -h localhost -p 5433 -U trading_user -d trading_db
```

### Connect with Python

```python
import asyncpg

conn = await asyncpg.connect(
    host="localhost",
    port=5433,
    user="trading_user",
    password="trading_pass_change_in_production",
    database="trading_db",
)
```

## Tables Created

- `oanda_candles` - OHLCV candle data (hypertable)
- `oanda_transactions` - Transaction history (hypertable)
- `oanda_positions` - Position snapshots (hypertable)
- `oanda_pricing` - Tick-level pricing (hypertable)
- `oanda_instruments` - Instrument metadata

## Materialized Views

- `oanda_candles_1h` - 1-hour aggregates (auto-refreshed every 10 min)
- `oanda_candles_1d` - 1-day aggregates (auto-refreshed every 1 hour)

## Useful Queries

### Get latest EUR/USD candle

```sql
SELECT * FROM get_latest_candle('EUR_USD', 'H1');
```

### Get current spread

```sql
SELECT get_current_spread('EUR_USD');
```

### Query candles by date range

```sql
SELECT time, open, high, low, close, volume
FROM oanda_candles
WHERE instrument = 'EUR_USD'
  AND granularity = 'H1'
  AND time >= NOW() - INTERVAL '7 days'
ORDER BY time DESC;
```

### Check database size

```sql
SELECT pg_size_pretty(pg_database_size('trading_db'));
```

### Check compression statistics

```sql
SELECT hypertable_name,
       pg_size_pretty(before_compression_total_bytes) as before,
       pg_size_pretty(after_compression_total_bytes) as after,
       ROUND(100.0 * (before_compression_total_bytes - after_compression_total_bytes)
             / before_compression_total_bytes, 2) as savings_pct
FROM timescaledb_information.compression_settings;
```

## Troubleshooting

### Database won't start

```bash
# Check logs
docker logs trading_timescaledb

# Remove old data and restart
docker-compose down
rm -rf data/timescaledb
docker-compose up -d timescaledb
```

### Connection refused

```bash
# Check if container is running
docker ps | grep timescaledb

# Check port
netstat -an | grep 5433
```

### Schema not initialized

```bash
# Manually run schema
docker exec -i trading_timescaledb psql -U trading_user -d trading_db < scripts/init_oanda_schema.sql
```
