# Kraken Exchange Integration

Complete integration guide for trading cryptocurrencies on Kraken with your aggressive ML trading system.



✅ What Was Integrated

New Files Created:

1. `src/brokers/kraken_adapter.py` - Production-ready Kraken adapter
   - ✅ Modern async/await patterns
   - ✅ HMAC-SHA512 authentication (Kraken standard)
   - ✅ ExecutionEngine protocol compliance
   - ✅ Built-in rate limiting support
   - ✅ Connection pooling with httpx
   - ✅ Automatic error handling

2. `examples/test_kraken_connection.py` - Connection testing
   - ✅ Tests all API endpoints
   - ✅ Verifies authentication
   - ✅ Shows account balances
   - ✅ Non-interactive (CI/CD friendly)

3. `examples/live_trading_kraken.py` - Live trading example
   - ✅ Crypto-specific risk limits
   - ✅ Safety confirmations
   - ✅ Real-time trading loop

4. `KRAKEN_INTEGRATION.md` - This guide



🎯 Kraken Capabilities

What You Can Trade:
- ✅ 200+ Cryptocurrencies (BTC, ETH, SOL, DOGE, ADA, DOT, etc.)
- ✅ Fiat Pairs (USD, EUR, GBP, CAD, JPY, CHF, AUD)
- ✅ Crypto-to-Crypto (BTC/ETH, ETH/USDT, etc.)
- ✅ Stablecoins (USDT, USDC, DAI)

Trading Features:
- ✅ Spot Trading (Buy/sell crypto directly)
- ✅ Margin Trading (Up to 5x leverage on select pairs)
- ✅ Advanced Orders (Limit, market, stop-loss, take-profit)
- ✅ High Liquidity (Top 10 global crypto exchange)
- ✅ Low Fees (0.16% maker, 0.26% taker for small volume)

Why Kraken:
- ✅ Regulatory Compliance (Licensed in multiple jurisdictions)
- ✅ Security (Never been hacked, strong security practices)
- ✅ Fiat Support (Easy USD/EUR deposits/withdrawals)
- ✅ 24/7 Trading (Crypto never sleeps)
- ✅ Professional API (Robust, well-documented)


🚀 Quick Start

Step 1: Get Kraken API Keys

1. Sign up: https://www.kraken.com/sign-up
2. Verify your account:
   - Starter (email only) - Limited trading
   - Intermediate (name, DOB, address) - Full crypto trading
   - Pro (government ID) - Fiat deposits/withdrawals
3. Generate API keys:
   - Go to: https://www.kraken.com/u/security/api
   - Click "Generate New Key"
   - Give it a description: "Trading Bot"
   - Permissions (select these):
     - ✅ Query Funds
     - ✅ Query Open Orders & Trades
     - ✅ Query Closed Orders & Trades
     - ✅ Create & Modify Orders
     - ❌ DO NOT enable: Withdraw Funds, Access WebSockets Auth Token
   - Click "Generate Key"
   - Save both keys immediately! (Secret shown only once)

Step 2: Configure .env

Add to your `.env` file:


# Kraken Crypto Exchange
KRAKEN_API_KEY=your_kraken_api_key_here
KRAKEN_API_SECRET=your_kraken_api_secret_here


Step 3: Test Connection


source .venv/bin/activate
python examples/test_kraken_connection.py


Expected output:

✅ ALL TESTS PASSED!
🎯 Kraken connection is working!

📊 Balances (3 assets):
  - ZUSD: 1,000.00000000
  - XXBT: 0.05000000
  - XETH: 1.25000000


Step 4: Start Trading (Optional)

python examples/live_trading_kraken.py


📊 Architecture Overview

Modern Async Design

python
from src.brokers.credentials import BrokerCredentials
from src.brokers.kraken_adapter import KrakenAdapter

# Load credentials (automatic .env loading)
creds = BrokerCredentials()

# Initialize adapter
async with KrakenAdapter(
    api_key=creds.kraken_api_key.get_secret_value(),
    api_secret=creds.kraken_api_secret.get_secret_value(),
) as adapter:
    # Get account balance
    balances = await adapter.get_account()

    # Get BTC price
    ticker = await adapter.get_ticker("XXBTZUSD")

    # Place order
    from src.core.execution import Order, OrderType, Side
    order = Order(
        symbol="BTC/USD",
        side=Side.BUY,
        quantity=0.001,
        order_type=OrderType.LIMIT,
        limit_price=40000.0,
    )
    await adapter.submit_orders([order])


