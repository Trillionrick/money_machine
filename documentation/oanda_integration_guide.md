# OANDA v20 REST API Integration Guide

Complete guide for integrating OANDA forex trading into your existing crypto/DEX application.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Configuration](#configuration)
3. [Basic Usage Examples](#basic-usage-examples)
4. [Market Data Integration](#market-data-integration)
5. [Order Management](#order-management)
6. [Position Reconciliation](#position-reconciliation)
7. [Streaming Real-Time Data](#streaming-real-time-data)
8. [Edge Cases & Forex-Specific Handling](#edge-cases--forex-specific-handling)
9. [Database Integration](#database-integration)
10. [Migration Strategy](#migration-strategy)
11. [Production Checklist](#production-checklist)

---

## Quick Start

### 1. Install Dependencies

The OANDA adapter uses existing dependencies (already in `pyproject.toml`):

```bash
# If using uv (recommended)
uv pip install -e ".[exchange]"

# Or with pip
pip install -e ".[exchange]"
```

### 2. Configure Credentials

Update `.env` with your OANDA credentials:

```bash
# OANDA (Forex) - Get API token from https://www.oanda.com/account/tpa/personal_token
OANDA_API_TOKEN=your_token_here
OANDA_ACCOUNT_ID=your-account-id-here
OANDA_ENVIRONMENT=practice  # 'practice' for demo, 'live' for real trading
```

### 3. Test Connection

```python
import asyncio
from src.brokers.oanda_config import OandaConfig
from src.brokers.oanda_adapter import OandaAdapter

async def test_connection():
    config = OandaConfig.from_env()

    async with OandaAdapter(config) as adapter:
        # Get account summary
        account = await adapter.get_account()
        print(f"Account balance: {account['balance']} {account['currency']}")

        # Get tradeable instruments
        instruments = await adapter.get_instruments()
        print(f"Available instruments: {len(instruments)}")

asyncio.run(test_connection())
```

---

## Configuration

### Environment Variables

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `OANDA_API_TOKEN` | Bearer token from OANDA | `e40e15bb...` | Yes |
| `OANDA_ACCOUNT_ID` | Your account ID | `101-001-1234567-001` | Yes |
| `OANDA_ENVIRONMENT` | Environment (practice/live) | `practice` | No (default: practice) |

### Pydantic Configuration

For programmatic configuration:

```python
from src.brokers.oanda_config import OandaConfig, OandaEnvironment
from pydantic import SecretStr

config = OandaConfig(
    oanda_token=SecretStr("your_token_here"),
    oanda_account_id="101-001-1234567-001",
    oanda_environment=OandaEnvironment.PRACTICE,
    max_requests_per_second=100,  # Conservative rate limit
    streaming_heartbeat_interval=5,
)
```

---

## Basic Usage Examples

### Example 1: Get Account Information

```python
async def get_account_info():
    from src.brokers.oanda_config import OandaConfig
    from src.brokers.oanda_adapter import OandaAdapter

    config = OandaConfig.from_env()

    async with OandaAdapter(config) as adapter:
        account = await adapter.get_account()

        print(f"Balance: {account['balance']}")
        print(f"Unrealized P&L: {account['unrealized_pl']}")
        print(f"NAV: {account['nav']}")
        print(f"Margin Used: {account['margin_used']}")
        print(f"Margin Available: {account['margin_available']}")
```

### Example 2: Place a Market Order

```python
from src.core.execution import Order, OrderType, Side

async def place_market_order():
    from src.brokers.oanda_config import OandaConfig
    from src.brokers.oanda_adapter import OandaAdapter

    config = OandaConfig.from_env()

    async with OandaAdapter(config) as adapter:
        # Buy 10,000 units of EUR/USD
        order = Order(
            symbol="EUR/USD",
            side=Side.BUY,
            quantity=10_000,
            order_type=OrderType.MARKET,
        )

        await adapter.submit_orders([order])
        print("Order submitted successfully")
```

### Example 3: Place a Limit Order

```python
async def place_limit_order():
    from src.brokers.oanda_config import OandaConfig
    from src.brokers.oanda_adapter import OandaAdapter

    config = OandaConfig.from_env()

    async with OandaAdapter(config) as adapter:
        # Buy EUR/USD at 1.0950
        order = Order(
            symbol="EUR/USD",
            side=Side.BUY,
            quantity=10_000,
            order_type=OrderType.LIMIT,
            price=1.0950,
        )

        await adapter.submit_orders([order])
        print("Limit order placed")
```

### Example 4: Get Current Positions

```python
async def get_positions():
    from src.brokers.oanda_config import OandaConfig
    from src.brokers.oanda_adapter import OandaAdapter

    config = OandaConfig.from_env()

    async with OandaAdapter(config) as adapter:
        positions = await adapter.get_positions()

        for symbol, quantity in positions.items():
            direction = "LONG" if quantity > 0 else "SHORT"
            print(f"{symbol}: {abs(quantity)} {direction}")
```

### Example 5: Close All Positions for an Instrument

```python
async def close_eur_usd_position():
    from src.brokers.oanda_config import OandaConfig
    from src.brokers.oanda_adapter import OandaAdapter

    config = OandaConfig.from_env()

    async with OandaAdapter(config) as adapter:
        # Close all EUR/USD positions (both long and short)
        await adapter.close_position(
            "EUR/USD",
            long_units="ALL",
            short_units="ALL",
        )
        print("Position closed")
```

---

## Market Data Integration

### Fetching Historical Candles

```python
from datetime import datetime, timezone
from src.brokers.oanda_config import OandaConfig
from src.brokers.oanda_adapter import OandaAdapter
from src.brokers.oanda_market_data import (
    OandaMarketData,
    CandleGranularity,
    PriceComponent,
)

async def fetch_historical_data():
    config = OandaConfig.from_env()

    async with OandaAdapter(config) as adapter:
        market_data = OandaMarketData(config, adapter.client)

        # Fetch last 100 1-hour candles for EUR/USD
        candles = await market_data.get_latest_candles(
            instrument="EUR_USD",
            granularity=CandleGranularity.H1,
            count=100,
            price=PriceComponent.MID,
        )

        # Normalize to standard OHLCV format
        normalized = market_data.normalize_candles(candles, PriceComponent.MID)

        for candle in normalized[-5:]:  # Show last 5
            print(f"{candle['time']}: O={candle['open']}, C={candle['close']}")
```

### Fetching Large Historical Ranges (Pagination)

```python
async def fetch_large_range():
    from datetime import datetime, timezone, timedelta

    config = OandaConfig.from_env()

    async with OandaAdapter(config) as adapter:
        market_data = OandaMarketData(config, adapter.client)

        # Fetch 1 year of daily candles (auto-paginated)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=365)

        candles = await market_data.get_candles_paginated(
            instrument="EUR_USD",
            granularity=CandleGranularity.D,
            from_time=start_time,
            to_time=end_time,
            price=PriceComponent.MID,
        )

        print(f"Fetched {len(candles)} daily candles")

        # Detect weekend gaps
        gaps = market_data.detect_weekend_gaps(
            market_data.normalize_candles(candles),
            CandleGranularity.D,
        )
        print(f"Found {len(gaps)} weekend gaps")
```

### Storing Candles in TimescaleDB

```python
async def store_candles_in_db():
    import asyncpg
    from decimal import Decimal

    config = OandaConfig.from_env()

    # Connect to TimescaleDB
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="your_user",
        password="your_password",
        database="trading_db",
    )

    async with OandaAdapter(config) as adapter:
        market_data = OandaMarketData(config, adapter.client)

        # Fetch candles
        candles = await market_data.get_latest_candles(
            instrument="EUR_USD",
            granularity=CandleGranularity.H1,
            count=100,
        )

        # Insert into database
        for candle in candles:
            if not candle.get("complete"):
                continue

            mid = candle.get("mid", {})
            bid = candle.get("bid", {})
            ask = candle.get("ask", {})

            await conn.execute(
                """
                INSERT INTO oanda_candles
                (time, instrument, granularity, open, high, low, close, volume,
                 bid_open, bid_high, bid_low, bid_close,
                 ask_open, ask_high, ask_low, ask_close, complete)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
                ON CONFLICT (time, instrument, granularity) DO UPDATE
                SET open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                    close = EXCLUDED.close, volume = EXCLUDED.volume,
                    bid_open = EXCLUDED.bid_open, bid_high = EXCLUDED.bid_high,
                    bid_low = EXCLUDED.bid_low, bid_close = EXCLUDED.bid_close,
                    ask_open = EXCLUDED.ask_open, ask_high = EXCLUDED.ask_high,
                    ask_low = EXCLUDED.ask_low, ask_close = EXCLUDED.ask_close,
                    complete = EXCLUDED.complete
                """,
                candle["time"], "EUR_USD", "H1",
                Decimal(mid["o"]), Decimal(mid["h"]), Decimal(mid["l"]), Decimal(mid["c"]),
                int(candle.get("volume", 0)),
                Decimal(bid["o"]) if bid else None,
                Decimal(bid["h"]) if bid else None,
                Decimal(bid["l"]) if bid else None,
                Decimal(bid["c"]) if bid else None,
                Decimal(ask["o"]) if ask else None,
                Decimal(ask["h"]) if ask else None,
                Decimal(ask["l"]) if ask else None,
                Decimal(ask["c"]) if ask else None,
                candle.get("complete", False),
            )

    await conn.close()
```

---

## Order Management

### Multi-Broker Order Routing

```python
async def route_orders_multi_broker():
    from src.brokers.alpaca_adapter import AlpacaAdapter
    from src.brokers.kraken_adapter import KrakenAdapter
    from src.brokers.oanda_adapter import OandaAdapter
    from src.brokers.config import AlpacaConfig
    from src.brokers.oanda_config import OandaConfig
    from src.core.execution import Order, OrderType, Side

    # Initialize multiple brokers
    alpaca = AlpacaAdapter(**AlpacaConfig.from_env().__dict__)
    oanda_config = OandaConfig.from_env()
    oanda = OandaAdapter(oanda_config)

    # Route orders based on instrument type
    orders = [
        Order(symbol="AAPL", side=Side.BUY, quantity=10, order_type=OrderType.MARKET),
        Order(symbol="EUR/USD", side=Side.BUY, quantity=10_000, order_type=OrderType.MARKET),
        Order(symbol="BTC/USD", side=Side.SELL, quantity=0.1, order_type=OrderType.MARKET),
    ]

    for order in orders:
        if "/" in order.symbol and order.symbol not in ("BTC/USD", "ETH/USD"):
            # Forex pair -> OANDA
            await oanda.submit_orders([order])
            print(f"Routed {order.symbol} to OANDA")
        elif order.symbol in ("BTC/USD", "ETH/USD"):
            # Crypto -> Kraken (not shown, but similar)
            print(f"Would route {order.symbol} to Kraken")
        else:
            # Stock -> Alpaca
            await alpaca.submit_orders([order])
            print(f"Routed {order.symbol} to Alpaca")
```

---

## Position Reconciliation

### Syncing Positions Across Brokers

```python
async def reconcile_positions():
    from src.brokers.oanda_config import OandaConfig
    from src.brokers.oanda_adapter import OandaAdapter
    from collections import defaultdict

    config = OandaConfig.from_env()

    # Get positions from all brokers
    all_positions = defaultdict(float)

    async with OandaAdapter(config) as oanda:
        oanda_positions = await oanda.get_positions()

        for symbol, quantity in oanda_positions.items():
            all_positions[f"OANDA:{symbol}"] = quantity

    # Check for discrepancies
    for key, quantity in all_positions.items():
        if abs(quantity) > 0:
            print(f"{key}: {quantity:.2f} units")
```

---

## Streaming Real-Time Data

### Streaming Prices

```python
async def stream_forex_prices():
    from src.brokers.oanda_config import OandaConfig
    from src.brokers.oanda_adapter import OandaAdapter
    from src.brokers.oanda_streaming import OandaStreamingClient

    config = OandaConfig.from_env()

    async with OandaAdapter(config) as adapter:
        streaming = OandaStreamingClient(config, adapter.stream_client)

        # Stream EUR/USD and GBP/USD prices
        instruments = ["EUR_USD", "GBP_USD"]

        async for price_update in streaming.stream_prices(instruments):
            if price_update.get("type") == "PRICE":
                instrument = price_update.get("instrument")
                bids = price_update.get("bids", [])
                asks = price_update.get("asks", [])

                if bids and asks:
                    bid = bids[0].get("price")
                    ask = asks[0].get("price")
                    spread = float(ask) - float(bid)

                    print(f"{instrument}: Bid={bid}, Ask={ask}, Spread={spread:.5f}")
```

### Streaming Order Fills

```python
async def stream_fills():
    from src.brokers.oanda_config import OandaConfig
    from src.brokers.oanda_adapter import OandaAdapter

    config = OandaConfig.from_env()

    async with OandaAdapter(config) as adapter:
        print("Streaming fills...")

        async for fill in adapter.stream_fills():
            print(f"Fill: {fill.symbol} {fill.side} {fill.quantity} @ {fill.price}")
```

---

## Edge Cases & Forex-Specific Handling

### Weekend Gap Detection

```python
async def handle_weekend_gaps():
    from src.brokers.oanda_config import OandaConfig
    from src.brokers.oanda_adapter import OandaAdapter
    from src.brokers.oanda_market_data import OandaMarketData, CandleGranularity
    from datetime import datetime

    config = OandaConfig.from_env()

    async with OandaAdapter(config) as adapter:
        market_data = OandaMarketData(config, adapter.client)

        candles = await market_data.get_latest_candles(
            instrument="EUR_USD",
            granularity=CandleGranularity.H1,
            count=200,
        )

        normalized = market_data.normalize_candles(candles)
        gaps = market_data.detect_weekend_gaps(normalized, CandleGranularity.H1)

        for gap_start, gap_end in gaps:
            gap_hours = (gap_end - gap_start).total_seconds() / 3600
            print(f"Weekend gap: {gap_start} to {gap_end} ({gap_hours:.1f} hours)")

            # Strategy: Use last known price or skip trading during gaps
```

### Negative Balance Protection (Closeout Handling)

```python
async def monitor_margin_closeout():
    """
    OANDA automatically closes positions if equity falls below margin requirements.
    Monitor account status to detect forced liquidations.
    """
    from src.brokers.oanda_config import OandaConfig
    from src.brokers.oanda_adapter import OandaAdapter

    config = OandaConfig.from_env()

    async with OandaAdapter(config) as adapter:
        account = await adapter.get_account()

        margin_used = account['margin_used']
        margin_available = account['margin_available']
        nav = account['nav']

        # Calculate margin level
        if margin_used > 0:
            margin_level = (nav / margin_used) * 100
            print(f"Margin level: {margin_level:.2f}%")

            # Warning threshold (OANDA closes at ~100%)
            if margin_level < 120:
                print("⚠️  WARNING: Approaching margin closeout!")

                # Reduce positions to avoid forced liquidation
                positions = await adapter.get_positions()
                for symbol, quantity in positions.items():
                    if abs(quantity) > 0:
                        print(f"Consider closing {symbol} position")
```

### Instrument Precision Handling

```python
from src.brokers.oanda_config import get_instrument_precision
from decimal import Decimal

def format_price_for_oanda(instrument: str, price: float) -> str:
    """Format price with correct precision for OANDA."""
    precision = get_instrument_precision(instrument)
    return f"{Decimal(str(price)):.{precision}f}"

# Examples
print(format_price_for_oanda("EUR_USD", 1.09523))  # "1.09523" (5 decimals)
print(format_price_for_oanda("USD_JPY", 149.823))  # "149.823" (3 decimals)
print(format_price_for_oanda("XAU_USD", 2052.45))  # "2052.45" (2 decimals)
```

---

## Database Integration

### Initialize TimescaleDB Schema

```sql
-- Run from psql or database client

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create OANDA tables (from oanda_schema.py)
-- Copy SQL from src/brokers/oanda_schema.py and execute
```

Or programmatically:

```python
import asyncpg
from src.brokers.oanda_schema import get_create_schema_sql

async def init_database():
    conn = await asyncpg.connect(
        host="localhost",
        user="your_user",
        database="trading_db",
    )

    schema_sql = get_create_schema_sql()
    await conn.execute(schema_sql)

    print("Database schema initialized")
    await conn.close()
```

---

## Migration Strategy

### Phase 1: Add OANDA as Additional Data Source (Week 1)

1. **Setup**:
   - Install OANDA adapter
   - Configure credentials in `.env`
   - Test connection with practice account

2. **Data Integration**:
   - Start collecting forex price data
   - Store in separate TimescaleDB tables
   - No trading yet, just observation

```python
# data_collection.py
async def collect_forex_data():
    from src.brokers.oanda_config import OandaConfig
    from src.brokers.oanda_adapter import OandaAdapter
    from src.brokers.oanda_market_data import OandaMarketData, CandleGranularity

    config = OandaConfig.from_env()

    async with OandaAdapter(config) as adapter:
        market_data = OandaMarketData(config, adapter.client)

        # Major forex pairs
        instruments = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD"]

        for instrument in instruments:
            candles = await market_data.get_latest_candles(
                instrument=instrument,
                granularity=CandleGranularity.H1,
                count=500,
            )

            # Store in database (implementation depends on your DB layer)
            print(f"Collected {len(candles)} candles for {instrument}")
```

### Phase 2: Parallel Testing (Week 2-3)

1. **Paper Trading**:
   - Run strategies on forex data
   - Compare performance vs crypto
   - Test order execution in practice account

2. **Position Sizing Adjustments**:
   - Forex uses different lot sizes than crypto
   - Adjust Kelly criterion calculations
   - Test margin requirements

```python
# strategy_testing.py
async def test_forex_strategy():
    # Your existing strategy, adapted for forex
    # Use OANDA practice account
    pass
```

### Phase 3: Unified Portfolio (Week 4)

1. **Multi-Asset Portfolio**:
   - Combine crypto and forex positions
   - Unified risk management
   - Cross-asset correlation analysis

2. **Order Routing Logic**:

```python
class UnifiedBrokerRouter:
    def __init__(self):
        self.alpaca = AlpacaAdapter(...)
        self.kraken = KrakenAdapter(...)
        self.oanda = OandaAdapter(...)

    async def submit_order(self, order: Order):
        if self._is_forex(order.symbol):
            return await self.oanda.submit_orders([order])
        elif self._is_crypto(order.symbol):
            return await self.kraken.submit_orders([order])
        else:
            return await self.alpaca.submit_orders([order])

    def _is_forex(self, symbol: str) -> bool:
        forex_pairs = {"EUR/USD", "GBP/USD", "USD/JPY", ...}
        return symbol in forex_pairs

    def _is_crypto(self, symbol: str) -> bool:
        return symbol in {"BTC/USD", "ETH/USD", ...}
```

### Phase 4: Production Deployment (Week 5+)

1. **Switch to Live OANDA Account**:
   - Update `OANDA_ENVIRONMENT=live` in `.env`
   - Start with small positions
   - Monitor closely for first week

2. **Monitoring & Alerts**:

```python
# monitoring.py
async def monitor_forex_positions():
    """Alert on unusual forex position changes."""
    while True:
        positions = await oanda.get_positions()

        for symbol, quantity in positions.items():
            # Check position limits
            if abs(quantity) > MAX_POSITION_SIZE:
                send_alert(f"Large {symbol} position: {quantity}")

        await asyncio.sleep(60)  # Check every minute
```

---

## Production Checklist

### Security

- [ ] Never log OANDA API token
- [ ] Use environment variables or secrets manager (HashiCorp Vault, AWS Secrets Manager)
- [ ] Enable IP whitelisting on OANDA account
- [ ] Use TLS 1.3 for all connections
- [ ] Rotate API tokens periodically

### Observability

- [ ] Structured logging with correlation IDs
- [ ] Prometheus metrics for:
  - API latency (p50, p95, p99)
  - Rate limit hits
  - Order fill rates
  - Position drift (vs internal state)
- [ ] Health checks:
  - Periodic account summary validation
  - Streaming connection status
  - Database connectivity

### Error Handling

- [ ] Retry logic for transient failures
- [ ] Circuit breakers for OANDA API
- [ ] Graceful degradation if OANDA unavailable
- [ ] Dead letter queue for failed orders

### Testing

- [ ] Unit tests with mocked OANDA responses
- [ ] Integration tests against fxPractice account
- [ ] Load test: 50 concurrent instruments streaming
- [ ] Chaos test: Simulate API downtime mid-trade

### Performance Targets

- [ ] Order submission latency: <100ms p95
- [ ] Streaming price ingestion: 4 updates/sec/instrument without backpressure
- [ ] Database write throughput: >1000 candle inserts/sec
- [ ] Memory footprint: <50MB per active instrument

### Compliance

- [ ] Review NFA/CFTC regulations for forex trading
- [ ] Understand OANDA's terms of service
- [ ] Implement required risk disclosures
- [ ] Maintain audit trail of all trades

---

## Support & Resources

- **OANDA API Documentation**: https://developer.oanda.com/rest-live-v20/introduction/
- **OANDA Support**: https://www.oanda.com/contact
- **NFA Investor Advisory**: [Included in documentation folder]
- **Project Issues**: https://github.com/yourrepo/issues

---

## Troubleshooting

### Common Issues

**Issue**: `401 Unauthorized` error

**Solution**: Check that your OANDA_API_TOKEN is correct and hasn't expired.

---

**Issue**: `404 Not Found` for instrument

**Solution**: Some instruments aren't available in all jurisdictions. Use `get_instruments()` to see what's tradeable.

```python
instruments = await adapter.get_instruments()
available = [i["name"] for i in instruments]
print(f"Available: {available}")
```

---

**Issue**: Weekend trading hours

**Solution**: Forex markets close Friday 17:00 ET, reopen Sunday 17:00 ET. Detect weekend gaps:

```python
gaps = market_data.detect_weekend_gaps(candles, granularity)
```

---

**Issue**: Streaming disconnects

**Solution**: The adapter auto-reconnects with exponential backoff. Check logs for `oanda.stream.reconnecting`.

---

## Next Steps

1. Review [NFA Investor Advisory](../documentation/customeradvisory_urvct121517.pdf)
2. Open OANDA practice account if you don't have one
3. Run integration tests
4. Start collecting forex data
5. Gradually add forex to your portfolio

Good luck with your forex trading integration!
