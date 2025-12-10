# Dashboard Configuration Guide

Your dashboard is now fully integrated with all production features: circuit breakers, model versioning, market volatility tracking, and TimescaleDB data.

## Available Dashboards

### 1. Production Dashboard (New!) 🚀
**URL:** http://localhost:8080/

The comprehensive production monitoring dashboard with:
- **System Health** - Real-time health of all components
- **Circuit Breakers** - Status and manual controls
- **ML Models** - Version info and training metrics
- **Performance Stats** - 24h rolling metrics
- **Market Volatility** - Real-time volatility tracking
- **Recent Opportunities** - Latest arbitrage detections

**Features:**
- Auto-refresh every 30 seconds
- Circuit breaker controls (reset, recovery)
- Model version comparison
- Live volatility tracking
- Dark theme optimized for trading

### 2. Classic Dashboard
**URL:** http://localhost:8080/classic

The original dashboard (preserved for compatibility)

### 3. Grafana Dashboard
**URL:** http://localhost:3000 (admin/admin)

Pre-configured time-series dashboards with:
- Opportunities over time
- Win rate trends
- Symbol breakdown
- Profit tracking

### 4. MLflow Dashboard
**URL:** http://localhost:5000

ML model tracking and versioning:
- Experiment tracking
- Model comparison
- Performance metrics
- Artifact management

## API Endpoints Reference

### Production System Endpoints

#### Circuit Breakers
```bash
# Get circuit breaker status
curl http://localhost:8080/api/production/circuit-breakers/status

# Reset all circuit breakers (USE WITH CAUTION)
curl -X POST http://localhost:8080/api/production/circuit-breakers/control \
  -H "Content-Type: application/json" \
  -d '{"action": "reset_all"}'

# Attempt recovery on specific breaker
curl -X POST http://localhost:8080/api/production/circuit-breakers/control \
  -H "Content-Type: application/json" \
  -d '{"action": "attempt_recovery", "breaker_type": "win_rate"}'
```

#### Model Versioning
```bash
# Get current model status
curl http://localhost:8080/api/production/models/current

# List model versions
curl "http://localhost:8080/api/production/models/versions?model_name=route_success_model&limit=10"

# Compare two versions
curl "http://localhost:8080/api/production/models/compare?model_name=route_success_model&version1=20250105_143022&version2=20250108_091534"
```

#### Market Volatility
```bash
# Get current volatility for symbols
curl "http://localhost:8080/api/production/volatility/current?symbols=ETH/USDC,WETH/USDC&chain=ethereum"
```

#### Database Queries
```bash
# Get recent opportunities
curl "http://localhost:8080/api/production/opportunities/recent?hours=1&limit=50"

# Get opportunity statistics
curl "http://localhost:8080/api/production/opportunities/stats?hours=24"

# Get hourly performance
curl "http://localhost:8080/api/production/performance/hourly?hours=24"
```

#### System Health
```bash
# Comprehensive health check
curl http://localhost:8080/api/production/health
```

### AI System Endpoints (Existing)

```bash
# AI system status
curl http://localhost:8080/api/ai/status

# AI metrics
curl http://localhost:8080/api/ai/metrics

# Recent performance (custom window)
curl "http://localhost:8080/api/ai/metrics/recent?window_minutes=60"

# AI configuration
curl http://localhost:8080/api/ai/config
```

### AI On-Chain Endpoints

```bash
# On-chain AI status
curl http://localhost:8080/api/ai/onchain/status

# Profitability metrics
curl http://localhost:8080/api/ai/onchain/profitability

# ML decision metrics
curl http://localhost:8080/api/ai/onchain/ml-decisions
```

## Starting the Dashboard

### Quick Start
```bash
# Start all infrastructure first
./scripts/start_infrastructure.sh

# Start the dashboard
./start_dashboard.sh
```

### Manual Start
```bash
# Activate venv
source .venv/bin/activate

# Set PYTHONPATH
export PYTHONPATH=$PWD

# Start with uvicorn
uvicorn web_server:app --host 127.0.0.1 --port 8080 --reload
```

### Production Start (Docker)
```bash
# Infrastructure already includes the app
docker-compose up -d

# Dashboard available at http://localhost:8080
```

## Dashboard Features Walkthrough

### 1. System Health Card
Shows real-time status of:
- **Circuit Breakers** - All breakers functional?
- **Database** - TimescaleDB connected?
- **ML Models** - Models loaded?

**Status Indicators:**
- 🟢 Healthy - All systems operational
- 🟡 Warning - Non-critical issues
- 🔴 Error - Critical component down

### 2. Performance Card (24h)
Key metrics at a glance:
- **Opportunities** - Total detected in 24h
- **Win Rate** - Percentage of profitable trades
- **Total Profit** - Gross profit (excludes gas)
- **Avg Edge** - Average arbitrage spread

### 3. ML Models Card
Current model status:
- Model name
- Training samples
- Version timestamp
- Metrics (if available)

### 4. Circuit Breakers Panel
Visual representation of all safety mechanisms:

**Breaker Types:**
- 🟢 **Win Rate** - Monitors profitability (min 40%)
- 🟢 **Drawdown** - Protects capital (max 15%)
- 🟢 **Gas Cost** - Prevents excessive fees (max 40% of profit)
- 🟢 **Consecutive Failures** - Detects systematic issues (max 5)
- 🟢 **Volatility Spike** - Reacts to market volatility (3x threshold)
- 🟢 **Execution Failures** - Monitors execution success (min 70%)
- 🟢 **Anomalous Slippage** - Detects unusual slippage (2.5 std dev)

