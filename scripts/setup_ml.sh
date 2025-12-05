#!/bin/bash
# ML Integration Setup Script
set -e

echo "=============================================================="
echo "ML INTEGRATION SETUP"
echo "=============================================================="
echo ""

# Check if running from correct directory
if [ ! -f "requirements-ml.txt" ]; then
    echo "❌ Error: Run this script from the money_machine directory"
    exit 1
fi

echo "[1/4] Installing ML dependencies..."
source .venv/bin/activate
pip install -r requirements-ml.txt
echo "✅ ML packages installed"
echo ""

echo "[2/4] Creating models directory..."
mkdir -p models
echo "✅ Models directory created"
echo ""

echo "[3/4] Setting up database schema..."
docker exec trading_timescaledb psql -U trading_user -d trading_db -f /tmp/init_ml_schema.sql 2>/dev/null || {
    echo "⚠️  Database not running or schema already exists"
    echo "   To manually setup: docker cp scripts/init_ml_schema.sql trading_timescaledb:/tmp/"
    echo "                      docker exec trading_timescaledb psql -U trading_user -d trading_db -f /tmp/init_ml_schema.sql"
}
echo ""

echo "[4/4] Making scripts executable..."
chmod +x scripts/train_slippage_model.py
chmod +x scripts/setup_ml.sh
echo "✅ Scripts ready"
echo ""

echo "=============================================================="
echo "ML SETUP COMPLETE"
echo "=============================================================="
echo ""
echo "Next steps:"
echo "  1. Run your arbitrage system for 1 week to collect data"
echo "  2. Train the slippage model: python scripts/train_slippage_model.py"
echo "  3. Switch to ML-enhanced runner in your main script"
echo ""
echo "See docs/ML_INTEGRATION_GUIDE.md for detailed instructions"
echo ""
