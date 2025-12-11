#!/bin/bash
# TimescaleDB Setup Script
# Automatically sets up TimescaleDB for OANDA trading data

set -e  # Exit on error

echo "🚀 TimescaleDB Setup for OANDA Trading Data"
echo "============================================"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running"
    echo "Please start Docker Desktop and try again"
    exit 1
fi

echo "✅ Docker is running"
echo ""

# Check if scripts directory exists
if [ ! -d "scripts" ]; then
    echo "❌ Error: Must run from project root directory"
    exit 1
fi

# Fix Docker credentials if needed
echo "🔧 Configuring Docker credentials..."
mkdir -p ~/.docker
if [ ! -f ~/.docker/config.json ]; then
    echo '{"credsStore": ""}' > ~/.docker/config.json
    echo "✅ Created Docker config"
fi
echo ""

# Pull TimescaleDB image
echo "📦 Pulling TimescaleDB image..."
docker pull timescale/timescaledb:latest-pg16 || {
    echo "⚠️  Warning: Could not pull image (may already exist)"
}
echo ""

# Stop and remove existing container if it exists
echo "🧹 Cleaning up old containers..."
docker stop trading_timescaledb 2>/dev/null || true
docker rm trading_timescaledb 2>/dev/null || true
echo ""

# Create data directory
echo "📁 Creating data directory..."
mkdir -p ./data/timescaledb
echo ""

# Start TimescaleDB container
echo "🐳 Starting TimescaleDB container..."
docker run -d \
  --name trading_timescaledb \
  -p 5433:5432 \
  -e POSTGRES_USER=trading_user \
  -e POSTGRES_PASSWORD=trading_pass_change_in_production \
  -e POSTGRES_DB=trading_db \
  -v "$(pwd)/data/timescaledb:/var/lib/postgresql/data" \
  timescale/timescaledb:latest-pg16 \
  postgres \
  -c shared_preload_libraries=timescaledb \
  -c max_connections=200 \
  -c work_mem=16MB

echo "✅ Container started"
echo ""

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL to be ready (30 seconds)..."
for i in {1..30}; do
    if docker exec trading_timescaledb pg_isready -U trading_user > /dev/null 2>&1; then
        echo "✅ PostgreSQL is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Error: PostgreSQL did not start in time"
        echo "Check logs with: docker logs trading_timescaledb"
        exit 1
    fi
    sleep 1
    echo -n "."
done
echo ""
echo ""

# Initialize schema
echo "📊 Initializing OANDA database schema..."
docker exec -i trading_timescaledb psql -U trading_user -d trading_db < scripts/init_oanda_schema.sql
echo "✅ Schema initialized"
echo ""

# Install Python dependencies if needed
echo "🐍 Checking Python dependencies..."
if ! python3 -c "import asyncpg" 2>/dev/null; then
    echo "Installing asyncpg..."
    pip3 install asyncpg
fi
echo "✅ Python dependencies ready"
echo ""

# Run verification
echo "🔍 Running verification tests..."
python3 scripts/verify_db_setup.py

echo ""
echo "============================================"
echo "✨ TimescaleDB setup complete!"
echo "============================================"
echo ""
echo "Connection details:"
echo "  Host: localhost"
echo "  Port: 5433"
echo "  Database: trading_db"
echo "  User: trading_user"
echo "  Password: trading_pass_change_in_production"
echo ""
echo "Next steps:"
echo "  1. Update .env with your OANDA credentials"
echo "  2. Run: python scripts/fetch_initial_data.py"
echo "  3. Start trading!"
echo ""
echo "Useful commands:"
echo "  • Connect: psql -h localhost -p 5433 -U trading_user -d trading_db"
echo "  • Logs: docker logs trading_timescaledb -f"
echo "  • Stop: docker stop trading_timescaledb"
echo "  • Start: docker start trading_timescaledb"
echo ""
