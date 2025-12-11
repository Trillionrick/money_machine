#!/bin/bash
# Production Live Monitoring Dashboard
# Shows real-time AI trading system metrics

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# API endpoint
API_BASE="http://localhost:8080"

# Clear screen and show header
clear_and_header() {
    clear
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║         🚀 PRODUCTION AI TRADING SYSTEM - LIVE DASHBOARD 🚀           ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════════════════╝${NC}"
    echo -e "${CYAN}Session: $(date '+%Y-%m-%d %H:%M:%S UTC')${NC}"
    echo ""
}

# Check if system is running
check_system() {
    if ! curl -s "$API_BASE/api/ai/status" > /dev/null 2>&1; then
        echo -e "${RED}❌ ERROR: Trading system not responding at $API_BASE${NC}"
        echo -e "${YELLOW}Please start the system first:${NC}"
        echo -e "  cd /mnt/c/Users/catty/Desktop/money_machine"
        echo -e "  ./run.sh"
        exit 1
    fi
}

# Get system status
get_status() {
    curl -s "$API_BASE/api/ai/status" | jq -r '
        "  Status: \(if .enabled then "🟢 ENABLED" else "🔴 DISABLED" end)
  Mode: \(.mode | ascii_upcase)
  Portfolio: \(.portfolio_value_eth) ETH
  ML Enabled: \(if .ml_enabled then "Yes" else "No" end)"
    '
}

# Get safety status
get_safety() {
    # This will call your production safety endpoint when you add it
    local HOURLY_PNL=$(curl -s "$API_BASE/api/ai/metrics" 2>/dev/null | jq -r '.summary.decisions.total_profit_eth // 0')
    local TRADES_HOUR=$(curl -s "$API_BASE/api/ai/metrics" 2>/dev/null | jq -r '.summary.decisions.total_decisions // 0')

    echo -e "  Hourly P&L: ${GREEN}${HOURLY_PNL} ETH${NC}"
    echo -e "  Trades (1h): ${TRADES_HOUR}"
    echo -e "  Emergency Shutdown: ${GREEN}No${NC}"
}

# Get performance metrics
get_performance() {
    curl -s "$API_BASE/api/ai/metrics" | jq -r '.summary.decisions |
        "  Total Decisions: \(.total_decisions)
  Executed: \(.executed_decisions) (\(.execution_rate)%)
  Wins: \(.winning_trades) | Losses: \(.losing_trades)
  Win Rate: \(.win_rate)%
  Total Profit: \(.total_profit_eth) ETH
  Avg Profit: \(.average_profit_eth) ETH
  Avg Confidence: \(.average_confidence)"
    '
}

# Get ML model stats
get_ml_stats() {
    curl -s "$API_BASE/api/ai/metrics" | jq -r '.summary.ml_model |
        "  Accuracy: \(.accuracy)%
  Total Predictions: \(.total_predictions)
  Avg Confidence: \(.average_confidence)
  Last Updated: \(.last_update // "Never")"
    '
}

# Get latest decisions
get_latest_decisions() {
    curl -s "$API_BASE/api/ai/decisions/latest?limit=5" | jq -r '.decisions | .[] |
        "  [\(.timestamp | split("T")[1] | split(".")[0])] Confidence: \(.confidence) | Edge: \(.edge_bps) bps | \(if .executed then "✅ EXECUTED" else "⏸️  SKIPPED" end)"
    '
}

# Get health status
get_health() {
    local HEALTH=$(curl -s "$API_BASE/api/ai/health" | jq -r '.status')
    local WIN_RATE=$(curl -s "$API_BASE/api/ai/health" | jq -r '.win_rate')
    local NET_PROFIT=$(curl -s "$API_BASE/api/ai/health" | jq -r '.net_profit')

    case $HEALTH in
        "healthy")
            echo -e "  Overall Health: ${GREEN}🟢 HEALTHY${NC}"
            ;;
        "warning")
            echo -e "  Overall Health: ${YELLOW}🟡 WARNING${NC}"
            ;;
        "critical")
            echo -e "  Overall Health: ${RED}🔴 CRITICAL${NC}"
            ;;
    esac

    echo -e "  Win Rate: ${WIN_RATE}%"
    echo -e "  Net Profit: ${NET_PROFIT} USD"
}

# Get on-chain stats
get_onchain_stats() {
    curl -s "$API_BASE/api/ai/onchain/stats" 2>/dev/null | jq -r '
        "  AI Decisions Made: \(.ai_decisions_made)
  AI Decisions Executed: \(.ai_decisions_executed)
  Flash Loans Executed: \(.flash_loans_executed)
  Total Profit: \(.total_profit_eth) ETH
  Gas Spent: \(.total_gas_spent_eth) ETH"
    '
}

# Check for alerts
check_alerts() {
    local ALERTS=$(curl -s "$API_BASE/api/ai/health" | jq -r '.alerts | length')

    if [ "$ALERTS" -gt 0 ]; then
        echo -e "${RED}⚠️  ACTIVE ALERTS:${NC}"
        curl -s "$API_BASE/api/ai/health" | jq -r '.alerts | .[] |
            "  - \(.type): \(.value) (threshold: \(.threshold // "N/A"))"
        '
    else
        echo -e "${GREEN}✅ No active alerts${NC}"
    fi
}

# Main monitoring loop
main() {
    check_system

    while true; do
        clear_and_header

        echo -e "${GREEN}[SYSTEM STATUS]${NC}"
        get_status
        echo ""

        echo -e "${GREEN}[SAFETY GUARDS]${NC}"
        get_safety
        echo ""

        echo -e "${GREEN}[PERFORMANCE METRICS]${NC}"
        get_performance
        echo ""

        echo -e "${GREEN}[ML MODEL STATS]${NC}"
        get_ml_stats
        echo ""

        echo -e "${GREEN}[HEALTH CHECK]${NC}"
        get_health
        echo ""

        echo -e "${GREEN}[ALERTS]${NC}"
        check_alerts
        echo ""

        echo -e "${GREEN}[ON-CHAIN AI STATS]${NC}"
        get_onchain_stats
        echo ""

        echo -e "${GREEN}[LATEST DECISIONS - Last 5]${NC}"
        get_latest_decisions
        echo ""

        echo -e "${BLUE}════════════════════════════════════════════════════════════════════════${NC}"
        echo -e "${YELLOW}Refreshing in 5 seconds... (Ctrl+C to exit)${NC}"

        sleep 5
    done
}

# Run
main
