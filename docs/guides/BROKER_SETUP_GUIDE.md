Broker Setup & Deployment Guide

Complete guide to connecting your trading system to live brokers.

🎯 Overview

Your system now supports:

| Broker              | Asset Class  | Best For                  | Paper Trading |
|                   --|             -|                          -|               |
| Alpaca              | US Stocks    | Testing, small accounts   | ✅ Free       |
| Binance             | Crypto       | High volatility, leverage | ✅ Testnet    |
| Interactive Brokers | Everything   | Professional trading      | ✅ Via TWS    |



📋 Prerequisites

Before connecting to brokers:

- ✅ System fully tested with backtests
- ✅ Paper trading validated (30+ days)
- ✅ Risk management tested
- ✅ Emergency procedures documented
- ✅ Can afford to lose capital



🔐 Step 1: Get API Credentials

Option A: Alpaca (Stocks) - Recommended for Testing

1. Sign up: https://alpaca.markets
2. Create API keys:
   - Go to Paper Trading dashboard
   - Generate API Key & Secret
   - Save immediately(secret shown once only)

3. Permissions needed:
   - ✅ Trading
   - ✅ Account Data
   - ❌ NOT needed: Account Configurations

Cost: Free paper trading, $0 commissions live


Option B: Binance (Crypto) - For Aggressive Strategies

1. Sign up: https://www.binance.com
2. Enable 2FA: Security → Two-Factor Authentication
3. Create API keys:
   - Account → API Management
   - Create API Key
   - Save Key + Secret

4. Permissions:
   - ✅ Enable Spot & Margin Trading
   - ❌ Disable Withdrawals (security)
   - ✅ Enable Reading
   - ✅ Restrict to your IP (recommended)

5. Testnet (recommended first):
   - https://testnet.binance.vision
   - Free test funds
   - Same API, no risk

Cost: 0.1% maker/taker fees (use BNB for discount)


Option C: Interactive Brokers (Professional)

1. Open account: https://www.interactivebrokers.com
2. Download TWS or IB Gateway
3. Enable API:
   - Account Management → Settings → API
   - Enable ActiveX and Socket Clients

4. Paper trading:
   - Request paper trading account
   - Login with separate credentials

Cost: $0.005/share (stocks), varies by product


⚙️ Step 2: Configure Your System

Create .env File

bash
cd /mnt/c/Users/catty/Desktop/money_machine

# Copy template
cp .env.example .env

# Edit with your credentials
nano .env  # or your preferred editor


Fill In Credentials

bash
# For Alpaca
ALPACA_API_KEY=PK...  # Your key
ALPACA_API_SECRET=...  # Your secret
ALPACA_PAPER=true  # KEEP AS TRUE initially!

# For Binance
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
BINANCE_TESTNET=true  # KEEP AS TRUE initially!

# Trading Config
TRADING_MODE=paper
TARGET_WEALTH=500000
STARTING_CAPITAL=5000
MAX_LEVERAGE=2.0
DRY_RUN=false  # Set true to test without executing


⚠️ IMPORTANT:
- Never commit `.env` to git
- Use paper/testnet initially
- Store secrets securely
- Rotate keys periodically



🧪 Step 3: Test Connection

Install Broker SDKs

bash
source .venv/bin/activate

# For Alpaca
uv pip install alpaca-py

# For Binance
uv pip install python-binance

# For data (if not installed)
uv pip install yfinance python-dotenv


Run Connection Test

bash
python examples/test_broker_connection.py


Expected output:

TESTING ALPACA CONNECTION
================================
✓ Loaded config (paper=True)
✓ Initialized adapter

Account Information:
  Cash: $100,000.00
  Equity: $100,000.00
  Buying Power: $200,000.00

✓ Alpaca connection successful!


If it fails:
1. Check API keys in `.env`
2. Verify internet connection
3. Check broker status page
4. Ensure paper/testnet mode enabled

Test Real-Time Streaming (Optional but Recommended)

Your system uses Alpaca's SSE (Server-Sent Events) for real-time updates:

bash
# Install SSE dependencies
uv pip install httpx httpx-sse

# Test real-time event streaming
python examples/test_sse_streaming.py


What this does:
- Monitors trade fills in real-time (no 1-second polling delay)
- Shows account status updates as they happen
- Displays non-trade activities (dividends, splits)

Expected output:

TESTING TRADE EVENT STREAM
================================
Monitoring for 30 seconds...
Submit a test order in another terminal to see events