Key Features

1. HMAC-SHA512 Authentication
python
# Automatic signature generation (you don't need to do this)
signature = adapter._generate_signature(url_path, data, nonce)


2. Symbol Format Conversion
python
# Your code uses standard format
order = Order(symbol="BTC/USD", ...)  # Standard format

# Adapter converts to Kraken format automatically
# "BTC/USD" -> "XXBTZUSD" (Kraken's format)


3. Rate Limiting Support
python
from src.utils.rate_limiter import AdaptiveRateLimiter

limiter = AdaptiveRateLimiter(max_requests=15, time_window=1.0)

async with limiter:
    await adapter.submit_orders([order])


4. Error Handling
python
try:
    balances = await adapter.get_account()
except Exception as e:
    log.error("kraken.error", error=str(e))




🔧 Adapter API Reference

Public Endpoints (No Authentication)

Get Server Time:
python
timestamp = await adapter.get_server_time()
# Returns: Unix timestamp (int)


Get Ticker:
python
ticker = await adapter.get_ticker("XXBTZUSD")
# Returns: {'XXBTZUSD': {'a': [...], 'b': [...], 'c': [...]}}


Private Endpoints (Requires API Key)

Get Account Balances:
python
balances = await adapter.get_account()
# Returns: {'ZUSD': '1000.00', 'XXBT': '0.05', ...}


Get Trade Balance:
python
trade_balance = await adapter.get_trade_balance(asset="ZUSD")
# Returns: {'eb': '1000.00', 'mf': '950.00', 'm': '50.00', ...}
# - eb: Equity balance
# - mf: Free margin
# - m: Margin used


Get Positions:
python
positions = await adapter.get_positions()
# Returns: List of open positions


Get Orders:
python
# Open orders
open_orders = await adapter.get_orders(status="open")

# Closed orders
closed_orders = await adapter.get_orders(status="closed")


Trading Endpoints

Submit Orders:
python
from src.core.execution import Order, OrderType, Side

order = Order(
    symbol="ETH/USD",
    side=Side.BUY,
    quantity=0.5,
    order_type=OrderType.LIMIT,
    limit_price=2500.0,
)

await adapter.submit_orders([order])


Cancel Order:
python
await adapter.cancel_order(order_id="O7MN22-ZCX7J-TGLQHD")


Stream Fills:
python
async for fill in adapter.stream_fills():
    print(f"Fill: {fill.symbol} @ ${fill.price}")




💡 Symbol Format Guide

Kraken Symbol Naming

Kraken uses a unique naming convention:
- `X` prefix = crypto
- `Z` prefix = fiat
- `USD` = ZUSD
- `BTC` = XXBT (historical name)

Common Conversions

Your adapter automatically converts:

| Standard | Kraken | Asset |
|-|--|-|
| BTC/USD | XXBTZUSD | Bitcoin |
| ETH/USD | XETHZUSD | Ethereum |
| SOL/USD | SOLUSD | Solana |
| DOGE/USD | XDGUSD | Dogecoin |
| XRP/USD | XXRPZUSD | Ripple |
| ADA/USD | ADAUSD | Cardano |
| DOT/USD | DOTUSD | Polkadot |

How to Find Symbol Names

Method 1: Test Script
python
# Get all trading pairs
result = await adapter._request("AssetPairs")
for pair_name in result.keys():
    print(pair_name)


Method 2: Kraken API Explorer
- Go to: https://api.kraken.com/0/public/AssetPairs
- Search for your desired pair

Method 3: Add to Conversion Map

Edit `src/brokers/kraken_adapter.py`:
python
conversions = {
    "BTC/USD": "XXBTZUSD",
    "ETH/USD": "XETHZUSD",
    "YOUR/PAIR": "KRAKENFORMAT",  # Add here
}




🎮 Usage Examples

Example 1: Check Account Balance

python
import asyncio
from src.brokers.credentials import BrokerCredentials
from src.brokers.kraken_adapter import KrakenAdapter

