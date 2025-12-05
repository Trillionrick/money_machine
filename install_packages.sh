#!/bin/bash
# Incremental package installer - avoids hangs by installing in small batches
set -e

echo "Installing packages incrementally..."
source .venv/bin/activate

echo "[1/6] Web framework..."
pip install fastapi uvicorn websockets httpx structlog python-dotenv

echo "[2/6] Data processing..."
pip install polars pyarrow numpy

echo "[3/6] Web3..."
pip install web3 gql

echo "[4/6] Brokers..."
pip install alpaca-py ccxt python-binance krakenex

echo "[5/6] Database..."
pip install asyncpg sqlalchemy psycopg2-binary redis alembic

echo "[6/6] Config & utils..."
pip install pydantic pydantic-settings orjson msgspec backoff tenacity uvloop typing_extensions

echo "✅ Core packages installed successfully!"
echo "Total time: ~5-10 minutes"
echo ""
echo "To add ML later: pip install -r requirements-ml.txt"
