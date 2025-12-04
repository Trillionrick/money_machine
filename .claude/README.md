# Claude Code Configuration

Optimized commands for crypto arbitrage system workflows.

## Available Commands

### System Health & Monitoring
- `/status` - Comprehensive health check (RPC, CEX, DEX, gas oracle)
- `/env-check` - Validate .env configuration
- `/rpc-health` - Check RPC failover circuit breaker status
- `/logs` - Analyze recent arbitrage logs

### Trading Operations
- `/arb-scan` - Execute single dry-run arbitrage scan
- `/calc-profit` - Calculate profitability for specific opportunity
- `/flash-sim` - Simulate flash loan arbitrage execution
- `/monitor` - Start live monitoring (no execution)

### Position Sizing
- `/target-size` - Calculate optimal leverage using target optimizer

### Development
- `/fix-types` - Update to Python 3.11+ type hint syntax
- `/test-runner` - Run pytest suite
- `/gas-history` - Analyze gas price trends
- `/debug-trade` - Debug specific trade execution

### Configuration
- `/add-pair` - Add new trading pair to system

## Permissions

Pre-approved commands (no confirmation required):
- Python execution (`python`, `python3`)
- Package management (`pip`, `pytest`)
- Type checking (`mypy`, `pylint`, `black`)
- System utilities (`ls`, `ps`, `kill`, `curl`, `jq`)
- Git operations
- Dashboard scripts (`./start_dashboard.sh`, `./run_live_arbitrage.py`)

## Notes

All commands assume:
- Virtual environment activated (`.venv`)
- `.env` file configured with API keys
- DRY_RUN mode enabled by default

Use `/status` first on new sessions to verify system health.
