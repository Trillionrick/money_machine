# Money Machine - Crypto Arbitrage & Flash Loan System

## System Architecture

### Core Purpose
Multi-chain arbitrage detection and execution system with flash loan integration, targeting CEX-DEX price discrepancies across Ethereum and Polygon networks.

### Technology Stack
- **Backend**: Python 3.11+ (async/await patterns, structured concurrency)
- **Web3**: web3.py, eth-abi for smart contract interactions
- **API Integrations**: 
  - CEX: Kraken, Bybit, Coinbase, Alpaca (primary)
  - DEX: Uniswap V3, QuickSwap V3, 1inch aggregator
  - RPC: Alchemy, Polygon Official, Matic Network (with failover)
- **Frontend**: FastAPI + WebSocket (Uvicorn), real-time dashboard
- **Data**: Polars (not Pandas), NumPy for simulations
- **Logging**: structlog for structured JSON logs

### Key Components

#### 1. Price Fetching (`src/core/price_fetcher.py`)
- Multi-source price aggregation with failover
- Inverse pair calculation for synthetic prices
- CoinGecko fallback for illiquid pairs
- Uses Kraken as primary CEX for crypto prices

#### 2. Arbitrage Detection (`src/core/arbitrage.py`)
- Real-time CEX-DEX spread monitoring
- Configurable minimum edge thresholds (basis points)
- Gas cost estimation and profitability checks
- Dry-run mode for testing

#### 3. Flash Loan Execution (`src/core/flash_loan_executor.py`)
- Aave V3 flash loan integration
- Multi-step arbitrage execution in single transaction
- Slippage protection and MEV considerations
- Contract address: `0x8d2DF8b754154A3c16338353Ad9f7875B210D9B0`

#### 4. RPC Failover (`src/core/rpc_failover.py`)
- Circuit breaker pattern implementation
- Health scoring and automatic endpoint rotation
- Exponential backoff with jitter
- Currently experiencing 1inch API 500 errors (2024-12-02)

#### 5. Gas Oracle (`src/core/gas_oracle.py`)
- Multi-confidence level estimation
- Caching with TTL to minimize RPC calls
- Supports Ethereum mainnet and Polygon

#### 6. Dashboard (`src/api/dashboard.py`)
- WebSocket real-time updates
- Configuration management API
- Event streaming for arbitrage opportunities
- Runs on `http://localhost:8080`

### Trading Pairs
Primary focus on high-liquidity pairs:
```
ETH/USDC, WETH/USDC, ETH/USDT, BTC/USDT, WBTC/USDC, 
USDT/USDC, DAI/USDC, LINK/USDC, LINK/ETH, UNI/USDC,
AAVE/USDC, GRT/USDC, MATIC/USDC, SHIB/USDC, LDO/USDC, APE/USDC
```

### Configuration

#### Wallet Addresses
- **Metamask**: `0x31fcd43a349ada21f3c5df51d66f399be518a912`
- **Rainbow**: `0x21E722833CE4C3e8CE68F14D159456744402b48C`

#### RPC Endpoints
- **Ethereum**: `https://eth-mainnet.g.alchemy.com/v2/vZuXI4mrngK8K5m-FyIQ0`
- **Polygon**: `https://polygon-mainnet.g.alchemy.com/v2/vZuXI4mrngK8K5m-FyIQ0` (chain 137)

#### Environment Variables Required
```bash
ALCHEMY_API_KEY=<redacted>
KRAKEN_API_KEY=<required>
KRAKEN_API_SECRET=<required>
ALPACA_API_KEY=<required>
ALPACA_API_SECRET=<required>
WALLET_PRIVATE_KEY=<required-for-execution>
```

## Development Standards (2025)

### Code Style
- **Type hints**: Mandatory for all functions (use `dict[str, float]`, not `Dict`)
- **Async patterns**: Use `asyncio` for I/O-bound operations
- **Error handling**: Explicit exception types, structured logging
- **No deprecated code**: Remove all pre-2024 patterns

### Common Issues & Solutions

#### 1. 1inch API 500 Errors
**Current Status**: All Polygon 1inch endpoints failing (as of 2024-12-02)
**Workaround**: System falls back to direct Uniswap V3 quotes
**TODO**: Implement 0x API as secondary aggregator

#### 2. Type Checking (Pylance)
- Use explicit type annotations on all variables
- Prefer `dict[K, V] | None` over `Optional[Dict[K, V]]`
- Never use unparameterized `dict` as return type

#### 3. Kraken Rate Limits
- Built-in tier-aware rate limiting (Starter: 15/sec)
- Uses `ccxt` with retry logic
- Some pairs unavailable (MATIC/ETH, GRT/ETH, etc.) - use CoinGecko

## Development Workflows

### Starting the System
```bash
./start_dashboard.sh  # Launches dashboard on port 8080
```

