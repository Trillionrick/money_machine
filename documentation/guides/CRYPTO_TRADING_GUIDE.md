# Alpaca Crypto Trading Guide

Complete guide to trading cryptocurrencies 24/7 with your aggressive ML system.

---

## 🎯 **Overview**

**Why Crypto?**
- ✅ **24/7 Trading** - Markets never close (perfect for convexity hunting)
- ✅ **High Volatility** - Large price swings = more convex payoffs
- ✅ **Low Minimums** - Start with small capital ($1+ orders)
- ✅ **Fractional Trading** - Trade 0.000000001 BTC
- ✅ **No Pattern Day Trader Rules** - Trade as much as you want

**Supported Assets:**
- **20+ Cryptocurrencies** including BTC, ETH, SOL, USDC, USDT
- **Trading Pairs:** USD, BTC, ETH, USDC, USDT pairs
- **All Fractionable** - No need to buy whole coins

---

## 🚀 **Quick Start**

### **Step 1: Enable Crypto (One-Time Setup)**

Your Alpaca account needs crypto enabled. This happens automatically in **paper mode** (already enabled for testing).

For **live trading**, you'll need to:
1. Sign crypto agreement (via API or dashboard)
2. Wait for `crypto_status` to become `ACTIVE`

**Check your crypto status:**
```bash
source .venv/bin/activate
python -c "
import asyncio
from src.brokers.alpaca_adapter import AlpacaAdapter
from src.brokers.config import AlpacaConfig

async def check_crypto():
    config = AlpacaConfig.from_env()
    adapter = AlpacaAdapter(config.api_key, config.api_secret, paper=config.paper)
    account = await adapter.get_account()
    print(f'Crypto Status: {account.get(\"crypto_status\", \"INACTIVE\")}')

asyncio.run(check_crypto())
"
```

**Expected output:**
```
Crypto Status: ACTIVE  # ✅ Ready to trade!
```

### **Step 2: List Available Cryptocurrencies**

```bash
python examples/list_crypto_assets.py
```

You'll see:
```
Available Crypto Assets:
  BTC/USD  - Bitcoin         (fractionable, min: 0.00000001)
  ETH/USD  - Ethereum        (fractionable, min: 0.00000001)
  SOL/USD  - Solana          (fractionable, min: 0.00000001)
  USDC/USD - USD Coin        (fractionable, min: 0.00000001)
  ...
```

### **Step 3: Test Crypto Order**

```bash
python examples/test_crypto_order.py
```

This will:
1. Check crypto status
2. Submit small test order (e.g., $10 of BTC)
3. Show real-time fill via SSE
4. Display position

---

## 📊 **Trading Crypto**

### **Key Differences from Stocks**

| Feature | Stocks | Crypto |
|---------|--------|--------|
| **Trading Hours** | 9:30 AM - 4:00 PM ET (M-F) | **24/7/365** |
| **Order Types** | Market, Limit, Stop, Stop-Limit | Market, Limit, Stop-Limit |
| **Time in Force** | DAY, GTC, IOC, FOK | **GTC, IOC only** |
| **Minimum Order** | $1 (notional) | **$1 (notional)** |
| **Fractional** | Yes (some stocks) | **Yes (all crypto)** |
| **Precision** | Up to 6 decimals | **Up to 9 decimals** |
| **Margin** | Yes (2x+) | **No (cash only)** |
| **Short Selling** | Yes | **No** |
| **PDT Rule** | Yes ($25k min) | **No restriction** |

### **Symbol Format**

**Format:** `BASE/QUOTE`
- `BTC/USD` - Bitcoin priced in US Dollars
- `ETH/BTC` - Ethereum priced in Bitcoin
- `SOL/USDC` - Solana priced in USD Coin

**Always use the full symbol with slash!**

### **Order Sizing**

**Three ways to specify quantity:**

1. **Quantity (qty)** - Number of coins
   ```python
   Order(symbol="BTC/USD", side=Side.BUY, quantity=0.001)  # 0.001 BTC
   ```

2. **Notional** - Dollar amount
   ```python
   Order(symbol="BTC/USD", side=Side.BUY, notional=50.0)  # $50 worth of BTC
   ```

3. **Percentage** - Percent of buying power
   ```python
   # Not directly supported - calculate manually
   buying_power = account['buying_power']
   notional = buying_power * 0.10  # 10% of buying power
   ```

**Minimum Order Sizes:**
- **USD pairs:** $1 minimum
- **BTC/ETH/USDT pairs:** 0.000000002 minimum
- **Max order:** $200,000 per order

