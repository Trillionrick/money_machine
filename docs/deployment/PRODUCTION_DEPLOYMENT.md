# Production Deployment Guide

This guide covers the complete setup for transitioning from simulation to live trading.

## Prerequisites

1. **System Requirements**
   - Docker & Docker Compose
   - Python 3.11+
   - At least 8GB RAM
   - 20GB+ free disk space

2. **API Keys Required**
   - Alchemy API key (Ethereum/Polygon RPC)
   - Kraken API key + secret
   - Alpaca API key + secret
   - Wallet private key (for live trading)

3. **Recommended Setup Period**
   - **2 weeks minimum** of dry-run data collection before live trading
   - This allows ML models to learn from real market conditions

## Architecture Overview

### New Components Added

1. **TimescaleDB** - Time-series database for:
   - Arbitrage opportunity tracking
   - Market volatility metrics
   - Execution logs
   - ML model performance tracking

2. **MLflow** - ML model versioning and tracking:
   - Automatic version tagging with timestamps
   - Model performance metrics
   - Model lineage tracking
   - A/B testing support

3. **Grafana** - Real-time monitoring:
   - Opportunity detection rates
   - Win rates and profitability
   - System health metrics
   - Circuit breaker status

4. **Redis** - Caching and pub/sub:
   - Price caching
   - RPC call deduplication
   - Event streaming

### New AI/ML Features

1. **Market Data Collector** (`src/ai/market_data.py`)
   - Real-time volatility calculation (1h, 24h, 7d windows)
   - Historical price tracking
   - Volume and liquidity metrics

2. **Circuit Breakers** (`src/ai/circuit_breakers.py`)
   - Win rate monitoring (min 40%)
   - Drawdown protection (max 15%)
   - Gas cost limits (max 40% of profit)
   - Consecutive failure tracking (max 5)
   - Volatility spike detection
   - Anomalous slippage detection

3. **Model Versioning** (`src/ai/model_versioning.py`)
   - Automatic version tagging
   - Git commit tracking
   - Model comparison tools
   - Rollback capabilities

## Step-by-Step Deployment

### 1. Environment Setup

Create `.env` file in project root:

```bash
# RPC Endpoints
ALCHEMY_API_KEY=your_alchemy_key_here

# CEX API Keys
KRAKEN_API_KEY=your_kraken_key
KRAKEN_API_SECRET=your_kraken_secret
ALPACA_API_KEY=your_alpaca_key
ALPACA_API_SECRET=your_alpaca_secret

# Wallet (DO NOT COMMIT)
WALLET_PRIVATE_KEY=your_private_key_here

# Database
TIMESCALE_HOST=localhost
TIMESCALE_PORT=5433
TIMESCALE_USER=trading_user
TIMESCALE_PASSWORD=trading_pass_change_in_production
TIMESCALE_DB=trading_db

# MLflow
MLFLOW_TRACKING_URI=http://localhost:5000

# Redis
REDIS_URL=redis://localhost:6379/0
```

### 2. Start Infrastructure

```bash
# Make scripts executable
chmod +x scripts/*.sh

# Start all infrastructure
./scripts/start_infrastructure.sh
```

This will:
- Start Docker containers (TimescaleDB, Redis, Grafana, MLflow)
- Wait for services to be healthy
- Verify database schema
- Optionally bootstrap ML models with synthetic data

**Services will be available at:**
- Grafana: http://localhost:3000 (admin/admin)
- MLflow: http://localhost:5000
- TimescaleDB: localhost:5433
- Redis: localhost:6379

### 3. Start Data Collection (Dry-Run)

**CRITICAL: Run this for at least 2 weeks before live trading**

```bash
./scripts/run_data_collection.sh
```

This runs the arbitrage system in dry-run mode to:
- Detect arbitrage opportunities
- Calculate volatility metrics
- Log execution simulations
- Train ML models on real market data
- Build statistical baselines

**Monitoring data collection:**
```bash
# View real-time logs
tail -f logs/data_collection.log

# Check database
psql -h localhost -p 5433 -U trading_user -d trading_db
\dt  # List tables
SELECT COUNT(*) FROM arbitrage_opportunities;
```

### 4. Validate ML Models

After collecting data for 7+ days:

```bash
# Validate model performance
python scripts/validate_models.py --days 7 --save-report

# View validation report
cat logs/model_validation.txt
```

**Expected Metrics (after 2 weeks):**
- Route Success Predictor:
  - Accuracy: 60-70%
  - Precision: 55-65%
  - F1 Score: 0.55-0.65

