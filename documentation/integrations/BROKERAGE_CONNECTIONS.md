# Brokerage API Connection Guide

Complete guide for connecting to all supported brokers in your trading system.

---

## 📊 **Supported Brokers**

| Broker | Asset Classes | Status | Best For |
|--------|---------------|--------|----------|
| **Alpaca** | US Stocks, Crypto | ✅ Production | Beginners, US markets, crypto |
| **Binance** | Crypto (Spot) | ✅ Production | Crypto trading, high volume |
| **Kraken** | Crypto | 🔧 Framework Ready | Crypto, regulatory compliance |
| **Bybit** | Crypto Derivatives | 🔧 Framework Ready | Crypto futures, leverage |
| **Interactive Brokers** | Everything | 🔧 Framework Ready | Professional, global markets |
| **OANDA** | Forex | 🔧 Framework Ready | Forex, CFDs |
| **Tradier** | US Stocks | 🔧 Framework Ready | US stocks, options |

**Legend:**
- ✅ Production: Fully implemented and tested
- 🔧 Framework Ready: Configuration ready, need connector implementation

---

## 🚀 **Quick Start (Alpaca Paper Trading)**

**Fastest way to start trading (5 minutes):**

### **1. Create Alpaca Account**
- Go to: **https://app.alpaca.markets/signup**
- Sign up (free, no funding required for paper trading)
- Verify email

### **2. Get Paper Trading API Keys**
1. Go to **Paper Trading Dashboard**: https://app.alpaca.markets/paper/dashboard/overview
2. Click **"Your API Keys"** in left sidebar
3. Click **"Generate New Key"** or **"Regenerate Key"**
4. **Copy both keys immediately** (secret shown only once!)

### **3. Configure .env File**
```bash
# Copy example
cp .env.example .env

# Edit .env and add your keys:
ALPACA_API_KEY=PKxxxxxxxxxxxxxxxxxx
ALPACA_API_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ALPACA_PAPER=true
```

### **4. Test Connection**
```bash
source .venv/bin/activate
python examples/quick_connection_test.py
```

**Success looks like:**
```
✅ All connection tests passed!
📊 Account Info:
  - Buying Power: $100,000.00
  - Cash: $100,000.00
```

---

## 🔐 **Detailed Broker Setup**

### **1. Alpaca (US Stocks + Crypto)**

**What You Can Trade:**
- ✅ US Stocks (NYSE, NASDAQ)
- ✅ 20+ Cryptocurrencies (BTC, ETH, SOL, DOGE, etc.)
- ✅ Commission-free
- ✅ $100k paper trading account

**Get API Keys:**

**Paper Trading (Recommended):**
1. Dashboard: https://app.alpaca.markets/paper/dashboard/overview
2. Click **"Your API Keys"** → **"Generate New Key"**
3. Copy: `API Key ID` and `Secret Key`
4. Keys start with `PK` (paper) or `AK` (live)

**Live Trading:**
1. Complete account verification (SSN, address, bank)
2. Fund account (min $0, but realistic min ~$500)
3. Dashboard: https://app.alpaca.markets/live/dashboard/overview
4. Generate live API keys (start with `AK`)

**Configuration:**
```bash
# Paper Trading
ALPACA_API_KEY=PKE1234567890ABCDEF
ALPACA_API_SECRET=abc123def456ghi789jkl012mno345pqr678stu901
ALPACA_PAPER=true

# Live Trading (⚠️  Real Money!)
ALPACA_API_KEY=AKE1234567890ABCDEF
ALPACA_API_SECRET=abc123def456ghi789jkl012mno345pqr678stu901
ALPACA_PAPER=false
```

**OAuth2 (Advanced - Broker API):**
```bash
# For white-label broker solutions
ALPACA_OAUTH_CLIENT_ID=your_oauth_client_id
ALPACA_OAUTH_CLIENT_SECRET=your_oauth_client_secret
```

**Crypto Trading:**
- Automatically enabled in paper mode
- For live: Sign crypto agreement in dashboard
- Use "/" symbol format: `BTC/USD`, not `BTCUSD`

**Resources:**
- Signup: https://app.alpaca.markets/signup
- Docs: https://docs.alpaca.markets/
- API Reference: https://docs.alpaca.markets/reference
- Support: https://alpaca.markets/support

---

### **2. Binance (Crypto Spot)**

**What You Can Trade:**
- ✅ 500+ Cryptocurrencies
- ✅ High liquidity, low fees
- ✅ Spot trading (no leverage in this integration)

**Get API Keys:**