**Precision:**
- All crypto supports **up to 9 decimal places**
- Example: `0.000000001` is valid

### **Supported Order Types**

| Order Type | Description | Use Case |
|------------|-------------|----------|
| **Market** | Execute immediately at best price | Quick entry/exit |
| **Limit** | Execute at specific price or better | Price control |
| **Stop Limit** | Trigger at stop price, execute as limit | Stop-loss with control |

**NOT supported:** Stop-Market, Trailing Stop

### **Time in Force**

| TIF | Description | Crypto Support |
|-----|-------------|----------------|
| **GTC** | Good Till Canceled | ✅ Yes |
| **IOC** | Immediate or Cancel | ✅ Yes |
| **DAY** | Cancel at end of day | ❌ No (use GTC) |
| **FOK** | Fill or Kill | ❌ No |

**For crypto, use:**
- `GTC` for most orders (stays open until filled or canceled)
- `IOC` for immediate execution or cancel remainder

---

## 🎰 **Crypto for Aggressive Strategies**

### **Why Crypto Fits Your System**

Your aggressive ML policy is **perfect for crypto**:

1. **High Volatility = High Convexity**
   - Crypto has 5-10x more volatility than stocks
   - More frequent large moves (skewed payoffs)
   - Your ML convexity detector will find more opportunities

2. **24/7 Trading = More Attempts**
   - Markets never close
   - 3x more trading hours than stocks
   - More chances to hit 100x target

3. **No Pattern Day Trader Rules**
   - Trade as aggressively as you want
   - No $25k minimum
   - Unlimited day trades

4. **Lower Transaction Costs**
   - Commission-free at Alpaca
   - Only spread costs (typically 0.05-0.2%)

### **Crypto Assets by Volatility**

**High Volatility (Best for Convexity):**
- **DOGE/USD** - 10-20% daily moves
- **SHIB/USD** - 8-15% daily moves
- **SOL/USD** - 5-10% daily moves
- **BTC/USD** - 3-8% daily moves

**Medium Volatility:**
- **ETH/USD** - 3-6% daily moves
- **AVAX/USD** - 4-8% daily moves

**Low Volatility (Liquidity):**
- **USDC/USD** - ~0% (stablecoin)
- **USDT/USD** - ~0% (stablecoin)

**Recommended for aggressive trading:**
Start with **BTC/USD** or **ETH/USD** (high liquidity, medium-high volatility)

### **Example Strategy Configuration**

**In your live trading example:**

```python
# Crypto-optimized settings
symbols = ["BTC/USD", "ETH/USD", "SOL/USD"]
policy = AdaptiveAggressivePolicy(
    symbols=symbols,
    target_wealth=500_000,
    current_wealth=5_000,
    time_horizon_days=365,
    max_positions=3,
    min_convexity_score=0.15,  # Higher for crypto volatility
    max_leverage=1.0,  # Crypto is cash-only
)
```

**Key adjustments for crypto:**
- ✅ `max_leverage=1.0` (no margin for crypto)
- ✅ `min_convexity_score=0.15` (higher threshold for volatile assets)
- ✅ `max_position_pct=0.30` (same aggressive sizing)

---

## 💰 **Crypto Wallets (Advanced)**

### **Overview**

Alpaca offers **crypto wallet functionality** for deposits/withdrawals:
- Deposit crypto from external wallets
- Withdraw crypto to external wallets
- Trade between crypto and USD

**Note:** Requires enablement by Alpaca (contact them).

### **Deposit Flow**

1. **Generate funding wallet:**
   ```python
   GET /v1/crypto/funding_wallets?asset=USDC&network=ethereum
   ```

2. **Get your address:**
   ```json
   {
     "address": "0x42a76C83014e886e639768D84EAF3573b1876844"
   }
   ```

3. **Send crypto to this address** (from Coinbase, MetaMask, etc.)

4. **Wait for confirmations** (~12 blocks, 2-3 minutes)

5. **Monitor via SSE:**
   - Event type: `OCT` (Other Crypto Transaction)
   - Status: `PROCESSING` → `COMPLETE`

### **Withdrawal Flow**

1. **Whitelist destination address** (security requirement):
   ```python
   POST /v1/accounts/{account_id}/wallets/whitelists
   {"address": "0x...", "asset": "USDC"}
   ```

2. **Wait for approval** (up to 24 hours in live, instant in sandbox)