**Controls:**
- **Attempt Recovery** - Try to resume trading (time-locked)
- **Reset All Breakers** - Emergency reset (requires confirmation)

### 5. Market Volatility Table
Real-time volatility tracking:
- Current price
- 1h, 24h, 7d volatility (annualized)
- 1h returns
- Color-coded for quick assessment

### 6. Recent Opportunities Table
Latest 20 arbitrage opportunities:
- Timestamp
- Symbol and chain
- Edge in basis points
- Execution and profitability status
- Actual profit/loss

## Customization

### Change Refresh Interval
Edit `production_dashboard.html`:
```javascript
const REFRESH_INTERVAL = 30000; // 30 seconds (change as needed)
```

### Add Custom Metrics
Create new API endpoints in `src/api/production_endpoints.py`:

```python
@router.get("/custom/metric")
async def get_custom_metric() -> dict[str, Any]:
    # Your custom logic
    return {"metric": value}
```

Then add to dashboard JavaScript:
```javascript
async function fetchCustomMetric() {
    const response = await fetch('/api/production/custom/metric');
    const data = await response.json();
    // Update UI
}
```

### Modify Circuit Breaker Thresholds
Edit `src/ai/circuit_breakers.py`:
```python
@dataclass
class CircuitBreakerConfig:
    min_win_rate: float = 0.40  # Adjust as needed
    max_drawdown_pct: float = 0.15
    # ... other thresholds
```

## Troubleshooting

### Dashboard Not Loading
```bash
# Check if web server is running
ps aux | grep uvicorn

# Check logs
tail -f logs/web_server.log

# Restart dashboard
pkill -f uvicorn
./start_dashboard.sh
```

### API Errors (500)
```bash
# Check if infrastructure is running
docker-compose ps

# Check TimescaleDB connection
docker-compose logs timescaledb

# Verify database has data
psql -h localhost -p 5433 -U trading_user -d trading_db \
  -c "SELECT COUNT(*) FROM arbitrage_opportunities"
```

### Circuit Breakers Not Updating
```bash
# Test circuit breaker API directly
curl http://localhost:8080/api/production/circuit-breakers/status

# Check if circuit breaker manager is initialized
python -c "
from src.ai.circuit_breakers import get_circuit_breaker_manager
manager = get_circuit_breaker_manager()
print(manager.get_status())
"
```

### No Volatility Data
```bash
# Check if market data collector has data
python -c "
import asyncio
from src.ai.market_data import get_market_data_collector

async def test():
    collector = get_market_data_collector()
    await collector.connect()
    data = await collector.get_latest_volatility('ETH/USDC', 'ethereum')
    print(data)

asyncio.run(test())
"
```

### Models Not Found
```bash
# Check if models exist
ls -lh models/

# Re-bootstrap if needed
./run.sh scripts/bootstrap_ml_models.py
```

## WebSocket Integration (Future)

The dashboard currently uses polling (30s refresh). For real-time updates, implement WebSocket:

```javascript
const ws = new WebSocket('ws://localhost:8080/ws');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    // Update dashboard in real-time
};
```

## Mobile Access

Access from mobile device on same network:
```bash
# Find your local IP
ip addr show | grep inet

# Start dashboard on all interfaces
uvicorn web_server:app --host 0.0.0.0 --port 8080

# Access from mobile
http://<your-ip>:8080
```

## Security Considerations

⚠️ **Important for Production:**

1. **Authentication** - Dashboard has NO authentication
   - Add basic auth or OAuth before exposing publicly
   - Use nginx reverse proxy with authentication

2. **HTTPS** - Currently HTTP only
   - Use SSL certificate for production
   - Configure uvicorn with SSL

3. **Rate Limiting** - No rate limits on API
   - Add rate limiting middleware
   - Protect against DoS

4. **CORS** - Currently wide open
   - Configure CORS for production
   - Whitelist specific origins

## Advanced Usage

### Programmatic Access
```python
import httpx
import asyncio

async def get_system_status():
    async with httpx.AsyncClient() as client:
        # Get health
        health = await client.get('http://localhost:8080/api/production/health')

        # Get circuit breakers
        breakers = await client.get('http://localhost:8080/api/production/circuit-breakers/status')

        # Get opportunities
        opportunities = await client.get(
            'http://localhost:8080/api/production/opportunities/recent',
            params={'hours': 1, 'limit': 10}
        )

        return {
            'health': health.json(),
            'breakers': breakers.json(),
            'opportunities': opportunities.json()
        }

# Run
status = asyncio.run(get_system_status())
print(status)
```

### Automated Monitoring Script
```bash
#!/bin/bash
# monitor_health.sh - Check system health and alert

HEALTH=$(curl -s http://localhost:8080/api/production/health)
STATUS=$(echo $HEALTH | jq -r '.overall_status')

if [ "$STATUS" != "healthy" ]; then
    echo "⚠️ System unhealthy: $STATUS"
    # Send alert (email, Slack, Discord, etc.)
fi
```

## Support

For issues or questions:
1. Check logs: `tail -f logs/*.log`
2. Review API docs: http://localhost:8080/docs
3. Check Grafana: http://localhost:3000
4. Review PRODUCTION_DEPLOYMENT.md for infrastructure setup

---

**Your dashboard is production-ready!** Access it at http://localhost:8080 and monitor your arbitrage system in real-time.
