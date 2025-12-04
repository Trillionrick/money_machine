# 1inch Portfolio API v5.0 Integration Guide

## Overview

This project now includes full integration with **1inch Portfolio API v5.0** for tracking wallet positions, profits, and performance across multiple chains and DeFi protocols.

## Key Features

✅ **v5.0 Architecture**
- **Snapshots**: Current state of positions (token balances, amounts, values)
- **Metrics**: Historical analytics (PnL, ROI, APR over time ranges)

✅ **Multi-Wallet Support**
- Track multiple wallets simultaneously
- Aggregate portfolio value across all wallets
- Individual and combined metrics

✅ **Multi-Chain Support**
- Ethereum, Polygon, and other supported chains
- Chain-specific filtering
- Aggregated cross-chain views

✅ **Real-Time Updates**
- Configurable update intervals
- Automatic retry on errors
- In-memory caching with TTL

✅ **Dashboard Integration**
- REST API endpoints for portfolio data
- WebSocket support for live updates
- Start/stop controls

## Migration from v4 to v5.0

### What Changed

| v4 Endpoint | v5.0 Endpoint | Notes |
|-------------|---------------|-------|
| `/portfolio/v4/general/is_available` | `/portfolio/v5.0/general/status` | Renamed |
| `/portfolio/v4/general/profit_and_loss` | Removed → see `/metrics` | Moved to metrics |
| `/portfolio/v4/general/value_chart` | `/portfolio/v5.0/general/chart` | Renamed |
| `/portfolio/v4/overview/erc20/current_value` | `/portfolio/v5.0/tokens/snapshot` | Snapshot replaces current value |
| `/portfolio/v4/overview/erc20/profit_and_loss` | `/portfolio/v5.0/tokens/metrics` | Historical metrics |
| `/portfolio/v4/overview/protocols/current_value` | `/portfolio/v5.0/protocols/snapshot` | Snapshot replaces current value |
| `/portfolio/v4/overview/protocols/profit_and_loss` | `/portfolio/v5.0/protocols/metrics` | Historical metrics |

### Key Concepts

**Snapshot = Current State**
- Token balances and amounts
- Current prices
- Current USD values
- Protocol positions
- No historical data

**Metrics = Historical Analytics**
- Profit/Loss over time
- ROI percentage
- APR for protocol positions
- Requires time range parameter

## Setup & Configuration

### 1. Environment Variables

Add these to your `.env` file:

```bash
# Required: 1inch API Key
ONEINCH_API_KEY=your_1inch_api_key_here

# Required: Wallet addresses to track (comma-separated)
PORTFOLIO_WALLETS=0x1234...,0x5678...

# Optional: Wallet names (comma-separated, matches order of PORTFOLIO_WALLETS)
PORTFOLIO_WALLET_NAMES=Main Wallet,Trading Wallet

# Optional: Enable/disable portfolio tracking (default: true)
PORTFOLIO_ENABLED=true

# Optional: Snapshot update interval in seconds (default: 60)
PORTFOLIO_SNAPSHOT_INTERVAL=60

# Optional: Metrics update interval in seconds (default: 300)
PORTFOLIO_METRICS_INTERVAL=300
```

### 2. Get 1inch API Key

