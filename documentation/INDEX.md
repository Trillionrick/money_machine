# Money Machine Documentation Index

Complete documentation for the crypto arbitrage and flash loan trading system.

## Quick Start

**New users start here:**

- [Quick Start 2025](setup/QUICK_START_2025.md) - Modern setup guide
- [Quick Start AI](setup/QUICK_START_AI.md) - AI-integrated trading setup
- [Quick Start Data Collection](setup/QUICK_START_DATA_COLLECTION.md) - Historical data setup
- [Original Quick Start](setup/QUICKSTART.md) - Basic setup

## Setup & Configuration

- [Broker Setup Guide](setup/BROKER_SETUP_GUIDE.md) - Configure CEX/DEX connections
- [Arbitrage Quick Start](setup/ARBITRAGE_QUICK_START.md) - Get arbitrage system running
- [Setup Complete](setup/SETUP_COMPLETE.md) - Post-setup verification

## Integrations

- [Kraken Integration](integrations/KRAKEN_INTEGRATION.md) - Kraken CEX setup
- [Brokerage Connections](integrations/BROKERAGE_CONNECTIONS.md) - Multi-broker configuration
- [Arbitrage Integration Complete](integrations/ARBITRAGE_INTEGRATION_COMPLETE.md) - CEX-DEX integration
- [2025 Integration Summary](integrations/2025_INTEGRATION_SUMMARY.md) - Modern integration patterns
- [Mainnet Config Reference](integrations/MAINNET_CONFIG_REFERENCE.md) - Production configuration

## AI System

- [AI System Guide](ai/AI_SYSTEM_GUIDE.md) - Overview of AI decision system
- [AI Integrated System Guide](ai/AI_INTEGRATED_SYSTEM_GUIDE.md) - End-to-end AI integration
- [AI Dashboard Integration](ai/AI_DASHBOARD_INTEGRATION.md) - Dashboard AI features
- [AI Dashboard Ready](ai/AI_DASHBOARD_READY.md) - AI dashboard deployment
- [AI Decider](ai/AI_DECIDER.md) - Decision engine architecture
- [Aqua AI Trader Guide](ai/AQUA_AI_TRADER_GUIDE.md) - Aqua Protocol AI trading
- [Dashboard AI On-Chain Integration](ai/DASHBOARD_AI_ONCHAIN_INTEGRATION.md) - On-chain AI features

## Features & Trading

- [Flash Loan Guide](features/FLASH_LOAN_GUIDE.md) - Aave V3 flash loan execution
- [Adding Token Pairs](features/ADDING_TOKEN_PAIRS.md) - Add new trading pairs
- [Advanced Arbitrage Strategies](features/ADVANCED_ARBITRAGE_STRATEGIES.md) - Multi-step arbitrage
- [SSE Streaming Guide](features/SSE_STREAMING_GUIDE.md) - Real-time data streaming
- [Data Collection Guide](features/DATA_COLLECTION_GUIDE.md) - Historical data collection
- [TimescaleDB Setup](features/TIMESCALEDB_SETUP.md) - Time-series database

## Architecture

- [Modern Broker Architecture](architecture/MODERN_BROKER_ARCHITECTURE.md) - Broker adapter patterns
- [System Comparison](architecture/SYSTEM_COMPARISON.md) - Design tradeoffs
- [Project Summary](architecture/PROJECT_SUMMARY.md) - High-level overview
- [Your Actual Edge](architecture/YOUR_ACTUAL_EDGE.md) - Trading philosophy

## User Guides

- [Crypto Trading Guide](guides/CRYPTO_TRADING_GUIDE.md) - Trading fundamentals
- [Crypto Update Summary](guides/CRYPTO_UPDATE_SUMMARY.md) - Recent crypto changes
- [UI Guide](guides/UI_GUIDE.md) - Dashboard usage
- [What's New SSE](guides/WHATS_NEW_SSE.md) - SSE streaming benefits
- [Implementation Guide](guides/IMPLEMENTATION_GUIDE.md) - Development guide

## Updates & Changes

- [Arbitrage Fixes 2025](updates/ARBITRAGE_FIXES_2025.md) - Recent arbitrage improvements
- [Quick Update](updates/QUICK_UPDATE.md) - Latest changes
- [Improvements Applied](updates/IMPROVEMENTS_APPLIED.md) - Applied enhancements
- [Improvements Summary](updates/IMPROVEMENTS_SUMMARY.md) - Improvement overview
- [Enhancement Plan](updates/ENHANCEMENT_PLAN.md) - Planned enhancements
- [Hybrid Enhancements](updates/HYBRID_ENHANCEMENTS.md) - Hybrid trading features

## Reference Documentation

### Specific Features

- [1inch Portfolio V5 Guide](1INCH_PORTFOLIO_V5_GUIDE.md) - 1inch portfolio API
- [Subgraph API](arbitrage/subgraph API.txt) - GraphQL subgraph queries

### Operational Guides

- [Kill and Restart Server](KILL AND RESTART SERVER.txt) - Process management
- [Quick Restart Commands](Quick Restart Commands.txt) - Common restart commands

### Platform Guides

- [Where to Find Things in 1inch Portal](Where to Find Things in 1inch Portal.txt) - 1inch UI navigation
- [Deploy Using Remix IDE](arbitrage/Deploy Using Remix IDE.txt) - Smart contract deployment

### Daily Operations

- [Daily Activities](arbitrage/Daily Activities/) - Daily operational procedures
- [Dashboard Settings 11-29-2025](arbitrage/DASHBOARD_SETTINGS_11-29-2025.txt) - Current config

### Educational

- [Maximal Extractable Value](maximal extractable value.txt) - MEV concepts
- [Creating Zip Files](creating zip files.txt) - Archive management
- [What You Have Built](arbitrage/✅ What You Have Built.txt) - System capabilities
- [Aqua Protocol - Complete Guide](arbitrage/🌊 Aqua Protocol - Complete Guide.txt) - Aqua integration

### AI/ML

- [Complete AI System Implementation](Complete AI System Implementation.txt) - Full AI implementation
- [AI ML Documentation](AI ML/) - AI/ML specific docs

### Flash Loans

- [Gas Cap](Flashloans/Gas cap.txt) - Gas optimization for flash loans

## API Documentation

Auto-generated API docs available at `/docs` when running the dashboard server.

## Project Structure

```
money_machine/
├── src/               # Python source code
│   ├── ai/           # AI decision systems
│   ├── api/          # FastAPI endpoints
│   ├── brokers/      # CEX integrations
│   ├── core/         # Core trading logic
│   ├── dex/          # DEX connectors
│   ├── live/         # Live trading engines
│   ├── ml/           # Machine learning features
│   ├── portfolio/    # Portfolio tracking
│   └── research/     # Backtesting & analytics
├── contracts/        # Solidity smart contracts
├── documentation/    # This documentation
├── examples/         # Usage examples
├── tests/            # Test suite
└── web_*.py/html    # Dashboard UI
```

## Support & Resources

- Main README: [README.md](../README.md)
- AI Assistant Context: [CLAUDE.md](../CLAUDE.md)
- Example Code: [examples/](../examples/)

## Development

Start the dashboard:
```bash
./start_dashboard.sh
```

Run tests:
```bash
pytest tests/ -v
```

Check health:
```bash
python health_check.py
```
