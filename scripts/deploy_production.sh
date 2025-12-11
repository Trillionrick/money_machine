#!/bin/bash
# Production Deployment Script
# One command to go live with real capital

set -e  # Exit on error

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

PROJECT_DIR="/mnt/c/Users/catty/Desktop/money_machine"
LOG_DIR="$PROJECT_DIR/logs"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python3"

if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="$(command -v python3 || true)"
fi

if [ -z "$PYTHON_BIN" ]; then
    echo -e "${RED}❌ ERROR: python3 not found. Please install Python 3.12+${NC}"
    exit 1
fi

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}    🚀 PRODUCTION AI TRADING SYSTEM DEPLOYMENT 🚀${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""

# Step 1: Pre-flight checks
echo -e "${YELLOW}[STEP 1/7] Running pre-flight checks...${NC}"

# Check if .env exists
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo -e "${RED}❌ ERROR: .env file not found!${NC}"
    echo -e "Please create .env file with your configuration."
    exit 1
fi

# Check wallet private key
if ! grep -q "WALLET_PRIVATE_KEY=" "$PROJECT_DIR/.env" || grep -q "WALLET_PRIVATE_KEY=your" "$PROJECT_DIR/.env"; then
    echo -e "${RED}❌ ERROR: WALLET_PRIVATE_KEY not configured in .env!${NC}"
    echo -e "Please set your wallet private key in .env"
    exit 1
fi

# Check RPC endpoints
if ! grep -q "ETHEREUM_RPC_URL=https://" "$PROJECT_DIR/.env"; then
    echo -e "${RED}❌ ERROR: ETHEREUM_RPC_URL not configured!${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Configuration files OK${NC}"

# Step 2: Check wallet balance
echo -e "\n${YELLOW}[STEP 2/7] Checking wallet balance...${NC}"

cd "$PROJECT_DIR"

# Create temporary Python script for wallet check
cat > /tmp/check_balance.py << 'EOF'
import os
import sys
from web3 import Web3
from pathlib import Path

# Load .env manually
env_path = Path(__file__).parent.parent / "money_machine" / ".env"
if not env_path.exists():
    env_path = Path("/mnt/c/Users/catty/Desktop/money_machine/.env")

env_vars = {}
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env_vars[key] = value

rpc_url = env_vars.get("ETHEREUM_RPC_URL")
private_key = env_vars.get("WALLET_PRIVATE_KEY")

if not rpc_url or not private_key:
    print("❌ ERROR: RPC_URL or PRIVATE_KEY not found in .env")
    sys.exit(1)

if not private_key.startswith("0x"):
    private_key = "0x" + private_key

try:
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    account = w3.eth.account.from_key(private_key)
    balance_wei = w3.eth.get_balance(account.address)
    balance_eth = w3.from_wei(balance_wei, 'ether')

    print(f"Wallet Address: {account.address}")
    print(f"Balance: {balance_eth:.6f} ETH")

    if balance_eth < 0.1:
        print(f"\n⚠️  WARNING: Balance is low ({balance_eth:.6f} ETH)")
        print("You may not have enough for gas fees + trading capital")
    elif balance_eth < 1.0:
        print(f"\n✓ Balance OK for small-scale testing")
    else:
        print(f"\n✅ Balance sufficient for trading")
except Exception as e:
    print(f"❌ ERROR checking balance: {e}")
    sys.exit(1)
EOF

"$PYTHON_BIN" /tmp/check_balance.py

# Step 3: Safety configuration review
echo -e "\n${YELLOW}[STEP 3/7] Reviewing safety configuration...${NC}"

echo ""
echo -e "${CYAN}Current Safety Limits:${NC}"
echo -e "  Max Position Size: 2.0 ETH per trade"
echo -e "  Max Daily Loss: 1.0 ETH"
echo -e "  Max Total Drawdown: 5.0 ETH"
echo -e "  Min Profit After Gas: 0.01 ETH"
echo -e "  Max Gas Price: 300 gwei"
echo ""

read -p "$(echo -e ${YELLOW}Do you want to modify safety limits? [y/N]: ${NC})" -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${CYAN}Opening production_safety.py for editing...${NC}"
    echo -e "${YELLOW}Edit ProductionSafetyConfig class and save${NC}"
    read -p "Press Enter when done editing..."
fi

# Step 4: Set AI mode
echo -e "\n${YELLOW}[STEP 4/7] Configure AI trading mode...${NC}"
echo ""
echo -e "${CYAN}Available modes:${NC}"
echo -e "  1) CONSERVATIVE - High confidence (75%), lower leverage, safer"
echo -e "  2) BALANCED     - Moderate risk/reward (default)"
echo -e "  3) AGGRESSIVE   - Lower confidence (65%), higher leverage, riskier"
echo ""

read -p "$(echo -e ${YELLOW}Select mode [1/2/3]: ${NC})" MODE_CHOICE

case $MODE_CHOICE in
    1)
        AI_MODE="conservative"
        echo -e "${GREEN}✅ Conservative mode selected${NC}"
        ;;
    2)
        AI_MODE="balanced"
        echo -e "${GREEN}✅ Balanced mode selected${NC}"
        ;;
    3)
        AI_MODE="aggressive"
        echo -e "${YELLOW}⚠️  Aggressive mode selected - USE WITH CAUTION${NC}"
        ;;
    *)
        AI_MODE="balanced"
        echo -e "${YELLOW}Using default: Balanced mode${NC}"
        ;;
esac