**Testnet (Recommended for Testing):**
1. Go to: https://testnet.binance.vision/
2. Login with GitHub
3. Generate API keys (free testnet tokens)

**Live Trading:**
1. Sign up: https://www.binance.com/
2. Complete KYC verification
3. API Management: https://www.binance.com/en/my/settings/api-management
4. Click **"Create API"**
5. Enable **"Enable Spot & Margin Trading"**
6. Whitelist IPs (optional but recommended)

**Configuration:**
```bash
# Testnet
BINANCE_API_KEY=your_testnet_api_key
BINANCE_API_SECRET=your_testnet_api_secret
BINANCE_TESTNET=true

# Live Trading (⚠️  Real Money!)
BINANCE_API_KEY=your_live_api_key
BINANCE_API_SECRET=your_live_api_secret
BINANCE_TESTNET=false
```

**Security:**
- ✅ Enable 2FA (Google Authenticator)
- ✅ Whitelist IP addresses
- ✅ Set withdrawal whitelist
- ⚠️  Never share API keys
- ⚠️  Use separate keys for trading bots

**Resources:**
- Signup: https://www.binance.com/
- Testnet: https://testnet.binance.vision/
- API Docs: https://binance-docs.github.io/apidocs/spot/en/

---

### **3. Kraken (Crypto Exchange)**

**What You Can Trade:**
- ✅ 200+ Cryptocurrencies
- ✅ Fiat pairs (USD, EUR, GBP, CAD)
- ✅ High security, regulatory compliance

**Get API Keys:**

1. Sign up: https://www.kraken.com/
2. Complete verification (Starter, Intermediate, or Pro)
3. Settings → API: https://www.kraken.com/u/security/api
4. Click **"Generate New Key"**
5. Permissions needed:
   - ✅ Query Funds
   - ✅ Query Open Orders & Trades
   - ✅ Query Closed Orders & Trades
   - ✅ Create & Modify Orders
   - ⚠️  Don't enable withdrawal for trading bots!

**Configuration:**
```bash
KRAKEN_API_KEY=your_kraken_api_key
KRAKEN_API_SECRET=your_kraken_api_secret
```

**Note:** Kraken connector implementation needed (framework ready).

**Resources:**
- Signup: https://www.kraken.com/
- API Docs: https://docs.kraken.com/rest/

---

### **4. Bybit (Crypto Derivatives)**

**What You Can Trade:**
- ✅ Crypto futures (perpetual & delivery)
- ✅ Spot trading
- ✅ Options
- ✅ Up to 100x leverage (⚠️  high risk!)

**Get API Keys:**

**Testnet (Recommended):**
1. Go to: https://testnet.bybit.com/
2. Register with email
3. API Management → Create New Key
4. Free testnet tokens available

**Live Trading:**
1. Sign up: https://www.bybit.com/
2. Complete KYC
3. API Management: https://www.bybit.com/app/user/api-management
4. Create API key
5. Permissions: Contract, Spot, Wallet (not Withdrawal)

**Configuration:**
```bash
# Testnet
BYBIT_API_KEY=your_testnet_api_key
BYBIT_API_SECRET=your_testnet_api_secret
BYBIT_TESTNET=true

# Live Trading (⚠️  Real Money + Leverage!)
BYBIT_API_KEY=your_live_api_key
BYBIT_API_SECRET=your_live_api_secret
BYBIT_TESTNET=false
```

**Note:** Bybit connector implementation needed (framework ready).

**Resources:**
- Signup: https://www.bybit.com/
- Testnet: https://testnet.bybit.com/
- API Docs: https://bybit-exchange.github.io/docs/

---

### **5. Interactive Brokers (IBKR - Everything)**

**What You Can Trade:**
- ✅ Stocks (global)
- ✅ Options, Futures, Forex
- ✅ Bonds, Mutual Funds
- ✅ 150+ markets, 33 countries

**Get API Access:**

**Paper Trading:**
1. Sign up: https://www.interactivebrokers.com/
2. Open Paper Trading Account
3. Download TWS or IB Gateway
4. Enable API connections in settings

**Configuration (TWS Gateway):**
```bash
IB_HOST=127.0.0.1
IB_PORT=7497  # 7497 for paper, 7496 for live
IB_CLIENT_ID=1
```

**Configuration (Web API OAuth):**
```bash
IBKR_CLIENT_ID=your_client_id
IBKR_CLIENT_SECRET=your_client_secret
```