- Profit Maximizer:
  - MAE: $5-15
  - Correlation: 0.6-0.8
  - Mean % Error: 10-25%

- Slippage Predictor:
  - MAE: 5-15 bps
  - Correlation: 0.5-0.7

### 5. Monitor Performance

**Grafana Dashboard:**
1. Go to http://localhost:3000
2. Login (admin/admin)
3. Dashboard automatically loaded: "Arbitrage Monitoring"

**Key Metrics to Watch:**
- Opportunities detected per hour (target: 10+)
- Win rate (target: 55-65%)
- Average edge (target: 30+ bps)
- Circuit breaker status (all should be CLOSED)

**MLflow:**
1. Go to http://localhost:5000
2. View experiments: `arbitrage_route_success_predictor`, `arbitrage_profit_maximizer`
3. Compare model versions
4. Track performance over time

### 6. Production Checklist

Before enabling live trading:

- [ ] Collected 2+ weeks of dry-run data
- [ ] ML models validated (accuracy > 55%)
- [ ] Win rate > 50% in simulations
- [ ] Average profit per trade > gas costs
- [ ] Circuit breakers tested and verified
- [ ] Grafana dashboard showing healthy metrics
- [ ] Wallet funded with:
  - [ ] Ethereum for gas (0.1+ ETH)
  - [ ] Trading capital ($5,000+ recommended)
- [ ] Backup of wallet private key stored securely
- [ ] Alert notifications configured (optional)

### 7. Enable Live Trading

**Start with micro-capital to validate:**

```bash
# Edit config to enable live trading
# In run_ai_integrated_arbitrage.py, set:
# DRY_RUN = False
# MAX_TRADE_SIZE = 100  # Start small!

# Run with live trading enabled
python run_ai_integrated_arbitrage.py
```

**Monitor closely for first 24 hours:**
- Check every transaction on Etherscan/Polygonscan
- Verify profit calculations match reality
- Watch for slippage anomalies
- Ensure circuit breakers trigger appropriately

**Gradually increase capital:**
- Week 1: $100-500 per trade
- Week 2-3: $500-2000 per trade
- Month 2+: $2000-10000 per trade (if profitable)

## Circuit Breaker Reference

The system will automatically halt trading if:

1. **Win Rate Drop** - Falls below 40% (over last 20 trades)
2. **Drawdown** - Exceeds 15% from peak
3. **Gas Costs** - Exceed 40% of gross profit
4. **Consecutive Failures** - 5 or more failed trades in a row
5. **Volatility Spike** - 3x normal volatility detected
6. **Execution Failures** - 80%+ failure rate in 15min window
7. **Anomalous Slippage** - 2.5+ std deviations from expected

**Viewing Circuit Breaker Status:**
```python
from src.ai.circuit_breakers import get_circuit_breaker_manager

manager = get_circuit_breaker_manager()
status = manager.get_status()
print(status)
```

**Manual Recovery:**
```python
# After fixing issues, attempt recovery
manager.attempt_recovery(CircuitBreakerType.WIN_RATE)
```

## Database Schema

### Key Tables

**arbitrage_opportunities** - All detected opportunities
```sql
SELECT symbol, edge_bps, executed, profitable, profit_quote
FROM arbitrage_opportunities
WHERE timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp DESC;
```

**market_volatility** - Real-time volatility metrics
```sql
SELECT symbol, volatility_24h, returns_1h, volume_24h
FROM market_volatility
WHERE timestamp > NOW() - INTERVAL '1 hour'
ORDER BY timestamp DESC;
```

**execution_logs** - Trade execution records
```sql
SELECT symbol, success, profit_usd, gas_cost_usd, tx_hash
FROM execution_logs
WHERE timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp DESC;
```

**model_performance** - ML model metrics
```sql
SELECT model_name, accuracy, avg_actual_profit, timestamp
FROM model_performance
ORDER BY timestamp DESC
LIMIT 10;
```

### Continuous Aggregates

**ml_training_data** - Materialized view for ML training
**hourly_performance** - Hourly profitability stats
**daily_profitability** - Daily P&L summary

## Troubleshooting

### Issue: No opportunities detected
```bash
# Check price fetching
python -c "from src.core.price_fetcher import MultiSourcePriceFetcher; import asyncio; pf = MultiSourcePriceFetcher(); asyncio.run(pf.fetch_price('ETH/USDC'))"

# Check RPC connectivity
python -c "from src.dex.web3_connector import Web3Connector; w3 = Web3Connector(); print(w3.is_connected())"
```