3. **Request withdrawal:**
   ```python
   POST /v1/accounts/{account_id}/wallets/transfers
   {"amount": "100", "address": "0x...", "asset": "USDC"}
   ```

4. **Monitor status:**
   - `PROCESSING` - Submitted to blockchain
   - `COMPLETE` - Funds transferred
   - `FAILED` - Transaction failed

### **Fees**

- **Network fees:** Paid to blockchain (variable)
- **Alpaca fees:** Configured per broker (typically 0.5-1%)

**Example:**
- Withdraw 100 USDC
- Network fee: ~20 USDC (Ethereum gas)
- Alpaca fee: 0.3025 USDC (0.3%)
- **You receive:** ~79.70 USDC

---

## 🛡️ **Risk Management for Crypto**

### **Additional Risks**

Crypto adds these risks vs stocks:

1. **24/7 Volatility**
   - Large moves can happen overnight
   - No "market closed" safe period
   - **Solution:** Tighter stop-losses, smaller position sizes

2. **Higher Volatility**
   - 50%+ daily drops are possible
   - Flash crashes more common
   - **Solution:** Increase `min_convexity_score`, reduce `max_position_pct`

3. **Liquidity Varies**
   - BTC/ETH very liquid
   - Small coins can have wide spreads
   - **Solution:** Stick to top 5-10 coins

4. **Exchange Risk**
   - Crypto exchanges can be hacked
   - Alpaca uses multiple venues (reduces risk)
   - **Solution:** Don't hold large balances long-term

### **Recommended Risk Limits for Crypto**

**More conservative than stocks:**

```python
RiskLimits(
    max_position_pct=0.20,      # 20% max per position (vs 30% for stocks)
    max_leverage=1.0,            # No leverage (crypto is cash-only)
    max_daily_loss_pct=0.08,    # 8% daily loss limit (vs 10% for stocks)
    max_drawdown_pct=0.40,      # 40% max drawdown (vs 50% for stocks)
)
```

**Why more conservative?**
- Crypto is MORE volatile
- Your aggressive strategy is already high-risk
- Crypto + aggressive = need extra safety

### **Circuit Breakers**

Your existing circuit breakers work for crypto:
- ✅ Daily loss limit (8%)
- ✅ Max drawdown (40%)
- ✅ Position limits (20% per position)

**Additional for crypto:**
- Set `min_convexity_score=0.15` (higher than 0.10 for stocks)
- Monitor 24/7 (unlike stocks which close)

---

## 📈 **Performance Tracking**

### **Crypto-Specific Metrics**

In addition to standard metrics:

| Metric | Target (Aggressive) | Notes |
|--------|---------------------|-------|
| **Sharpe Ratio** | > 0.3 | Lower than stocks (more volatile) |
| **Max Drawdown** | < 60% | Higher than stocks (expected) |
| **Win Rate** | > 15% | Lower than stocks (bigger swings) |
| **Avg Win / Avg Loss** | > 3.0 | Need big wins to offset losses |

**Crypto volatility means:**
- Lower win rate acceptable (15% vs 20% for stocks)
- Larger drawdowns expected (60% vs 50%)
- But bigger wins when you hit (10x+ vs 2-3x)

### **Daily Monitoring**

**Check these daily:**
- [ ] Current drawdown (< 40%?)
- [ ] Yesterday's P&L (within limits?)
- [ ] Open positions (< 3?)
- [ ] Crypto market regime (bull/bear?)

**Weekly:**
- [ ] Overall P&L trend
- [ ] Convexity score distribution (finding opportunities?)
- [ ] Win rate by asset (which coins work best?)

---

## 🚨 **Common Issues**

### **"Order rejected: non_marginable"**

**Problem:** Tried to use leverage on crypto

**Solution:** Crypto is cash-only. Set:
```python
max_leverage=1.0  # No leverage
```

### **"Insufficient buying power"**

**Problem:** Not enough USD to buy crypto

**Solution:**
1. Check `buying_power` in account
2. Use smaller `notional` or `quantity`
3. Sell existing crypto to free up USD

### **"Symbol not found"**

**Problem:** Using wrong symbol format

**Solution:** Use full format with slash:
```python
symbol="BTC/USD"  # ✅ Correct
symbol="BTC"      # ❌ Wrong
symbol="BTCUSD"   # ❌ Wrong
```

### **"Time in force not supported"**

**Problem:** Used `DAY` or `FOK` time-in-force

