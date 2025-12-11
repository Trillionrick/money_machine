#!/bin/bash
# Quick setup script for Unified AI Trading System
set -euo pipefail

echo "======================================================================"
echo "🚀 UNIFIED AI TRADING SYSTEM - SETUP"
echo "======================================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo "📋 Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
REQUIRED_VERSION="3.11"

if python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)"; then
    echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION (>= 3.11 required)"
else
    echo -e "${RED}✗${NC} Python $PYTHON_VERSION is too old. Please install Python 3.11+"
    exit 1
fi

# Check virtual environment
echo ""
echo "📦 Checking virtual environment..."
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}!${NC} Virtual environment not found. Creating..."
    python3 -m venv .venv
    echo -e "${GREEN}✓${NC} Virtual environment created"
else
    echo -e "${GREEN}✓${NC} Virtual environment exists"
fi

# Activate virtual environment
echo ""
echo "🔌 Activating virtual environment..."
source .venv/bin/activate

# Install core dependencies
echo ""
echo "📥 Installing core dependencies..."
pip install -q --upgrade pip

if [ -f "requirements.txt" ]; then
    pip install -q -r requirements.txt
    echo -e "${GREEN}✓${NC} Core dependencies installed"
else
    echo -e "${YELLOW}!${NC} requirements.txt not found. Installing manually..."
    pip install -q web3 httpx structlog python-dotenv
    echo -e "${GREEN}✓${NC} Basic dependencies installed"
fi

# Install ML dependencies
echo ""
echo "🧠 Installing ML/AI dependencies..."
if pip list | grep -q torch; then
    echo -e "${GREEN}✓${NC} PyTorch already installed"
else
    echo "   Installing PyTorch (CPU version)..."
    pip install -q torch --index-url https://download.pytorch.org/whl/cpu
    echo -e "${GREEN}✓${NC} PyTorch installed"
fi

if pip list | grep -q stable-baselines3; then
    echo -e "${GREEN}✓${NC} stable-baselines3 already installed"
else
    echo "   Installing RL framework..."
    pip install -q stable-baselines3 gymnasium
    echo -e "${GREEN}✓${NC} RL dependencies installed"
fi

if pip list | grep -q xgboost; then
    echo -e "${GREEN}✓${NC} XGBoost already installed"
else
    echo "   Installing XGBoost..."
    pip install -q xgboost
    echo -e "${GREEN}✓${NC} XGBoost installed"
fi

# Create necessary directories
echo ""
echo "📁 Creating directories..."
mkdir -p models/multi_agent_rl
mkdir -p data
mkdir -p logs
echo -e "${GREEN}✓${NC} Directories created"

# Check .env file
echo ""
echo "🔐 Checking environment configuration..."
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}!${NC} .env file not found. Creating template..."
    cat > .env <<EOF
# Core RPC URLs
ETH_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
POLYGON_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY

# Wallet addresses
METAMASK_WALLET_ADDRESS=0x...
RAINBOW_WALLET_ADDRESS=0x...

# Trading keys (NEVER COMMIT THESE)
WALLET_PRIVATE_KEY=0x...
FLASHBOTS_SIGNER_KEY=0x...

# Exchange API keys
KRAKEN_API_KEY=
KRAKEN_API_SECRET=
ALPACA_API_KEY=
ALPACA_API_SECRET=

# Optional API keys
ZEROX_API_KEY=
OPENSEA_API_KEY=
ONEINCH_API_KEY=

# Trading mode
TRADING_MODE=paper
DRY_RUN=true
ALPACA_PAPER=true

# AI/ML settings
ENABLE_AI_ORCHESTRATION=true
ENABLE_PREDICTIVE_ARBITRAGE=false
ENABLE_RL_AGENTS=false

# Risk limits
MAX_DAILY_LOSS_ETH=0.5
MAX_POSITION_ETH=10.0
ENABLE_CIRCUIT_BREAKERS=true
EOF
    echo -e "${YELLOW}!${NC} .env template created. PLEASE EDIT IT WITH YOUR KEYS!"
    echo "   Edit: nano .env"
else
    echo -e "${GREEN}✓${NC} .env file exists"
fi

# Test imports
echo ""
echo "🧪 Testing imports..."
python3 -c "
import sys
try:
    import web3
    import torch
    import xgboost
    import structlog
    print('✓ All core imports successful')
except ImportError as e:
    print(f'✗ Import failed: {e}')
    sys.exit(1)
" && echo -e "${GREEN}✓${NC} Import test passed" || echo -e "${RED}✗${NC} Import test failed"

# Check if models are trained
echo ""
echo "🤖 Checking ML models..."
if [ -f "models/predictive_transformer.pt" ]; then
    echo -e "${GREEN}✓${NC} Predictive model found"
else
    echo -e "${YELLOW}!${NC} Predictive model not trained yet"
    echo "   Run: python scripts/train_ml_models.py --predictive"
fi

if [ -d "models/multi_agent_rl" ] && [ "$(ls -A models/multi_agent_rl)" ]; then
    echo -e "${GREEN}✓${NC} RL agents found ($(ls models/multi_agent_rl/*.zip 2>/dev/null | wc -l) agents)"
else
    echo -e "${YELLOW}!${NC} RL agents not trained yet"
    echo "   Run: python scripts/train_ml_models.py --rl"
fi

# Summary
echo ""
echo "======================================================================"
echo "🎉 SETUP COMPLETE"
echo "======================================================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Configure your API keys:"
echo "   ${YELLOW}nano .env${NC}"
echo ""
echo "2. Test the unified system (dry-run):"
echo "   ${GREEN}python run_unified_system.py${NC}"
echo ""
echo "3. Start the dashboard:"
echo "   ${GREEN}./start_dashboard.sh${NC}"
echo ""
echo "4. Train ML models (after collecting data):"
echo "   ${GREEN}python scripts/train_ml_models.py --all${NC}"
echo ""
echo "5. Monitor logs:"
echo "   ${GREEN}tail -f logs/arbitrage.log | jq .${NC}"
echo ""
echo "======================================================================"
echo ""
echo "📚 For detailed instructions, see: ${GREEN}IMPLEMENTATION_COMPLETE.md${NC}"
echo ""
