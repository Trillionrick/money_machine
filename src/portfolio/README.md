# 1inch Portfolio API v5.0 Integration

Track wallet positions, profits, and performance across multiple chains and DeFi protocols.

## Quick Start

### 1. Get API Key

Visit [1inch Developer Portal](https://portal.1inch.dev/) and create an API key.

### 2. Configure Environment

Add to `.env`:

```bash
ONEINCH_API_KEY=your_api_key_here
PORTFOLIO_WALLETS=0x742d35Cc6634C0532925a3b844Bc454e4438f44e
```

### 3. Use in Code

```python
from src.portfolio import OneInchPortfolioClient, TimeRange

async def main():
    client = OneInchPortfolioClient(api_key="your_key")

    # Get current snapshot
    snapshot = await client.get_full_snapshot("0x742d35...")
    print(f"Total Value: ${snapshot.total_value_usd}")

    # Get 30-day metrics
    metrics = await client.get_full_metrics("0x742d35...", TimeRange.ONE_MONTH)
    print(f"30-day Profit: ${metrics.total_profit_usd}")
    print(f"30-day ROI: {metrics.total_roi_percentage}%")

    await client.close()
```

## Architecture

### Key Concepts

**Snapshot** = Current State (Fast)
- Token balances and amounts
- Current prices and values
- Protocol positions
- No historical data

**Metrics** = Historical Analytics (Slower)
- Profit/Loss over time
- ROI percentage
- APR for protocol positions
- Requires time range

### Modules

- **oneinch_client.py** - Direct API client with retry logic
- **tracker.py** - Background service with auto-updates and caching

## API Endpoints

### Dashboard Endpoints

```bash
# Get status
GET /api/portfolio/status

# Get all snapshots
GET /api/portfolio/snapshots

# Get metrics
GET /api/portfolio/metrics?time_range=1month

# Get total value
GET /api/portfolio/total-value

# Start/stop tracking
POST /api/portfolio/start
POST /api/portfolio/stop
```

### Python API

**Client Methods:**
- `get_status(address)` - Check availability
- `get_full_snapshot(address)` - Current positions
- `get_full_metrics(address, time_range)` - Historical PnL
- `get_tokens_snapshot(address)` - Token balances
- `get_tokens_metrics(address, time_range)` - Token PnL
- `get_protocols_snapshot(address)` - Protocol positions
- `get_protocols_metrics(address, time_range)` - Protocol PnL

**Tracker Methods:**
- `start()` - Begin auto-updates
- `stop()` - Stop tracking
- `get_all_snapshots()` - Get cached data
- `get_total_portfolio_value()` - Aggregate value

## Examples

See `examples/portfolio_tracking_example.py` for:
- Direct client usage
- Background tracker service
- Multi-wallet comparison
- Performance analysis

## Documentation

Full documentation: `documentation/1INCH_PORTFOLIO_V5_GUIDE.md`

## Migration from v4

If migrating from v4, see the guide for endpoint mappings:

| v4 | v5.0 |
|----|------|
| `/v4/overview/erc20/current_value` | `/v5.0/tokens/snapshot` |
| `/v4/overview/erc20/profit_and_loss` | `/v5.0/tokens/metrics` |
| `/v4/overview/protocols/current_value` | `/v5.0/protocols/snapshot` |
| `/v4/overview/protocols/profit_and_loss` | `/v5.0/protocols/metrics` |

## Support

- [1inch Portfolio API Docs](https://portal.1inch.dev/documentation/apis/portfolio-api)
- Check logs with `structlog` for detailed errors
- Use health endpoints for monitoring