**Setup Steps:**
1. Install TWS Gateway: https://www.interactivebrokers.com/en/trading/tws.php
2. Login to TWS Gateway
3. Configure API:
   - File → Global Configuration → API → Settings
   - ✅ Enable ActiveX and Socket Clients
   - ✅ Read-Only API: OFF
   - Socket port: 7497 (paper) or 7496 (live)
   - Trusted IPs: 127.0.0.1
4. Keep TWS Gateway running while trading

**Note:** IBKR connector implementation needed (framework ready).

**Resources:**
- Signup: https://www.interactivebrokers.com/
- TWS Download: https://www.interactivebrokers.com/en/trading/tws.php
- API Docs: https://interactivebrokers.github.io/tws-api/

---

### **6. OANDA (Forex)**

**What You Can Trade:**
- ✅ 68 currency pairs
- ✅ CFDs on indices, commodities, metals
- ✅ Up to 100:1 leverage (region dependent)

**Get API Keys:**

**Practice Account (Recommended):**
1. Sign up: https://www.oanda.com/
2. Login to fxTrade Practice
3. Account → Manage API Access
4. Generate Personal Access Token

**Live Trading:**
1. Open live account
2. Complete verification and fund
3. Generate live API token

**Configuration:**
```bash
# Practice
OANDA_API_KEY=your_practice_api_token
OANDA_ACCOUNT_ID=your_practice_account_id

# Live (⚠️  Real Money + Leverage!)
OANDA_API_KEY=your_live_api_token
OANDA_ACCOUNT_ID=your_live_account_id
```

**Note:** OANDA connector implementation needed (framework ready).

**Resources:**
- Signup: https://www.oanda.com/
- API Docs: https://developer.oanda.com/

---

### **7. Tradier (US Stocks)**

**What You Can Trade:**
- ✅ US Stocks (NYSE, NASDAQ)
- ✅ Options
- ✅ ETFs

**Get API Keys:**

**Sandbox (Recommended):**
1. Sign up: https://developer.tradier.com/
2. Get sandbox access token (free)
3. No account needed for sandbox

**Live Trading:**
1. Open brokerage account: https://tradier.com/
2. Developer → Create Application
3. Get production access token

**Configuration:**
```bash
# Sandbox
TRADIER_ACCESS_TOKEN=your_sandbox_token

# Live (⚠️  Real Money!)
TRADIER_ACCESS_TOKEN=your_production_token
```

**Note:** Tradier connector implementation needed (framework ready).

**Resources:**
- Signup: https://developer.tradier.com/
- API Docs: https://documentation.tradier.com/

---

## 🔒 **Security Best Practices**

### **API Key Security**

**DO:**
- ✅ Use paper/testnet accounts first
- ✅ Generate separate API keys for each application
- ✅ Enable IP whitelisting when available
- ✅ Set minimal required permissions
- ✅ Store keys in `.env` file (never commit to git!)
- ✅ Use OS keyring for production (see below)
- ✅ Rotate keys regularly (every 90 days)
- ✅ Enable 2FA on all broker accounts

**DON'T:**
- ❌ Share API keys with anyone
- ❌ Commit `.env` to version control
- ❌ Enable withdrawal permissions for bots
- ❌ Use live keys for testing
- ❌ Store keys in code files
- ❌ Reuse keys across multiple bots
- ❌ Disable 2FA

### **Using OS Keyring (More Secure)**

Instead of `.env`, store credentials in your OS keyring:

**Setup:**
```bash
# Install keyring tool
pip install keyring

# Store credentials (run once)
keyring set trading_system alpaca_api_key
# Enter your API key when prompted

keyring set trading_system alpaca_api_secret
# Enter your API secret when prompted
```

**Load from keyring:**
```python
from src.brokers.credentials import BrokerCredentials

# Loads from OS keyring instead of .env
creds = BrokerCredentials.from_keyring()
```

**Benefits:**
- ✅ Encrypted by OS
- ✅ No plaintext files
- ✅ Safer for production

---

## 📝 **Configuration Reference**

### **Complete .env Template**