**Solution:** Use `GTC` or `IOC` only:
```python
time_in_force="GTC"  # ✅ Good Till Canceled
time_in_force="IOC"  # ✅ Immediate or Cancel
time_in_force="DAY"  # ❌ Not supported for crypto
```

### **"Order size below minimum"**

**Problem:** Order too small

**Solution:**
- For USD pairs: minimum $1
- For BTC pairs: minimum 0.000000002 BTC

### **"Market closed"**

**This will never happen!** Crypto trades 24/7/365.

---

## 🎯 **Recommended Workflow**

### **Phase 1: Crypto Paper Trading (Week 1-2)**

1. ✅ Update config for crypto symbols:
   ```bash
   # .env
   CRYPTO_SYMBOLS=BTC/USD,ETH/USD,SOL/USD
   ```

2. ✅ Run paper trading:
   ```bash
   python examples/live_trading_crypto.py
   ```

3. ✅ Monitor for 2 weeks:
   - Win rate > 15%?
   - Max drawdown < 60%?
   - Convexity detection working?

### **Phase 2: Small Live Test (Week 3-4)**

1. ✅ Start with $500 (10% of $5k)
2. ✅ Trade only BTC/USD (most liquid)
3. ✅ Monitor 24/7 for first 3 days
4. ✅ Validate fills, spreads, execution

### **Phase 3: Full Crypto (Week 5+)**

1. ✅ Scale to full $5k
2. ✅ Add ETH/USD, SOL/USD
3. ✅ Run 24/7 (set up systemd or screen)
4. ✅ Monitor daily

### **Phase 4: Hybrid Portfolio (Optional)**

**Mix stocks + crypto:**
- 50% stocks (AAPL, MSFT, TSLA) - daytime trading
- 50% crypto (BTC, ETH, SOL) - 24/7 trading

**Benefits:**
- More opportunities (never stops trading)
- Diversification (different volatility patterns)
- Maximize convexity detection

---

## 🔥 **Final Warnings**

1. **Crypto is MORE volatile than stocks**
   - Expect 50-80% drawdowns
   - This is on top of your aggressive strategy
   - **You can lose everything faster**

2. **24/7 means 24/7 monitoring**
   - Markets don't sleep
   - Big moves happen at 3 AM
   - Set up alerts or accept risk

3. **Start smaller than stocks**
   - If you'd use $5k for stocks, use $2.5k for crypto
   - Scale up only after validation
   - Crypto + aggressive = highest risk

4. **No margin = no liquidation risk**
   - But also no leverage
   - Gains will be slower per dollar
   - Need more capital for same returns

5. **Exit plan is critical**
   - When to stop? (After how many losses?)
   - How many attempts? (5? 10?)
   - What's the total risk budget?

---

## ✅ **You're Ready When...**

- [✓] Understand crypto trades 24/7
- [✓] Know no margin/shorting allowed
- [✓] Tested in paper trading (2+ weeks)
- [✓] Win rate > 15%, drawdown < 60%
- [✓] ML finding convexity in volatile crypto
- [✓] Can afford to lose 100% of crypto capital
- [✓] Have monitoring plan (alerts/daily checks)
- [✓] Know when to stop (exit criteria clear)

**If all checked:** You're ready for crypto!

**If not:** Keep paper trading.

---

## 🚀 **Quick Command Reference**

```bash
# Check crypto status
python -c "from src.brokers.alpaca_adapter import AlpacaAdapter; ..."

# List crypto assets
python examples/list_crypto_assets.py

# Test crypto order
python examples/test_crypto_order.py

# Run crypto paper trading
python examples/live_trading_crypto.py

# Monitor crypto (24/7)
screen -S crypto-trading
python examples/live_trading_crypto.py
# Detach: Ctrl+A, D
# Reattach: screen -r crypto-trading
```

---

## 📚 **Additional Resources**

- **Alpaca Crypto Docs:** https://docs.alpaca.markets/docs/crypto-trading
- **Crypto Assets API:** https://docs.alpaca.markets/reference/get-v2-assets
- **Crypto Wallets API:** https://docs.alpaca.markets/reference/crypto-wallets

---

**Remember:** Crypto + Aggressive Strategy = Highest Risk/Highest Reward

The math still works (target-utility optimization), but:
- Expect more failures (lower win rate)
- Expect bigger drawdowns (60-80%)
- But also bigger wins when you hit (10x+ possible)

**Your edge:** Finding convexity in 24/7 volatile markets that most traders can't stomach.

Good luck! 🚀💰🎰
