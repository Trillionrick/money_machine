#!/bin/bash
# Convenience script to run Python commands with proper environment
# Usage: ./run.sh <python_script_or_command>
#
# Examples:
#   ./run.sh scripts/bootstrap_ml_models.py
#   ./run.sh scripts/validate_models.py --days 7
#   ./run.sh run_ai_integrated_arbitrage.py

set -e

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Activate virtual environment
source .venv/bin/activate

# Set PYTHONPATH to project root
export PYTHONPATH="$SCRIPT_DIR"

# Run the Python command
python3 "$@"
