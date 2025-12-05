#!/bin/bash
# Regenerate ML integration files after restoring from backup
# This recreates all ML-related files that were added after the backup was made

set -e

echo "=========================================================================="
echo "REGENERATING ML INTEGRATION FILES"
echo "=========================================================================="
echo ""
echo "This will recreate:"
echo "  - ML schemas, loggers, runners"
echo "  - Training scripts"
echo "  - Documentation"
echo ""
echo "Files will be downloaded from the Claude Code session or recreated"
echo ""

# Check we're in the right directory
if [ ! -f "requirements.txt" ]; then
    echo "❌ Error: Run this from money_machine directory"
    exit 1
fi

echo "[1/5] Creating directory structure..."
mkdir -p src/ai
mkdir -p src/live
mkdir -p scripts
mkdir -p docs
mkdir -p models
echo "✅ Directories created"
echo ""

echo "[2/5] Regenerating ML components..."
echo "  ⚠️  Files need to be recreated manually or saved from Claude session"
echo "     Required files:"
echo "       - src/ai/opportunity_logger.py"
echo "       - src/ai/slippage_predictor.py (if missing)"
echo "       - src/live/flash_arb_ml_runner.py"
echo "       - scripts/init_ml_schema.sql"
echo "       - scripts/train_slippage_model.py"
echo "       - scripts/setup_ml.sh"
echo "       - docs/ML_INTEGRATION_GUIDE.md"
echo "       - ML_QUICKSTART.md"
echo ""

echo "[3/5] Checking dependencies..."
if [ -f "requirements-ml.txt" ]; then
    echo "✅ requirements-ml.txt exists"
else
    echo "⚠️  requirements-ml.txt missing - creating minimal version"
    cat > requirements-ml.txt << 'EOF'
# Machine Learning & Deep Learning (Optional)
scikit-learn==1.5.2
xgboost==2.1.2
lightgbm==4.5.0
joblib==1.4.2
EOF
fi
echo ""

echo "[4/5] Checking core requirements..."
if [ -f "requirements-core.txt" ]; then
    echo "✅ requirements-core.txt exists"
else
    echo "⚠️  requirements-core.txt missing"
    echo "     Use requirements.txt or regenerate split structure"
fi
echo ""

echo "[5/5] Setup checklist..."
echo ""
echo "=========================================================================="
echo "MANUAL STEPS REQUIRED"
echo "=========================================================================="
echo ""
echo "Since ML files were created after your backup, you need to either:"
echo ""
echo "Option A: Ask Claude to recreate the files"
echo "  'Recreate all the ML integration files you made earlier'"
echo ""
echo "Option B: Copy from current session (before restoring)"
echo "  cp src/ai/opportunity_logger.py /tmp/ml_backup/"
echo "  cp src/ai/slippage_predictor.py /tmp/ml_backup/"
echo "  cp src/live/flash_arb_ml_runner.py /tmp/ml_backup/"
echo "  cp scripts/*.sql /tmp/ml_backup/"
echo "  cp scripts/train_slippage_model.py /tmp/ml_backup/"
echo "  cp scripts/setup_ml.sh /tmp/ml_backup/"
echo "  cp docs/ML_INTEGRATION_GUIDE.md /tmp/ml_backup/"
echo "  cp ML_QUICKSTART.md /tmp/ml_backup/"
echo "  # Then restore from /tmp/ml_backup/ after unzipping"
echo ""
echo "Option C: Pull from git (if you committed these files)"
echo "  git checkout -- src/ai/opportunity_logger.py"
echo "  git checkout -- src/live/flash_arb_ml_runner.py"
echo "  # etc."
echo ""
echo "=========================================================================="
echo ""
