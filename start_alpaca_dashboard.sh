#!/bin/bash
# Alpaca Trading Dashboard Startup Script
# Starts the Alpaca trading dashboard on port 8081

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================================================${NC}"
echo -e "${GREEN}         📈 Starting Alpaca Trading Dashboard${NC}"
echo -e "${BLUE}================================================================${NC}"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}Warning: .env file not found${NC}"
    echo "Creating .env from .env.example..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "${GREEN}.env file created. Please configure your API keys.${NC}"
    else
        echo -e "${YELLOW}No .env.example found. Please create .env manually.${NC}"
    fi
fi

# Load environment variables
if [ -f .env ]; then
    # Better .env parsing - filter comments and empty lines
    set -a
    source <(cat .env | grep -v '^#' | grep -v '^$' | grep '=')
    set +a
    echo -e "${GREEN}✓ Environment variables loaded${NC}"
fi

# Check if Alpaca credentials are set (dual-key system)
PAPER_KEYS_SET=false
LIVE_KEYS_SET=false

if [ -n "$ALPACA_PAPER_API_KEY" ] && [ -n "$ALPACA_PAPER_API_SECRET" ]; then
    PAPER_KEYS_SET=true
fi

if [ -n "$ALPACA_LIVE_API_KEY" ] && [ -n "$ALPACA_LIVE_API_SECRET" ]; then
    if [[ ! "$ALPACA_LIVE_API_KEY" =~ ^your_ ]]; then
        LIVE_KEYS_SET=true
    fi
fi

if [ "$PAPER_KEYS_SET" = false ] && [ "$LIVE_KEYS_SET" = false ]; then
    echo -e "${YELLOW}⚠️  Warning: No valid Alpaca credentials found${NC}"
    echo "Please set paper or live API keys in .env:"
    echo "  ALPACA_PAPER_API_KEY and ALPACA_PAPER_API_SECRET"
    echo "  ALPACA_LIVE_API_KEY and ALPACA_LIVE_API_SECRET"
    echo ""
fi

# Check paper trading mode
if [ "${ALPACA_PAPER:-true}" = "true" ]; then
    echo -e "${GREEN}Default Mode: PAPER TRADING (Safe)${NC}"
    if [ "$PAPER_KEYS_SET" = false ]; then
        echo -e "${YELLOW}  ⚠️  Paper keys not configured - get keys from alpaca.markets${NC}"
    fi
else
    echo -e "${YELLOW}Default Mode: LIVE TRADING (Real Money!)${NC}"
    if [ "$LIVE_KEYS_SET" = false ]; then
        echo -e "${YELLOW}  ⚠️  Live keys not configured - will fall back to paper${NC}"
    fi
fi

echo ""
echo -e "${GREEN}💡 You can switch between Paper and Live modes in the dashboard${NC}"
echo ""
echo -e "${BLUE}Starting server on http://localhost:8081${NC}"
echo -e "${BLUE}Press Ctrl+C to stop${NC}"
echo ""

# Start the Alpaca server using virtual environment
if [ -d ".venv" ]; then
    .venv/bin/python alpaca_server.py
else
    python3 alpaca_server.py
fi
