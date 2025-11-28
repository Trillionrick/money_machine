# 🚀 Quick Start: Forex Data Collection

## What Was Created

I've built a complete forex data collection system for you:

### ✅ **Core Components**

1. **Real-Time Data Collector** (`src/data_collection/forex_collector.py`)
   - Streams live prices for 10 major forex pairs
   - Stores tick data in TimescaleDB
   - Periodically fetches historical candles
   - Auto-reconnects on failures
   - Structured logging

2. **Management Scripts**
   - `scripts/start_data_collection.sh` - Start collector
   - `scripts/stop_data_collection.sh` - Stop collector
   - `scripts/monitor_collection.sh` - Monitor status
   - `scripts/setup_timescaledb.sh` - Setup database

3. **Documentation**
   - `DATA_COLLECTION_GUIDE.md` - Complete guide
   - `TIMESCALEDB_SETUP.md` - Database setup
   - `documentation/oanda_integration_guide.md` - OANDA integration

---

## ⚡ Manual Setup (Recommended for WSL2)

Due to Docker credential issues in WSL2, here's the manual approach:

### **Step 1: Fix Docker Credentials**

```bash
# Create Docker config
mkdir -p ~/.docker
cat > ~/.docker/config.json << 'EOF'
{
  "credsStore": ""
}
EOF

# Restart Docker Desktop (in Windows, not WSL2)
```

### **Step 2: Start TimescaleDB**

```bash
cd /mnt/c/Users/catty/Desktop/money_machine

# Pull image (if you get credentials error, use Docker Desktop GUI to pull "timescale/timescaledb:latest-pg16")
docker pull timescale/timescaledb:latest-pg16

# Create data directory
mkdir -p ./data/timescaledb

# Start container (using port 5434 since 5433 is in use)
docker run -d \
  --name trading_timescaledb \
  -p 5434:5432 \
  -e POSTGRES_USER=trading_user \
  -e POSTGRES_PASSWORD=trading_pass_change_in_production \
  -e POSTGRES_DB=trading_db \
  -v "$(pwd)/data/timescaledb:/var/lib/postgresql/data" \
  timescale/timescaledb:latest-pg16 \
  postgres \
  -c shared_preload_libraries=timescaledb \
  -c max_connections=200

# Wait for startup
sleep 30

# Check if running
docker ps | grep timescale
```

### **Step 3: Initialize Database Schema**

```bash
# Initialize schema
docker exec -i trading_timescaledb psql -U trading_user -d trading_db < scripts/init_oanda_schema.sql

# Should see: ✅ OANDA database schema initialized successfully!
```

### **Step 4: Verify Setup**

```bash
# Install Python dependencies
pip install asyncpg structlog

# Run verification
# First, update port in verify script:
sed -i 's/port=5433/port=5434/' scripts/verify_db_setup.py

# Run verification
python scripts/verify_db_setup.py
```

### **Step 5: Update Data Collector Port**

```bash
# Update collector to use port 5434
sed -i 's/port=5433/port=5434/' src/data_collection/forex_collector.py
```

### **Step 6: Start Data Collection**

```bash
# Create logs directory
mkdir -p logs

# Start collector in background
nohup python -u src/data_collection/forex_collector.py > logs/forex_collector.log 2>&1 &

# Save PID
echo $! > logs/collector.pid

# Check it's running
tail -f logs/forex_collector.log
```

---

## 🎯 Alternative: Use Docker Desktop GUI

If Docker commands aren't working in WSL2:

1. **Open Docker Desktop** (Windows)

2. **Pull Image**
   - Go to "Images" tab
   - Click "Pull"
   - Enter: `timescale/timescaledb:latest-pg16`

3. **Create Container**
   - Click "Run" next to the image
   - Expand "Optional settings"
   - **Container name**: `trading_timescaledb`
   - **Port**: Host `5434` → Container `5432`
   - **Environment variables**:
     - `POSTGRES_USER=trading_user`
     - `POSTGRES_PASSWORD=trading_pass_change_in_production`
     - `POSTGRES_DB=trading_db`
   - **Volume**: `C:\Users\catty\Desktop\money_machine\data\timescaledb` → `/var/lib/postgresql/data`
   - Click "Run"

4. **Initialize Schema** (from WSL2):
   ```bash
   docker exec -i trading_timescaledb psql -U trading_user -d trading_db < scripts/init_oanda_schema.sql
   ```

5. **Start Collector** (from WSL2):
   ```bash
   sed -i 's/port=5433/port=5434/' src/data_collection/forex_collector.py
   python src/data_collection/forex_collector.py
   ```

---

## 📊 What Gets Collected

