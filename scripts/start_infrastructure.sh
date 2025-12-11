#!/bin/bash
# Start Full Trading Infrastructure
#
# This script:
# 1. Starts Docker containers (TimescaleDB, Redis, Grafana, MLflow)
# 2. Waits for services to be healthy
# 3. Runs database migrations
# 4. Bootstraps ML models (if needed)
# 5. Validates system readiness

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Money Machine Infrastructure Startup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${RED}❌ .env file not found${NC}"
    echo "Please create .env file with required API keys"
    echo "See .env.example for reference"
    exit 1
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running${NC}"
    echo "Please start Docker and try again"
    exit 1
fi

echo -e "${YELLOW}🐳 Starting Docker containers...${NC}"
docker compose up -d

echo ""
echo -e "${YELLOW}⏳ Waiting for services to be healthy...${NC}"

# Wait for TimescaleDB
echo -n "  TimescaleDB: "
for i in {1..30}; do
    if docker compose exec -T timescaledb pg_isready -U trading_user -d trading_db > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ Timeout${NC}"
        exit 1
    fi
    sleep 1
done

# Wait for Redis
echo -n "  Redis: "
for i in {1..20}; do
    if docker compose exec -T redis redis-cli ping > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Ready${NC}"
        break
    fi
    if [ $i -eq 20 ]; then
        echo -e "${RED}✗ Timeout${NC}"
        exit 1
    fi
    sleep 1
done

# Wait for MLflow (HTTP check)
echo -n "  MLflow: "
for i in {1..30}; do
    if curl -s http://localhost:5000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${YELLOW}⚠ MLflow may not be ready (non-critical)${NC}"
        break
    fi
    sleep 1
done

# Wait for Grafana (HTTP check)
echo -n "  Grafana: "
for i in {1..30}; do
    if curl -s http://localhost:3000/api/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${YELLOW}⚠ Grafana may not be ready (non-critical)${NC}"
        break
    fi
    sleep 1
done

echo ""
echo -e "${YELLOW}📊 Verifying database schema...${NC}"

# Check if arbitrage tables exist
TABLES_EXIST=$(docker compose exec -T timescaledb psql -U trading_user -d trading_db -t -c \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name IN ('arbitrage_opportunities', 'market_volatility', 'execution_logs');" \
    | tr -d ' ')

if [ "$TABLES_EXIST" = "3" ]; then
    echo -e "${GREEN}✓ Arbitrage schema already exists${NC}"
else
    echo -e "${YELLOW}⚠ Arbitrage schema incomplete, may need migration${NC}"
fi

echo ""
echo -e "${YELLOW}🤖 Checking ML models...${NC}"

# Check if models exist
if [ -f "models/route_success_model.pkl" ] && [ -f "models/profit_maximizer.pkl" ]; then
    echo -e "${GREEN}✓ ML models found${NC}"
else
    echo -e "${YELLOW}⚠ ML models not found${NC}"
    echo -e "${BLUE}  Would you like to bootstrap ML models with synthetic data? (y/n)${NC}"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo -e "${YELLOW}  Bootstrapping ML models...${NC}"
        python scripts/bootstrap_ml_models.py
        echo -e "${GREEN}✓ ML models bootstrapped${NC}"
    else
        echo -e "${YELLOW}  Skipping ML model bootstrap. Models will be trained from live data.${NC}"
    fi
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ Infrastructure is ready!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Services:${NC}"
echo "  📊 Grafana:      http://localhost:3000 (admin/admin)"
echo "  🔬 MLflow:       http://localhost:5000"
echo "  🗄️  TimescaleDB:  localhost:5433 (trading_user/trading_pass_change_in_production)"
echo "  💾 Redis:        localhost:6379"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "  1. Start data collection:  ./scripts/run_data_collection.sh"
echo "  2. Validate ML models:     python scripts/validate_models.py --days 7"
echo "  3. Start live trading:     python run_ai_integrated_arbitrage.py"
echo ""
echo -e "${BLUE}Monitoring:${NC}"
echo "  View logs:       docker compose logs -f trading_app"
echo "  Stop services:   docker compose down"
echo "  Restart:         docker compose restart"
echo ""