### Running Tests
```bash
pytest tests/ -v --asyncio-mode=auto
```

### Monitoring Logs
```bash
tail -f logs/arbitrage.log | jq .  # Pretty-print structured logs
```

### Common Tasks

#### Add New Trading Pair
1. Update `SUPPORTED_SYMBOLS` in `src/core/arbitrage.py`
2. Verify pair availability on Kraken/Alpaca
3. Add token address to `TOKEN_ADDRESSES` dict
4. Test with dry-run mode

#### Modify Profit Threshold
Edit `config/arbitrage_config.json`:
```json
{
  "min_profit_bps": 50,  // 0.5% minimum edge
  "max_slippage_bps": 30,
  "gas_buffer_multiplier": 1.5
}
```

#### Debug RPC Issues
```python
from src.core.rpc_failover import PolygonRPCManager

manager = PolygonRPCManager()
status = await manager.get_health_status()
# Check circuit_state, health_scores, consecutive_failures
```

## Critical Constraints

### Safety Mechanisms
1. **Dry-run mode**: Default is `True` - no real transactions
2. **Gas estimation**: Always simulate before execution
3. **Slippage protection**: Max 0.3% configured
4. **Circuit breakers**: Auto-disable failing RPC endpoints

### Known Limitations
- **1inch reliability**: Currently experiencing service degradation
- **Flash loan gas costs**: ~300k gas units minimum
- **MEV vulnerability**: Transactions visible in mempool (TODO: Flashbots integration)

### Performance Targets
- Price fetch latency: <200ms (95th percentile)
- Arbitrage detection cycle: <5s full scan
- WebSocket update frequency: Real-time on opportunity detection

## Target Optimization Module

### Purpose
Implements aggressive position sizing for wealth target optimization (opposite of Kelly criterion).

**Key Insight**: When you have a specific wealth target and can afford multiple attempts, optimal strategy accepts higher ruin risk to maximize P(hitting target).

### Components
- `TargetObjective`: Defines current → target wealth path
- `TargetOptimizer`: Calculates optimal leverage (often 2-5x Kelly)
- Monte Carlo simulation: 10k+ paths for probability estimation

### Usage Context
Used for calculating position sizes in high-conviction arbitrage setups where:
- Edge is validated and persistent
- Multiple attempts possible (can reset capital)
- Target wealth justifies aggressive allocation

**Warning**: This is mathematically correct but psychologically brutal. Most users cannot handle the variance.

## Next Development Priorities

### High Priority
1. ✅ Fix type hints in `target_optimizer.py` 
2. 🔄 Implement 0x API as 1inch backup
3. 🔄 Add Flashbots RPC for MEV protection
4. ⏳ Integrate historical arbitrage opportunity database

### Medium Priority
- Cross-chain arbitrage (Ethereum ↔ Polygon bridge opportunities)
- Automated profit tracking and tax reporting
- Dynamic gas price bidding for time-sensitive opportunities
- Telegram/Discord alerts for high-value opportunities

### Research/Experimental
- DeepSeek reasoning model for market regime detection
- Uniswap V4 hook integration (when mainnet launches)
- Governance token staking for fee discounts (UNI, AAVE)

## Debugging Commands

### Check System Status
```python
# In Python REPL
from src.core.arbitrage import ArbitrageSystem
system = ArbitrageSystem()
await system.initialize()
print(system.get_status())
```

### Simulate Single Opportunity
```python
opportunity = {
    "symbol": "ETH/USDC",
    "cex_price": 3054.05,
    "dex_price": 3050.98,
    "edge_bps": 10.0,
}
result = await system.simulate_arbitrage(opportunity)
```

### Force RPC Endpoint Reset
```python
from src.core.rpc_failover import PolygonRPCManager
manager = PolygonRPCManager()
await manager.reset_all_circuits()
```

## File Structure
```
money_machine/
├── src/
│   ├── core/           # Core trading logic
│   ├── api/            # Dashboard API
│   └── utils/          # Helpers
├── config/             # Configuration files
├── contracts/          # Solidity smart contracts
├── tests/              # Test suite
├── logs/               # Structured logs
└── start_dashboard.sh  # Startup script
```

## Important Notes for AI Assistants

1. **Never use deprecated libraries**: Check PyPI for latest stable versions
2. **Type hints are mandatory**: Unparameterized generics cause Pylance errors
3. **Async everywhere**: This is I/O-bound code, use async/await patterns
4. **Structured logging only**: Use `structlog`, never plain `print()`
5. **Gas costs matter**: Always estimate and validate profitability
6. **Test in dry-run first**: Real money is at stake

## Contact & Resources

- **Project Owner**: Richard (advanced technical user, prefers direct communication)
- **Communication Style**: No excessive formatting, avoid lists unless necessary
- **Technical Level**: Expects 2025 best practices, production-ready implementations
- **Documentation**: Prefer mechanistic explanations over simplified overviews
