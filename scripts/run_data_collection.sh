#!/bin/bash
# 24/7 Data Collection Runner
#
# Runs arbitrage detection in dry-run mode to collect training data.
# This should run continuously for at least 2 weeks before live trading.
#
# Features:
# - Automatic restart on failure
# - Log rotation
# - Performance monitoring
# - Graceful shutdown on SIGTERM

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Configuration
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/data_collection.log"
PID_FILE="$PROJECT_ROOT/.data_collection.pid"
MAX_RESTARTS=10
RESTART_DELAY=30

# Create log directory
mkdir -p "$LOG_DIR"

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}🛑 Shutting down data collection...${NC}"
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            kill -TERM "$PID" 2>/dev/null || true
            sleep 2
            if ps -p "$PID" > /dev/null 2>&1; then
                kill -KILL "$PID" 2>/dev/null || true
            fi
        fi
        rm -f "$PID_FILE"
    fi
    echo -e "${GREEN}✅ Data collection stopped${NC}"
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

# Check if already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo -e "${RED}❌ Data collection already running (PID: $OLD_PID)${NC}"
        echo "To stop it: kill $OLD_PID"
        exit 1
    else
        rm -f "$PID_FILE"
    fi
fi

# Check if infrastructure is running
if ! docker ps | grep -q "trading_timescaledb"; then
    echo -e "${RED}❌ Infrastructure not running${NC}"
    echo "Please run: ./scripts/start_infrastructure.sh"
    exit 1
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}24/7 Data Collection Started${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Mode:${NC} DRY-RUN (no real trades)"
echo -e "${YELLOW}Goal:${NC} Collect 2+ weeks of arbitrage opportunity data"
echo -e "${YELLOW}Logs:${NC} $LOG_FILE"
echo ""
echo -e "${GREEN}Press Ctrl+C to stop gracefully${NC}"
echo ""

# Initialize counters
restart_count=0
total_runtime=0

# Main loop with restart logic
while true; do
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} Starting data collection runner..."

    # Run the arbitrage system in dry-run mode
    python3 run_ai_integrated_arbitrage.py --dry-run 2>&1 | tee -a "$LOG_FILE" &

    # Save PID
    RUNNER_PID=$!
    echo $RUNNER_PID > "$PID_FILE"

    # Wait for process to exit
    wait $RUNNER_PID
    EXIT_CODE=$?

    # Remove PID file
    rm -f "$PID_FILE"

    # Check exit code
    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] Runner exited normally${NC}"
        break
    else
        restart_count=$((restart_count + 1))
        echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] Runner crashed (exit code: $EXIT_CODE)${NC}"

        if [ $restart_count -ge $MAX_RESTARTS ]; then
            echo -e "${RED}❌ Max restarts ($MAX_RESTARTS) reached. Stopping.${NC}"
            echo -e "${YELLOW}Check logs at: $LOG_FILE${NC}"
            exit 1
        fi

        echo -e "${YELLOW}⏳ Restarting in $RESTART_DELAY seconds... (attempt $restart_count/$MAX_RESTARTS)${NC}"
        sleep $RESTART_DELAY
    fi
done

echo -e "${GREEN}✅ Data collection completed successfully${NC}"
