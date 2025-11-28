#!/bin/bash
# Start forex data collection in the background

set -e

echo "🚀 Starting Forex Data Collection"
echo "=================================="
echo ""

# Check if TimescaleDB is running
if ! docker ps | grep -q trading_timescaledb; then
    echo "❌ Error: TimescaleDB is not running"
    echo "Start it with: docker start trading_timescaledb"
    exit 1
fi

echo "✅ TimescaleDB is running"

# Check if database is accessible
if ! docker exec trading_timescaledb pg_isready -U trading_user > /dev/null 2>&1; then
    echo "❌ Error: Database is not ready"
    exit 1
fi

echo "✅ Database is accessible"

# Check OANDA credentials
if ! grep -q "OANDA_API_TOKEN=e40e15bb" .env 2>/dev/null; then
    echo "⚠️  Warning: OANDA_API_TOKEN may not be set in .env"
fi

echo "✅ Configuration looks good"
echo ""

# Install required Python packages
echo "📦 Installing dependencies..."
pip install -q structlog asyncpg

echo "✅ Dependencies installed"
echo ""

# Create logs directory
mkdir -p logs

# Get current date for log file
LOG_FILE="logs/forex_collector_$(date +%Y%m%d_%H%M%S).log"

echo "📊 Starting data collector..."
echo "   Log file: $LOG_FILE"
echo ""

# Start collector in background
nohup python -u src/data_collection/forex_collector.py > "$LOG_FILE" 2>&1 &

# Get PID
PID=$!

# Save PID to file
echo $PID > logs/collector.pid

echo "✅ Data collector started!"
echo ""
echo "   PID: $PID"
echo "   Log: $LOG_FILE"
echo ""
echo "Monitor with:"
echo "   tail -f $LOG_FILE"
echo ""
echo "Stop with:"
echo "   kill $PID"
echo "   # or"
echo "   bash scripts/stop_data_collection.sh"
echo ""

# Wait a few seconds and check if still running
sleep 3

if ps -p $PID > /dev/null; then
    echo "✅ Collector is running successfully!"
    echo ""
    echo "Collecting data for:"
    echo "   • EUR/USD, GBP/USD, USD/JPY"
    echo "   • AUD/USD, USD/CAD, USD/CHF"
    echo "   • NZD/USD, EUR/GBP, EUR/JPY, GBP/JPY"
    echo ""
    echo "Data being stored in TimescaleDB:"
    echo "   • Real-time tick data (oanda_pricing table)"
    echo "   • Hourly candles (oanda_candles table)"
    echo "   • 5-minute candles for major pairs"
else
    echo "❌ Error: Collector stopped unexpectedly"
    echo "Check log file: $LOG_FILE"
    exit 1
fi