async def check_balance():
    creds = BrokerCredentials()

    async with KrakenAdapter(
        api_key=creds.kraken_api_key.get_secret_value(),
        api_secret=creds.kraken_api_secret.get_secret_value(),
    ) as adapter:
        # Get all balances
        balances = await adapter.get_account()

        # Get trade balance (equity, margin, etc.)
        trade_balance = await adapter.get_trade_balance()

        print(f"Equity: ${float(trade_balance['eb']):,.2f}")
        print(f"Free Margin: ${float(trade_balance['mf']):,.2f}")

        for asset, amount in balances.items():
            if float(amount) > 0:
                print(f"{asset}: {amount}")

asyncio.run(check_balance())


Example 2: Get Current BTC Price

python
async def get_btc_price():
    creds = BrokerCredentials()

    async with KrakenAdapter(
        api_key=creds.kraken_api_key.get_secret_value(),
        api_secret=creds.kraken_api_secret.get_secret_value(),
    ) as adapter:
        ticker = await adapter.get_ticker("XXBTZUSD")
        btc_data = ticker["XXBTZUSD"]

        last_price = float(btc_data["c"][0])
        print(f"BTC/USD: ${last_price:,.2f}")

asyncio.run(get_btc_price())


Example 3: Place Limit Order

python
from src.core.execution import Order, OrderType, Side

async def place_order():
    creds = BrokerCredentials()

    async with KrakenAdapter(
        api_key=creds.kraken_api_key.get_secret_value(),
        api_secret=creds.kraken_api_secret.get_secret_value(),
    ) as adapter:
        # Buy 0.001 BTC at $40,000
        order = Order(
            symbol="BTC/USD",
            side=Side.BUY,
            quantity=0.001,
            order_type=OrderType.LIMIT,
            limit_price=40000.0,
        )

        await adapter.submit_orders([order])
        print("✓ Order placed!")

asyncio.run(place_order())


Example 4: Monitor Open Orders

python
async def monitor_orders():
    creds = BrokerCredentials()

    async with KrakenAdapter(
        api_key=creds.kraken_api_key.get_secret_value(),
        api_secret=creds.kraken_api_secret.get_secret_value(),
    ) as adapter:
        while True:
            orders = await adapter.get_orders(status="open")
            print(f"Open orders: {len(orders)}")

            for order in orders:
                print(f"  - {order.get('descr', {}).get('order', 'N/A')}")

            await asyncio.sleep(10)  # Check every 10 seconds

asyncio.run(monitor_orders())


Example 5: Multi-Exchange Trading

python
from src.brokers.alpaca_adapter import AlpacaAdapter

async def multi_exchange():
    creds = BrokerCredentials()

    # Connect to both Alpaca and Kraken
    alpaca = AlpacaAdapter(
        api_key=creds.alpaca_api_key.get_secret_value(),
        api_secret=creds.alpaca_api_secret.get_secret_value(),
        paper=True,
    )

    async with KrakenAdapter(
        api_key=creds.kraken_api_key.get_secret_value(),
        api_secret=creds.kraken_api_secret.get_secret_value(),
    ) as kraken:
        # Trade stocks on Alpaca
        stock_order = Order(symbol="AAPL", side=Side.BUY, quantity=10, ...)
        await alpaca.submit_orders([stock_order])

        # Trade crypto on Kraken
        crypto_order = Order(symbol="BTC/USD", side=Side.BUY, quantity=0.001, ...)
        await kraken.submit_orders([crypto_order])

asyncio.run(multi_exchange())




🔒 Security Best Practices

API Key Permissions

DO enable:
- ✅ Query Funds
- ✅ Query Open Orders & Trades
- ✅ Query Closed Orders & Trades
- ✅ Create & Modify Orders

DO NOT enable:
- ❌ Withdraw Funds (NEVER for bots!)
- ❌ Access WebSockets Auth Token (not needed)

IP Whitelisting

For production:
1. Go to https://www.kraken.com/u/security/api
2. Edit your API key
3. Add your server's IP address
4. Save changes

Key Storage

Development:

# .env file (already in .gitignore)
KRAKEN_API_KEY=your_key
KRAKEN_API_SECRET=your_secret