### Issue: Database connection failed
```bash
# Check TimescaleDB status
docker-compose ps timescaledb

# View logs
docker-compose logs timescaledb

# Restart database
docker-compose restart timescaledb
```

### Issue: ML models not training
```bash
# Check training data availability
psql -h localhost -p 5433 -U trading_user -d trading_db -c "SELECT COUNT(*) FROM arbitrage_opportunities WHERE executed = TRUE"

# Should have 50+ executed trades for initial training

# Manually trigger training
python scripts/bootstrap_ml_models.py
```

### Issue: Circuit breakers stuck OPEN
```python
from src.ai.circuit_breakers import get_circuit_breaker_manager

manager = get_circuit_breaker_manager()

# View detailed status
print(manager.get_status())

# Reset ALL breakers (use with caution!)
manager.reset_all()
```

## Performance Optimization

### Database Tuning
```sql
-- Add indexes for common queries
CREATE INDEX IF NOT EXISTS idx_arb_profitable_time
ON arbitrage_opportunities (profitable, timestamp DESC)
WHERE executed = TRUE;

-- Vacuum regularly
VACUUM ANALYZE arbitrage_opportunities;
```

### RPC Rate Limiting
```python
# In src/core/rpc_failover.py
# Adjust rate limits based on Alchemy tier
RATE_LIMITS = {
    "ethereum": 300,  # requests per second
    "polygon": 300,
}
```

### Model Retraining Frequency
```python
# In src/ai/profit_maximizer.py
ml_retrain_frequency = 25  # Retrain every N trades (default)
# Increase for stability, decrease for faster adaptation
```

## Expected Outcomes

### Conservative Estimates (After 2 months)

**Performance Metrics:**
- Win rate: 55-65%
- Average profit per trade: 15-30 bps (after costs)
- Sharpe ratio: 1.2-1.8
- Max drawdown: 10-20%
- Expected monthly return: 5-15% (highly variable)

**Capital Requirements:**
- Minimum: $5,000 (meaningful results)
- Recommended: $10,000-25,000 (proper diversification)
- Flash loan buffer: $0 (borrowed capital)
- Gas reserve: $500-1000 ETH for transaction fees

**Execution Stats:**
- Opportunities per day: 20-100
- Trades executed per day: 5-20
- Average trade size: $2,000-10,000
- Gas cost per trade: $10-50 (Ethereum), $0.50-2 (Polygon)

## Advanced Features

### Model Version Comparison
```python
from src.ai.model_versioning import get_model_version_manager

manager = get_model_version_manager()

# List all versions
versions = manager.list_versions("route_success_predictor")

# Compare two versions
comparison = manager.compare_versions(
    "route_success_predictor",
    "20250105_143022",
    "20250108_091534"
)
print(comparison)
```

### Custom Dashboards

Add custom Grafana queries:
```sql
-- Win rate by symbol
SELECT
    symbol,
    CAST(COUNT(*) FILTER (WHERE profitable = TRUE) AS FLOAT) /
    NULLIF(COUNT(*) FILTER (WHERE executed = TRUE), 0) as win_rate
FROM arbitrage_opportunities
WHERE executed = TRUE
GROUP BY symbol
ORDER BY win_rate DESC;

-- Hourly profit
SELECT
    time_bucket('1 hour', timestamp) AS hour,
    SUM(profit_quote) as total_profit
FROM arbitrage_opportunities
WHERE executed = TRUE AND profitable = TRUE
GROUP BY hour
ORDER BY hour DESC;
```

### Volatility-Based Position Sizing
```python
from src.ai.market_data import get_market_data_collector

collector = get_market_data_collector()
vol_metrics = await collector.get_latest_volatility("ETH/USDC", "ethereum")

# Reduce position size in high volatility
if vol_metrics.volatility_24h > 0.50:  # 50% annualized
    position_multiplier = 0.5
else:
    position_multiplier = 1.0
```

## Support & Resources

- **Documentation**: See CLAUDE.md for system architecture
- **Model Details**: See documentation/ML models integrated.txt
- **Issues**: Check logs in `logs/` directory
- **Database**: `psql -h localhost -p 5433 -U trading_user -d trading_db`

## Security Reminders

1. **NEVER commit private keys to git**
2. **Change database password** from default
3. **Use hardware wallet** for large capital
4. **Enable 2FA** on all CEX accounts
5. **Monitor wallet** for suspicious activity
6. **Regular backups** of database and ML models
7. **Test recovery procedures** before needed

---

**The system is ready. The ML pipeline is solid. The missing piece is real-world data validation. Start collecting data TODAY, validate models in 2 weeks, deploy micro-capital in 4 weeks. This is the path to production.**