[13:30:00.658] FILL: AAPL buy 0.05513895 - filled
           Fill: 0.05513895 @ $181.36, Position: 0.05513895


Benefits of SSE:
- ⚡ Lower latency: Events pushed immediately (not polled)
- 📉 More efficient: Single connection vs repeated requests
- 🎯 More accurate: See exact order lifecycle (new → fill)

If SSE dependencies aren't installed, system automatically falls back to polling.



🚀 Step 4: Paper Trading

Run Paper Trading

bash
python examples/live_trading_example.py


This will:
1. Connect to broker
2. Load your aggressive ML policy
3. Start scanning for convexity
4. Execute trades (paper money)
5. Log all activity

What to Monitor

| Metric | Check | Action |
|--|-|--|
| Win Rate | > 20% | If < 10%, review ML |
| Sharpe | > 0.5 | If negative, pause |
| Max DD | < 50% | If > 80%, reduce leverage |
| Order Fill Rate | > 80% | If low, adjust limit prices |

Paper trade for minimum 30 days before live.



💰 Step 5: Going Live (When Ready)

Pre-Flight Checklist

- [ ] Paper trading profitable for 30+ days
- [ ] Win rate validated (>20% for aggressive)
- [ ] Max drawdown acceptable (<50%)
- [ ] ML finding genuine convexity
- [ ] Risk limits tested (circuit breakers work)
- [ ] Emergency stop procedure documented
- [ ] Starting with <10% of intended capital
- [ ] Can afford to lose 100% of capital
- [ ] Will monitor continuously
- [ ] Family/obligations accounted for

If ANY box unchecked, DO NOT go live.

Enable Live Trading

bash
# Edit .env
ALPACA_PAPER=false  # ⚠️ REAL MONEY!
TRADING_MODE=live

# Or for Binance
BINANCE_TESTNET=false  # ⚠️ REAL MONEY!


Start Small


Week 1: 10% of intended capital
Week 2: If profitable, 20%
Week 3: If profitable, 40%
Week 4: If profitable, 80%
Week 5+: Full capital


Scaling Rule:Only increase if previous week was profitable.

Run Live

bash
# Triple-check config
cat .env | grep PAPER
cat .env | grep TESTNET

# If both show false, you're going live
python examples/live_trading_example.py




🛡️ Safety Mechanisms

Built-In Protections

Your system has:

1. Position Limits
   - Max 30% per position (configured in .env)
   - Max 2x leverage
   - Max 3 concurrent positions

2. Circuit Breakers
   - Stops at 10% daily loss
   - Stops at 50% total drawdown
   - Cannot be overridden

3. Order Validation
   - Checks before every order
   - Rejects oversized orders
   - Validates cash available

Manual Overrides

Emergency Stop:
bash
# Press Ctrl+C in terminal
# Then:
python -c "
from src.brokers.alpaca_adapter import AlpacaAdapter
from src.brokers.config import AlpacaConfig
import asyncio

async def emergency_stop():
    config = AlpacaConfig.from_env()
    adapter = AlpacaAdapter(config.api_key, config.api_secret, paper=config.paper)
    await adapter.cancel_all_orders()
    print('All orders cancelled')

asyncio.run(emergency_stop())
"


Check Positions:
bash
python -c "
from src.brokers.alpaca_adapter import AlpacaAdapter
from src.brokers.config import AlpacaConfig
import asyncio

async def check():
    config = AlpacaConfig.from_env()
    adapter = AlpacaAdapter(config.api_key, config.api_secret, paper=config.paper)
    positions = await adapter.get_positions()
    account = await adapter.get_account()
    print(f'Equity: \${account[\"equity\"]:,.2f}')
    print(f'Positions: {positions}')

asyncio.run(check())
"




📊 Monitoring & Logging

View Logs

Logs are output to console. For production:

bash
# Run with logging to file
python examples/live_trading_example.py 2>&1 | tee trading.log

# Monitor in real-time
tail -f trading.log | grep ERROR


Key Events to Watch


✓ GOOD:
- order.submitted
- order.filled
- fill.received
- health.check status=ok

⚠️ WARNING:
- order.rejected (check buying power)
- policy.error (ML issue)
- market_data.error (connection issue)

❌ CRITICAL:
- trading.halted (circuit breaker!)
- risk.violation (limit breach)
- engine.error (system failure)


