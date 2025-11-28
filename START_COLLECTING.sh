#!/bin/bash
# Quick Start Script for Forex Data Collection
# Run this after updating your OANDA credentials in .env

echo "🚀 Starting Forex Data Collection"
echo "=================================="
echo ""

# Check prerequisites
echo "Checking prerequisites..."

# Check Docker container
if ! docker ps | grep -q trading_timescaledb; then
    echo "❌ Database not running. Starting..."
    docker start trading_timescaledb
    sleep 5
fi
echo "✅ Database running"

# Check OANDA credentials
if grep -q "101-001-1234567-001" .env; then
    echo "⚠️  WARNING: Using placeholder account ID"
    echo ""
    echo "To get your real OANDA account ID:"
    echo "1. Go to: https://www.oanda.com/account/login"
    echo "2. Navigate to: My Account → My Services → Manage API Access"
    echo "3. Copy your Account ID (format: XXX-XXX-XXXXXXX-XXX)"
    echo "4. Update .env file: OANDA_ACCOUNT_ID=YOUR_REAL_ID"
    echo ""
    read -p "Press Enter to continue anyway, or Ctrl+C to exit and update credentials..."
fi

# Stop any existing collector
if [ -f "logs/collector.pid" ]; then
    OLD_PID=$(cat logs/collector.pid)
    if ps -p $OLD_PID > /dev/null 2>&1; then
        echo "Stopping old collector (PID: $OLD_PID)..."
        kill $OLD_PID 2>/dev/null
        sleep 2
    fi
fi

# Start collector
echo "Starting data collector..."
mkdir -p logs
nohup .venv/bin/python -u src/data_collection/forex_collector.py > logs/forex_collector.log 2>&1 &
PID=$!
echo $PID > logs/collector.pid

sleep 5

# Check if running
if ps -p $PID > /dev/null; then
    echo ""
    echo "✅ Data collector started successfully!"
    echo ""
    echo "   PID: $PID"
    echo "   Log: logs/forex_collector.log"
    echo ""
    echo "Monitor with:"
    echo "   tail -f logs/forex_collector.log"
    echo ""
    echo "Check data:"
    echo "   docker exec trading_timescaledb psql -U trading_user -d trading_db -c 'SELECT COUNT(*) FROM oanda_pricing;'"
    echo ""
    echo "Stop with:"
    echo "   kill $PID"
    echo ""
else
    echo "❌ Failed to start collector"
    echo "Check logs: tail -50 logs/forex_collector.log"
    exit 1
fi