### **10 Major Forex Pairs**
- EUR/USD, GBP/USD, USD/JPY
- AUD/USD, USD/CAD, USD/CHF
- NZD/USD, EUR/GBP, EUR/JPY, GBP/JPY

### **Data Types**
- **Tick Data**: Bid/Ask prices ~250ms updates
- **1-Hour Candles**: Last 50 hours (every 15 min)
- **5-Min Candles**: Top 3 pairs (every 15 min)

### **Storage**
- **oanda_pricing** - Tick-level data
- **oanda_candles** - OHLCV candles
- **Compression** - Automatic after 1-7 days

---

## 🔍 Monitor Collection

### **Check if Running**

```bash
# Check process
ps aux | grep forex_collector

# View logs
tail -f logs/forex_collector.log

# Check database
docker exec trading_timescaledb psql -U trading_user -d trading_db -c "
  SELECT COUNT(*) as tick_count FROM oanda_pricing;
"
```

### **View Latest Prices**

```bash
docker exec trading_timescaledb psql -U trading_user -d trading_db -c "
  SELECT time, instrument, bid, ask, spread
  FROM oanda_pricing
  ORDER BY time DESC
  LIMIT 10;
"
```

### **Check Statistics**

```bash
# In the log file, you'll see every minute:
# collector_statistics uptime_minutes=15 prices_received=3420 prices_stored=3420
#   candles_stored=150 errors=0 prices_per_minute=228.0
```

---

## 🛑 Stop Collection

```bash
# Graceful stop
kill -TERM $(cat logs/collector.pid)

# Or force kill
kill -9 $(cat logs/collector.pid)

# Clean up PID file
rm logs/collector.pid
```

---

## 📈 Expected Results

After 1 hour of collection, you should have:

- **~15,000-20,000 tick prices** (10 instruments × ~30 ticks/min × 60 min)
- **~80 hourly candles** (10 instruments × 1 candle + historical)
- **~300 5-minute candles** (3 instruments × 100 candles)
- **Database size**: ~5-10 MB (before compression)

---

## ❌ Troubleshooting

### **Port 5433 Already in Use**

**Solution**: Use port 5434 instead (as shown above)

Update all files:
```bash
# Update collector
sed -i 's/5433/5434/g' src/data_collection/forex_collector.py

# Update verification script
sed -i 's/5433/5434/g' scripts/verify_db_setup.py

# Update fetch script
sed -i 's/5433/5434/g' scripts/fetch_initial_data.py
```

### **Docker Credential Errors**

**Solution**: Use Docker Desktop GUI to pull images, then use WSL2 commands to start containers

### **"Module not found" Errors**

**Solution**: Install dependencies
```bash
pip install asyncpg structlog orjson
```

### **OANDA Connection Errors**

**Solution**: Check credentials
```bash
# Verify .env file
grep OANDA .env

# Test connection
python -c "
import asyncio
from src.brokers.oanda_config import OandaConfig
from src.brokers.oanda_adapter import OandaAdapter

async def test():
    try:
        config = OandaConfig.from_env()
        async with OandaAdapter(config) as adapter:
            account = await adapter.get_account()
            print(f'✅ Connected! Balance: {account[\"balance\"]}')
    except Exception as e:
        print(f'❌ Failed: {e}')

asyncio.run(test())
"
```

---

## 🎉 Success Indicators

You'll know it's working when:

1. ✅ **Logs show**: `collector_started tasks=3`
2. ✅ **Every minute**: `collector_statistics` with increasing counts
3. ✅ **Database**: `SELECT COUNT(*) FROM oanda_pricing` returns growing number
4. ✅ **No errors**: `errors=0` in statistics

---

## 📚 Next Steps

Once collecting:

1. **Wait 1 hour** - Let data accumulate
2. **Run analytics** - See `DATA_COLLECTION_GUIDE.md` for SQL queries
3. **Build strategies** - Use collected data for backtesting
4. **Live trading** - Connect strategies to real-time stream

---

## 🆘 Need Help?

- **Full Documentation**: `DATA_COLLECTION_GUIDE.md`
- **Database Setup**: `TIMESCALEDB_SETUP.md`
- **OANDA Integration**: `documentation/oanda_integration_guide.md`

---

## 📝 Files Created

- `src/data_collection/forex_collector.py` - Main collector
- `scripts/start_data_collection.sh` - Start script
- `scripts/stop_data_collection.sh` - Stop script
- `scripts/monitor_collection.sh` - Monitor script
- `scripts/setup_timescaledb.sh` - Database setup
- `scripts/forex-collector.service` - Systemd service
- `DATA_COLLECTION_GUIDE.md` - Complete guide
- `TIMESCALEDB_SETUP.md` - DB setup guide

All ready to go! Just follow the manual setup steps above. 🚀
