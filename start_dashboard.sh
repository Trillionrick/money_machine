#!/bin/bash
# Startup script for Arbitrage Dashboard

echo "======================================================================"
echo "🚀 LAUNCHING ARBITRAGE DASHBOARD"
echo "======================================================================"
echo ""
echo "Dashboard will be available at: http://localhost:8080"
echo "Metamask: ${METAMASK_WALLET_ADDRESS:-not set}"
echo "Rainbow : ${RAINBOW_WALLET_ADDRESS:-not set}"
echo "RPC     : ${ETH_RPC_URL:-${ETHEREUM_RPC_URL:-not set}}"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""
echo "======================================================================"
echo ""

# Activate virtual environment
source .venv/bin/activate

# Start the web server (prefer uvicorn with reload for fast iteration)
if command -v uvicorn >/dev/null 2>&1; then
  uvicorn web_server:app --host 0.0.0.0 --port 8080 --reload
else
  python web_server.py
fi
