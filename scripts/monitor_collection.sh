#!/bin/bash
# Monitor forex data collection

echo "📊 Forex Data Collection Monitor"
echo "================================="
echo ""

# Check if collector is running
if [ -f "logs/collector.pid" ]; then
    PID=$(cat logs/collector.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "✅ Collector is running (PID: $PID)"

        # Get runtime
        RUNTIME=$(ps -p $PID -o etime= | tr -d ' ')
        echo "   Runtime: $RUNTIME"

        # Get memory usage
        MEM=$(ps -p $PID -o rss= | awk '{printf "%.1f MB", $1/1024}')
        echo "   Memory: $MEM"
    else
        echo "❌ Collector is not running (stale PID file)"
    fi
else
    echo "❌ Collector is not running"
fi

echo ""

# Check TimescaleDB
if docker ps | grep -q trading_timescaledb; then
    echo "✅ TimescaleDB is running"
else
    echo "❌ TimescaleDB is not running"
fi

echo ""

# Get database statistics
echo "📈 Database Statistics:"
echo "======================="

docker exec trading_timescaledb psql -U trading_user -d trading_db -t << 'EOF'
-- Tick data count
SELECT '   Tick prices: ' || COUNT(*)::TEXT FROM oanda_pricing;

-- Candle count
SELECT '   Candles: ' || COUNT(*)::TEXT FROM oanda_candles;

-- Latest tick
SELECT '   Latest tick: ' || MAX(time)::TEXT FROM oanda_pricing;

-- Latest candle
SELECT '   Latest candle: ' || MAX(time)::TEXT FROM oanda_candles;

-- Instruments with data
SELECT '   Active instruments: ' || COUNT(DISTINCT instrument)::TEXT FROM oanda_pricing;

-- Database size
SELECT '   Database size: ' || pg_size_pretty(pg_database_size('trading_db'));
EOF

echo ""

# Show recent activity
echo "📝 Recent Activity (last 10 ticks):"
echo "===================================="

docker exec trading_timescaledb psql -U trading_user -d trading_db -c "
SELECT
    time,
    instrument,
    bid,
    ask,
    spread
FROM oanda_pricing
ORDER BY time DESC
LIMIT 10;
"

echo ""

# Show latest log entries
if [ -f "logs/collector.pid" ]; then
    LATEST_LOG=$(ls -t logs/forex_collector_*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
        echo "📜 Latest Log Entries:"
        echo "======================"
        tail -20 "$LATEST_LOG"
        echo ""
        echo "Full log: $LATEST_LOG"
    fi
fi

echo ""
echo "Commands:"
echo "  • View live logs: tail -f logs/forex_collector_*.log"
echo "  • Stop collector: bash scripts/stop_data_collection.sh"
echo "  • Restart: bash scripts/stop_data_collection.sh && bash scripts/start_data_collection.sh"