```bash
# ============================================================================
# BROKER CREDENTIALS (Choose what you need)
# ============================================================================

# 1. ALPACA (US Stocks + Crypto) - Recommended for beginners
ALPACA_API_KEY=your_alpaca_key_here
ALPACA_API_SECRET=your_alpaca_secret_here
ALPACA_PAPER=true  # true for paper, false for live

# Alpaca OAuth2 (optional - for Broker API)
ALPACA_OAUTH_CLIENT_ID=
ALPACA_OAUTH_CLIENT_SECRET=

# 2. BINANCE (Crypto Spot)
BINANCE_API_KEY=your_binance_key_here
BINANCE_API_SECRET=your_binance_secret_here
BINANCE_TESTNET=true  # true for testnet, false for mainnet

# 3. KRAKEN (Crypto Exchange)
KRAKEN_API_KEY=
KRAKEN_API_SECRET=

# 4. BYBIT (Crypto Derivatives)
BYBIT_API_KEY=
BYBIT_API_SECRET=
BYBIT_TESTNET=true  # true for testnet, false for mainnet

# 5. INTERACTIVE BROKERS (Everything)
IB_HOST=127.0.0.1
IB_PORT=7497  # 7497 for paper, 7496 for live
IB_CLIENT_ID=1

# IBKR Web API OAuth2 (alternative to TWS)
IBKR_CLIENT_ID=
IBKR_CLIENT_SECRET=

# 6. OANDA (Forex)
OANDA_API_KEY=
OANDA_ACCOUNT_ID=

# 7. TRADIER (US Stocks)
TRADIER_ACCESS_TOKEN=

# ============================================================================
# TRADING CONFIGURATION
# ============================================================================

TRADING_MODE=paper  # paper, live
TARGET_WEALTH=500000
STARTING_CAPITAL=5000
TIME_HORIZON_DAYS=365

# Risk limits
MAX_POSITION_PCT=0.30
MAX_LEVERAGE=2.0
MAX_DAILY_LOSS_PCT=0.10
MAX_DRAWDOWN_PCT=0.50

# Position sizing
KELLY_FRACTION=0.50
MIN_CONVEXITY_SCORE=0.10
MAX_CONCURRENT_POSITIONS=3

# ============================================================================
# CRYPTO TRADING (if using crypto)
# ============================================================================

ENABLE_CRYPTO=true
CRYPTO_SYMBOLS=BTC/USD,ETH/USD,SOL/USD
CRYPTO_MAX_POSITION_PCT=0.20
CRYPTO_MAX_DAILY_LOSS_PCT=0.08
CRYPTO_MAX_DRAWDOWN_PCT=0.40

# ============================================================================
# LOGGING & SAFETY
# ============================================================================

LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT=json  # json for production, text for development

ENABLE_CIRCUIT_BREAKERS=true
HALT_ON_DAILY_LOSS=true
HALT_ON_DRAWDOWN=true
VALIDATE_ORDERS=true
DRY_RUN=false  # true to log orders without executing
```

### **Minimal .env (Alpaca Only)**

```bash
# Just Alpaca paper trading
ALPACA_API_KEY=PKE1234567890ABCDEF
ALPACA_API_SECRET=abc123def456ghi789jkl012mno345pqr678
ALPACA_PAPER=true

# Trading config
TRADING_MODE=paper
TARGET_WEALTH=500000
STARTING_CAPITAL=5000
```

---

## 🧪 **Testing Your Connection**

### **Quick Test**
```bash
source .venv/bin/activate
python examples/quick_connection_test.py
```

**Expected output:**
```
✅ All connection tests passed!
📊 Account Info:
  - Buying Power: $100,000.00
  - Cash: $100,000.00
  - Portfolio Value: $100,000.00
```

### **Full Test (Interactive)**
```bash
python examples/test_broker_connection.py
```

### **Test Specific Features**

**Test SSE Streaming:**
```bash
python examples/test_sse_streaming.py
```

**Test Crypto Trading:**
```bash
python examples/list_crypto_assets.py
python examples/test_crypto_order.py
```

---

## 🐛 **Troubleshooting**

### **401 Unauthorized**

**Problem:** `{"message": "unauthorized."}`

**Solutions:**
1. ✅ Verify API keys are correct (no extra spaces)
2. ✅ Check paper/live mode matches keys
3. ✅ Regenerate API keys on broker website
4. ✅ Check API key permissions (trading enabled)
5. ✅ For Alpaca: Paper keys start with `PK`, live with `AK`

### **403 Forbidden**

**Problem:** API access denied

**Solutions:**
1. ✅ Check IP whitelist settings
2. ✅ Verify API key permissions
3. ✅ For IBKR: Enable API in TWS settings
4. ✅ For Binance: Enable "Spot & Margin Trading"

### **Connection Timeout**

**Problem:** Cannot connect to broker

**Solutions:**
1. ✅ Check internet connection
2. ✅ For IBKR: Ensure TWS Gateway is running
3. ✅ Check firewall settings
4. ✅ Try different network (VPN may block some APIs)

### **Rate Limit Errors**

**Problem:** `429 Too Many Requests`

