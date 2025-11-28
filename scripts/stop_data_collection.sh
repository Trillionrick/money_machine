#!/bin/bash
# Stop forex data collection

echo "🛑 Stopping Forex Data Collection"
echo "=================================="
echo ""

# Check if PID file exists
if [ ! -f "logs/collector.pid" ]; then
    echo "⚠️  No PID file found"
    echo "Searching for running collector process..."

    # Try to find process by name
    PID=$(pgrep -f "forex_collector.py" | head -1)

    if [ -z "$PID" ]; then
        echo "❌ No running collector found"
        exit 0
    fi
else
    PID=$(cat logs/collector.pid)
fi

echo "Found collector process: PID $PID"

# Check if process is running
if ! ps -p $PID > /dev/null 2>&1; then
    echo "⚠️  Process $PID is not running"
    rm -f logs/collector.pid
    exit 0
fi

# Send SIGTERM for graceful shutdown
echo "Sending shutdown signal..."
kill -TERM $PID

# Wait up to 10 seconds for graceful shutdown
for i in {1..10}; do
    if ! ps -p $PID > /dev/null 2>&1; then
        echo "✅ Collector stopped gracefully"
        rm -f logs/collector.pid
        exit 0
    fi
    sleep 1
    echo -n "."
done

echo ""
echo "⚠️  Process did not stop gracefully, forcing..."
kill -KILL $PID

sleep 1

if ! ps -p $PID > /dev/null 2>&1; then
    echo "✅ Collector stopped (forced)"
    rm -f logs/collector.pid
else
    echo "❌ Failed to stop collector"
    exit 1
fi