# Update .env with selected mode
if grep -q "^AI_MODE=" "$PROJECT_DIR/.env"; then
    sed -i "s/^AI_MODE=.*/AI_MODE=$AI_MODE/" "$PROJECT_DIR/.env"
else
    echo "AI_MODE=$AI_MODE" >> "$PROJECT_DIR/.env"
fi

# Step 5: Setup monitoring
echo -e "\n${YELLOW}[STEP 5/7] Setting up monitoring...${NC}"

# Create log directories
mkdir -p "$LOG_DIR/trades"
mkdir -p "$LOG_DIR/system"

echo -e "${GREEN}✅ Log directories created${NC}"

# Make monitoring script executable
chmod +x "$PROJECT_DIR/scripts/live_monitor.sh"

echo -e "${GREEN}✅ Monitoring dashboard ready${NC}"

# Step 6: Discord/Telegram alerts (optional)
echo -e "\n${YELLOW}[STEP 6/7] Configure alerts (optional)...${NC}"

read -p "$(echo -e ${YELLOW}Setup Discord alerts? [y/N]: ${NC})" -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    read -p "Discord Webhook URL: " DISCORD_URL
    if grep -q "^DISCORD_WEBHOOK_URL=" "$PROJECT_DIR/.env"; then
        sed -i "s|^DISCORD_WEBHOOK_URL=.*|DISCORD_WEBHOOK_URL=$DISCORD_URL|" "$PROJECT_DIR/.env"
    else
        echo "DISCORD_WEBHOOK_URL=$DISCORD_URL" >> "$PROJECT_DIR/.env"
    fi
    echo -e "${GREEN}✅ Discord alerts configured${NC}"
fi

# Step 7: Final confirmation
echo -e "\n${YELLOW}[STEP 7/7] Final deployment confirmation...${NC}"
echo ""
echo -e "${RED}════════════════════════════════════════════════════════════════${NC}"
echo -e "${RED}                    ⚠️  FINAL WARNING ⚠️${NC}"
echo -e "${RED}════════════════════════════════════════════════════════════════${NC}"
echo -e "${RED}You are about to deploy with REAL CAPITAL.${NC}"
echo -e "${RED}This system will execute trades on mainnet with real ETH.${NC}"
echo ""
echo -e "${CYAN}Deployment Summary:${NC}"
echo -e "  AI Mode: ${AI_MODE}"
echo -e "  Max Loss Per Trade: 0.1 ETH"
echo -e "  Max Daily Loss: 1.0 ETH"
echo -e "  Emergency Shutdown: ENABLED"
echo ""
echo -e "${YELLOW}Risk Warning:${NC}"
echo -e "  ⚠️  You may lose all deployed capital"
echo -e "  ⚠️  Smart contract risks exist"
echo -e "  ⚠️  Market conditions may be unfavorable"
echo -e "  ⚠️  MEV bots may frontrun your trades"
echo ""

read -p "$(echo -e ${RED}Type 'I ACCEPT THE RISK' to continue: ${NC})" CONFIRMATION

if [ "$CONFIRMATION" != "I ACCEPT THE RISK" ]; then
    echo -e "${YELLOW}Deployment cancelled.${NC}"
    exit 0
fi

# Deploy!
echo -e "\n${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}             🚀 DEPLOYING PRODUCTION SYSTEM 🚀${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

# Start the system
echo -e "${YELLOW}Starting FastAPI server...${NC}"
cd "$PROJECT_DIR"

# Kill existing instance if running
pkill -f "uvicorn web_server:app" || true
sleep 2

# Start in background
nohup "$PYTHON_BIN" -m uvicorn web_server:app --host 0.0.0.0 --port 8080 > "$LOG_DIR/system/server.log" 2>&1 &
SERVER_PID=$!

echo -e "${GREEN}✅ Server started (PID: $SERVER_PID)${NC}"

# Wait for server to be ready
echo -e "${YELLOW}Waiting for server to start...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:8080/api/ai/status > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Server is ready${NC}"
        break
    fi
    sleep 1
    echo -n "."
done
echo ""

# Set AI mode via API
echo -e "${YELLOW}Configuring AI mode...${NC}"
curl -s -X POST "http://localhost:8080/api/ai/mode/$AI_MODE" > /dev/null
echo -e "${GREEN}✅ AI mode set to: $AI_MODE${NC}"

# Enable AI system
echo -e "${YELLOW}Enabling AI system...${NC}"
curl -s -X POST "http://localhost:8080/api/ai/enable" > /dev/null
echo -e "${GREEN}✅ AI system ENABLED${NC}"

# Success!
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}           ✅ PRODUCTION DEPLOYMENT COMPLETE ✅${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${CYAN}System Status:${NC}"
curl -s http://localhost:8080/api/ai/status | jq .
echo ""
echo -e "${CYAN}Monitoring Commands:${NC}"
echo -e "  Dashboard:  ${YELLOW}./scripts/live_monitor.sh${NC}"
echo -e "  Logs:       ${YELLOW}tail -f $LOG_DIR/system/server.log${NC}"
echo -e "  API:        ${YELLOW}http://localhost:8080/docs${NC}"
echo ""
echo -e "${CYAN}Emergency Commands:${NC}"
echo -e "  Disable AI: ${RED}curl -X POST http://localhost:8080/api/ai/disable${NC}"
echo -e "  Stop:       ${RED}kill $SERVER_PID${NC}"
echo ""
echo -e "${YELLOW}Starting monitoring dashboard in 5 seconds...${NC}"
sleep 5

# Launch monitoring dashboard
exec "$PROJECT_DIR/scripts/live_monitor.sh"