**Solutions:**
1. ✅ System has built-in rate limiting - should auto-handle
2. ✅ Reduce trading frequency if custom code
3. ✅ Check if multiple instances running
4. ✅ Wait 60 seconds and retry

### **ModuleNotFoundError**

**Problem:** Missing Python packages

**Solutions:**
```bash
source .venv/bin/activate
uv pip install -e ".[exchange]"
```

---

## 📚 **Additional Resources**

### **Documentation**
- **Architecture Guide**: `MODERN_BROKER_ARCHITECTURE.md`
- **Integration Summary**: `2025_INTEGRATION_SUMMARY.md`
- **SSE Streaming**: `SSE_STREAMING_GUIDE.md`
- **Crypto Trading**: `CRYPTO_TRADING_GUIDE.md`

### **Example Code**
- `examples/quick_connection_test.py` - Fast connection test
- `examples/test_broker_connection.py` - Full interactive test
- `examples/live_trading_example.py` - Live stock trading
- `examples/live_trading_crypto.py` - Live crypto trading
- `examples/test_sse_streaming.py` - Real-time event streaming

### **Broker Websites**
- Alpaca: https://alpaca.markets/
- Binance: https://www.binance.com/
- Kraken: https://www.kraken.com/
- Bybit: https://www.bybit.com/
- Interactive Brokers: https://www.interactivebrokers.com/
- OANDA: https://www.oanda.com/
- Tradier: https://tradier.com/

---

## 🎯 **Recommended Path**

### **For Beginners:**
1. ✅ Start with **Alpaca Paper Trading** (free, instant)
2. ✅ Test strategies for 1-3 months
3. ✅ Move to Alpaca live with small capital ($500-1000)
4. ✅ Add other brokers as needed

### **For Crypto Traders:**
1. ✅ Start with **Binance Testnet** or **Alpaca Paper**
2. ✅ Test crypto strategies
3. ✅ Move to live with small position sizes
4. ✅ Add Kraken/Bybit for diversification

### **For Professional Traders:**
1. ✅ **Interactive Brokers** for global markets
2. ✅ **Alpaca** for US stocks/crypto
3. ✅ **OANDA** for forex
4. ✅ Use multiple brokers for redundancy

---

## ⚠️ **Important Warnings**

### **Paper vs Live Trading**

**Paper Trading:**
- ✅ No real money at risk
- ✅ Perfect for testing strategies
- ✅ Instant access
- ❌ No real execution risk (fills always execute)
- ❌ May not reflect real market conditions
- ❌ No slippage/partial fills

**Live Trading:**
- ⚠️  **REAL MONEY AT RISK**
- ⚠️  **CAN LOSE YOUR ENTIRE ACCOUNT**
- ⚠️  **START SMALL** ($500-1000 max)
- ⚠️  **TEST THOROUGHLY IN PAPER FIRST**
- ⚠️  **NEVER RISK MONEY YOU CAN'T AFFORD TO LOSE**

### **Leverage Warning**

**Using leverage (margin, futures, forex):**
- ⚠️  **CAN LOSE MORE THAN YOU INVEST**
- ⚠️  **EXTREMELY HIGH RISK**
- ⚠️  **NOT RECOMMENDED FOR BEGINNERS**
- ⚠️  This system defaults to 1x-2x leverage (conservative)
- ⚠️  Crypto futures can use 100x+ leverage = **INSTANT LIQUIDATION RISK**

**Recommended:**
- ✅ Start with **NO LEVERAGE** (1x)
- ✅ Max 2x leverage for stocks
- ✅ Max 1x for crypto (spot only)
- ✅ Understand liquidation mechanics before using leverage

---

## ✅ **Quick Checklist**

Before starting live trading:

- [ ] ✅ Tested in paper/testnet for 1+ month
- [ ] ✅ Strategy shows consistent profitability
- [ ] ✅ Understand all risks
- [ ] ✅ Using risk limits (MAX_DAILY_LOSS_PCT, MAX_DRAWDOWN_PCT)
- [ ] ✅ Starting with small capital you can afford to lose
- [ ] ✅ Have stop-loss mechanisms in place
- [ ] ✅ Monitoring system is working (logs, alerts)
- [ ] ✅ API keys have minimal permissions (no withdrawal)
- [ ] ✅ 2FA enabled on all broker accounts
- [ ] ✅ .env file is NOT committed to git
- [ ] ✅ Understand tax implications of trading

---

**Your path to $500k starts with a single API connection!** 🚀

But remember: **Always test in paper trading first. Never risk money you can't afford to lose.**

For support, see: `README.md` or https://github.com/anthropics/claude-code/issues