Metrics Dashboard (Optional)

Add to your system:

bash
# Install Prometheus + Grafana
# Metrics exported on :9090
# Visualize: P&L, win rate, drawdown




🚨 Common Issues

"Invalid API Key"
- Check `.env` has correct keys
- Verify no extra spaces
- Regenerate keys if old

"Insufficient Buying Power"
- Position size too large
- Reduce MAX_POSITION_PCT
- Or increase capital

"Order Rejected"
- Check symbol is tradable
- Verify market is open
- Ensure fractional shares allowed (if needed)

"No Convexity Found"
- ML not finding opportunities
- Try different symbols
- Adjust MIN_CONVEXITY_SCORE
- Improve feature engineering

"Circuit Breaker Triggered"
- You hit loss limit (by design!)
- Review what went wrong
- Adjust strategy if needed
- Reset: `risk_mgr.resume_trading()`



📈 Performance Tracking

Daily Review Checklist

- [ ] Check P&L vs target
- [ ] Review trades (winning/losing)
- [ ] Validate ML predictions (did convexity pay off?)
- [ ] Check drawdown vs limits
- [ ] Review any errors in logs
- [ ] Adjust if needed

Weekly Deep Dive

- [ ] Calculate Sharpe ratio
- [ ] Analyze win rate by symbol
- [ ] Review max drawdown
- [ ] Validate edge still exists
- [ ] Retrain ML model if needed

Monthly Assessment

- [ ] Are we on track for target?
- [ ] Is strategy still working?
- [ ] Should we adjust aggression?
- [ ] Do we need more capital?
- [ ] Should we try again?



⚡ Advanced: Running 24/7

For continuous operation:

Option 1: Screen/Tmux

bash
# Start screen session
screen -S trading

# Run bot
python examples/live_trading_example.py

# Detach: Ctrl+A, D
# Reattach: screen -r trading


Option 2: Systemd Service

bash
# Create /etc/systemd/system/trading-bot.service
[Unit]
Description=Trading Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/money_machine
ExecStart=/path/to/.venv/bin/python examples/live_trading_example.py
Restart=on-failure

[Install]
WantedBy=multi-user.target

# Enable
sudo systemctl enable trading-bot
sudo systemctl start trading-bot


Option 3: Docker

dockerfile
FROM python:3.12
WORKDIR /app
COPY . .
RUN pip install uv && uv pip install -e ".[dev]"
CMD ["python", "examples/live_trading_example.py"]




🎯 Recommended Workflow

Phase 1: Validation (Weeks 1-4)
1. ✅ Backtest on 2+ years data
2. ✅ Paper trade Alpaca (30 days)
3. ✅ Verify win rate > 20%
4. ✅ Confirm can handle variance

Phase 2: Small Scale (Weeks 5-8)
1. ✅ Live with $500 (10% of $5k)
2. ✅ Monitor daily
3. ✅ Validate fills match expectations
4. ✅ Scale if profitable

Phase 3: Full Scale (Weeks 9-12)
1. ✅ Live with full capital
2. ✅ Monitor for first week
3. ✅ Let system run
4. ✅ Make attempt at 100x

Phase 4: Iterate (Ongoing)
- If successful: Scale up, compound
- If failed: Analyze, improve ML, try again
- Expected: 2-5 attempts to hit target



🔥 Final Warnings

1. This is aggressive trading
   - Expect 50-80% drawdowns
   - You WILL have losing streaks
   - Most people can't handle this

2. Start with paper trading
   - Minimum 30 days
   - Validate everything works
   - Don't skip this step

3. Use risk capital only
   - Money you can afford to lose
   - Not rent, not savings
   - Treat as high-risk venture

4. Monitor continuously
   - Especially first week live
   - Check logs daily
   - Be ready to stop

5. Have exit plan
   - What if you lose 50%?
   - How many attempts?
   - When to quit?



✅ You're Ready When...

- [✓] Paper trading profitable for 30+ days
- [✓] You understand the math (target-utility)
- [✓] You can stomach 50%+ drawdowns
- [✓] You have 5-10 attempts worth of capital
- [✓] Your ML finds genuine convexity
- [✓] You've tested all safety mechanisms
- [✓] You have emergency procedures
- [✓] Your family/obligations are secure

If all checked: Execute the plan.
If not: Keep testing.

Remember: The math works over multiple attempts. Be patient. Be disciplined.

Good luck! 🚀💰
