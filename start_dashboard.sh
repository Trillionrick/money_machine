#!/bin/bash
# Startup script for Arbitrage Dashboard
set -euo pipefail

echo "======================================================================"
echo "🚀 LAUNCHING ARBITRAGE DASHBOARD"
echo "======================================================================"
echo ""
# Load environment if present
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

echo "Dashboard will be available at: http://localhost:8080"
echo "Metamask: ${METAMASK_WALLET_ADDRESS:-not set}"
echo "Rainbow : ${RAINBOW_WALLET_ADDRESS:-not set}"
echo "RPC     : ${ETH_RPC_URL:-${ETHEREUM_RPC_URL:-not set}}"
echo "Polygon : ${POLYGON_RPC_URL:-not set} (chain ${POLYGON_CHAIN_ID:-137})"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""
echo "======================================================================"
echo ""

# Activate virtual environment
if [ ! -f ".venv/bin/activate" ]; then
  echo "Virtualenv missing at .venv; please create it (python -m venv .venv) before starting." >&2
  exit 1
fi
source .venv/bin/activate

# Start the web server (prefer uvicorn with reload for fast iteration)
if command -v uvicorn >/dev/null 2>&1; then
  uvicorn web_server:app --host 0.0.0.0 --port 8080 --reload
else
  python web_server.py
fi