Production:
python
# OS keyring (more secure)
from src.brokers.credentials import BrokerCredentials

creds = BrokerCredentials.from_keyring()




📈 Rate Limits

Kraken has tiered rate limits based on verification level and trading volume.

Default Limits:
- Public API: ~1 request/second
- Private API: ~15 requests/second (increases with volume)
- Order Placement: ~20 orders/second

Using Rate Limiter:

python
from src.utils.rate_limiter import MultiEndpointRateLimiter

limiter = MultiEndpointRateLimiter({
    "/0/private/AddOrder": (15, 1.0),     # 15 orders/sec
    "/0/private/Balance": (10, 1.0),       # 10 req/sec
    "/0/public/Ticker": (1, 1.0),          # 1 req/sec
})

# Rate-limited order submission
async with limiter.limit("/0/private/AddOrder"):
    await adapter.submit_orders([order])




🐛 Troubleshooting

"API key not found"

Problem: Invalid API key

Solution:
1. Verify API key in `.env` matches Kraken
2. Check for extra spaces/newlines
3. Regenerate API key if needed

"Permission denied"

Problem: API key doesn't have required permissions

Solution:
1. Go to https://www.kraken.com/u/security/api
2. Edit API key
3. Enable required permissions:
   - Query Funds
   - Query Open Orders & Trades
   - Create & Modify Orders

"Invalid signature"

Problem: API secret is incorrect

Solution:
1. Verify `KRAKEN_API_SECRET` in `.env`
2. API secret should be base64-encoded (from Kraken)
3. Regenerate if you lost the original

"Rate limit exceeded"

Problem: Too many requests

Solution:
python
from src.utils.rate_limiter import AdaptiveRateLimiter

limiter = AdaptiveRateLimiter(max_requests=10, time_window=1.0)
async with limiter:
    await adapter.get_account()


"EOrder:Insufficient funds"

Problem: Not enough balance

Solution:
1. Check balance: `await adapter.get_account()`
2. Deposit more funds
3. Reduce order size



⚠️ Important Notes

Symbol Formats

- Your code: Use standard format (`BTC/USD`, `ETH/USD`)
- Adapter converts to Kraken format automatically
- If conversion fails, add to `_convert_symbol_to_kraken()`

Minimum Order Sizes

Kraken has minimum order sizes:
- BTC: 0.0001 BTC (~$4)
- ETH: 0.002 ETH (~$5)
- SOL: 0.5 SOL (~$50)

Check: https://support.kraken.com/hc/en-us/articles/205893708

Trading Fees

- Maker: 0.16% (add liquidity)
- Taker: 0.26% (take liquidity)
- Volume discounts: Available at higher tiers

Margin Trading

Current adapter uses spot trading only (no leverage).

For margin trading:
1. Enable margin in your Kraken account
2. Add leverage to orders: `order.leverage = 2.0`
3. ⚠️  High risk - can lose more than invested!



✅ Next Steps

1. Test Connection

python examples/test_kraken_connection.py


2. Paper Trade First

There's no Kraken testnet, but you can:
- Start with very small amounts ($10-50)
- Test all features with minimal risk
- Monitor for 1-2 weeks before scaling up

3. Start Live Trading

python examples/live_trading_kraken.py


4. Monitor Performance

- Check logs in `logs/` directory
- Monitor P&L daily
- Adjust risk limits as needed

5. Scale Up

Once confident:
- Increase position sizes gradually
- Add more trading pairs
- Optimize strategy parameters



📚 Resources

- Kraken API Docs: https://docs.kraken.com/rest/
- API Support: https://support.kraken.com/
- Trading Fees: https://www.kraken.com/features/fee-schedule
- Status Page: https://status.kraken.com/



🎯 Summary

You now have:

✅ Production-ready Kraken adapter
✅ Modern async/await patterns
✅ HMAC-SHA512 authentication
✅ Automatic symbol conversion
✅ Rate limiting support
✅ Connection testing
✅ Live trading examples

Your system can now trade 200+ cryptocurrencies on Kraken! 🚀

Start small, test thoroughly, and scale gradually. Crypto is volatile - always use proper risk management!



Happy trading! May your ML models find profitable asymmetries! 💰