1. Visit [1inch Developer Portal](https://portal.1inch.dev/)
2. Create an account or sign in
3. Navigate to API Keys section
4. Create a new API key
5. Copy the key and add to `.env` as `ONEINCH_API_KEY`

### 3. Configure Wallets

Add your wallet addresses to `.env`:

```bash
# Single wallet
PORTFOLIO_WALLETS=0x742d35Cc6634C0532925a3b844Bc454e4438f44e

# Multiple wallets
PORTFOLIO_WALLETS=0x742d35Cc6634C0532925a3b844Bc454e4438f44e,0x1234567890123456789012345678901234567890

# With custom names
PORTFOLIO_WALLET_NAMES=MetaMask Wallet,Rainbow Wallet
```

## Usage

### Method 1: Programmatic Usage

```python
import asyncio
from src.portfolio import OneInchPortfolioClient, TimeRange

async def main():
    # Initialize client
    client = OneInchPortfolioClient(
        api_key="your_1inch_api_key",
        timeout=10.0,
        max_retries=3,
    )

    wallet_address = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"

    # Get current snapshot (current state)
    snapshot = await client.get_full_snapshot(wallet_address)
    print(f"Total Value: ${snapshot.total_value_usd}")
    print(f"Chains: {len(snapshot.chains)}")

    # Get 1-month metrics (historical PnL)
    metrics = await client.get_full_metrics(
        wallet_address,
        time_range=TimeRange.ONE_MONTH
    )
    print(f"30-day Profit: ${metrics.total_profit_usd}")
    print(f"30-day ROI: {metrics.total_roi_percentage}%")

    # Get token snapshot
    tokens = await client.get_tokens_snapshot(wallet_address)
    print(f"Tokens: {tokens}")

    # Get protocol positions
    protocols = await client.get_protocols_snapshot(wallet_address)
    print(f"Protocol Positions: {protocols}")

    # Cleanup
    await client.close()

asyncio.run(main())
```

### Method 2: Portfolio Tracker Service

```python
import asyncio
from src.portfolio import create_portfolio_tracker_from_env

async def main():
    # Create tracker from environment variables
    tracker = create_portfolio_tracker_from_env()

    if not tracker:
        print("Portfolio tracker not configured")
        return

    # Start tracking (runs in background)
    await tracker.start()

    # Get cached data (updated automatically)
    while True:
        total_value = tracker.get_total_portfolio_value()
        print(f"Total Portfolio Value: ${total_value}")

        all_snapshots = tracker.get_all_snapshots()
        for address, snapshot in all_snapshots.items():
            print(f"  {address}: ${snapshot.total_value_usd}")

        await asyncio.sleep(10)

asyncio.run(main())
```

### Method 3: Dashboard API

The web dashboard (`web_server.py`) automatically exposes portfolio endpoints:

**Get Portfolio Status:**
```bash
curl http://localhost:8080/api/portfolio/status
```

**Get All Snapshots:**
```bash
curl http://localhost:8080/api/portfolio/snapshots
```

**Get Metrics:**
```bash
# All wallets, 1-month metrics
curl http://localhost:8080/api/portfolio/metrics?time_range=1month

# Specific wallet, 1-day metrics
curl "http://localhost:8080/api/portfolio/metrics?address=0x742d35...&time_range=1day"
```

**Get Total Value:**
```bash
curl http://localhost:8080/api/portfolio/total-value
```

**Start/Stop Tracking:**
```bash
# Start
curl -X POST http://localhost:8080/api/portfolio/start

# Stop
curl -X POST http://localhost:8080/api/portfolio/stop
```

## API Endpoints

### Snapshot Endpoints

**Get Current State (No Historical Data)**

- `get_tokens_snapshot(address)` - Token balances and values
- `get_protocols_snapshot(address)` - Protocol position values
- `get_full_snapshot(address)` - Combined snapshot

**Use Case:** "What do I currently own and what's it worth?"

### Metrics Endpoints

**Get Historical Analytics**

- `get_tokens_metrics(address, time_range)` - Token PnL and ROI
- `get_protocols_metrics(address, time_range)` - Protocol PnL, ROI, APR
- `get_full_metrics(address, time_range)` - Combined metrics

**Use Case:** "How much profit did I make this month?"

### General Endpoints

- `get_status(address)` - Check if portfolio data is available
- `get_supported_chains()` - List supported blockchains
- `get_supported_protocols()` - List supported DeFi protocols
- `get_current_value(address)` - Quick total value lookup
- `get_value_chart(address, time_range)` - Historical value chart data
- `check_address(address)` - Validate address and check activity

## Time Ranges

Available time ranges for metrics:

- `TimeRange.ONE_DAY` - Last 24 hours
- `TimeRange.ONE_WEEK` - Last 7 days
- `TimeRange.ONE_MONTH` - Last 30 days
- `TimeRange.THREE_MONTHS` - Last 90 days
- `TimeRange.ONE_YEAR` - Last 365 days
- `TimeRange.ALL_TIME` - Since wallet creation

## Architecture

```
src/portfolio/
├── __init__.py              # Public API exports
├── oneinch_client.py        # 1inch Portfolio API v5.0 client
└── tracker.py               # Portfolio tracker service

Integration Points:
├── web_server.py            # Dashboard API endpoints
└── .env                     # Configuration
```

## Example Responses

### Snapshot Response

```json
{
  "address": "0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
  "total_value_usd": 125430.50,
  "chains": {
    "1": {
      "chain_id": "1",
      "total_value_usd": 100000.00,
      "tokens": [
        {
          "address": "0x...",
          "symbol": "USDC",
          "balance": "50000.0",
          "value_usd": 50000.00
        }
      ],
      "protocols": [
        {
          "id": "uniswap_v3",
          "name": "Uniswap V3",
          "value_usd": 25000.00
        }
      ]
    }
  }
}
```

### Metrics Response

```json
{
  "address": "0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
  "time_range": "1month",
  "total_profit_usd": 3250.75,
  "total_roi_percentage": 2.65,
  "protocols": [
    {
      "protocol_name": "Uniswap V3",
      "chain_id": "1",
      "profit_usd": 1500.00,
      "roi_percentage": 6.0,
      "apr_percentage": 72.0
    }
  ],
  "tokens": [
    {
      "symbol": "ETH",
      "chain_id": "1",
      "profit_usd": 850.25,
      "roi_percentage": 3.2,
      "value_usd": 26570.00
    }
  ]
}
```

## Error Handling

The client includes comprehensive error handling:

- **Automatic Retries**: Up to 3 retries on 5xx errors and timeouts
- **Exponential Backoff**: Delays increase between retries
- **Circuit Breaker**: Tracker continues on errors with backoff
- **Logging**: All errors logged with structured logging

## Performance Considerations

**Update Intervals:**
- Snapshots: Every 60 seconds (default)
- Metrics: Every 300 seconds (default)
- Adjust based on your needs and API rate limits

**Caching:**
- All data cached in-memory
- Configurable TTL (default: 1 hour)
- Stale cache triggers refresh

**Rate Limits:**
- Respect 1inch API rate limits
- Avoid setting intervals too low
- Use caching to minimize API calls

## Troubleshooting

**Portfolio tracker not starting:**
- Check `ONEINCH_API_KEY` is set
- Verify `PORTFOLIO_WALLETS` contains valid addresses
- Check logs for detailed error messages

**No data returned:**
- Ensure wallet has transaction history
- Check wallet address is checksummed correctly
- Verify 1inch supports your target chains

**Stale data:**
- Check tracker is running: `/api/portfolio/status`
- Review update intervals
- Check for errors in logs

## Best Practices

1. **Use Snapshots for Current State**: Fast and cheap
2. **Use Metrics for Analytics**: More expensive, cache aggressively
3. **Set Reasonable Intervals**: 60s snapshots, 5min metrics
4. **Monitor Health**: Use `/api/portfolio/status` endpoint
5. **Handle Errors Gracefully**: Client includes retry logic
6. **Cache Wisely**: Don't request same data repeatedly

## Next Steps

1. Configure your `.env` with API key and wallets
2. Start the dashboard: `python web_server.py`
3. Check status: `http://localhost:8080/api/portfolio/status`
4. View snapshots: `http://localhost:8080/api/portfolio/snapshots`
5. Monitor metrics: `http://localhost:8080/api/portfolio/metrics`

## Support

- [1inch Portfolio API Docs](https://portal.1inch.dev/documentation/apis/portfolio-api)
- [1inch Developer Portal](https://portal.1inch.dev/)
- Check logs for detailed error messages
- Use `/api/portfolio/status` for health monitoring
