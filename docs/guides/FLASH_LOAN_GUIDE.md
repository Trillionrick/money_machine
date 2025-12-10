# Flash Loan Arbitrage - Quick Start Guide

## ✅ Configuration Complete!

Your bot is now configured to use flash loans for capital-free arbitrage.

---

## 📋 Current Settings

```bash
ENABLE_FLASH_LOANS=true                    # Flash loans enabled
MIN_FLASH_PROFIT_ETH=0.05                  # Min $120 profit (at $2,400/ETH)
MAX_FLASH_BORROW_ETH=10.0                  # Max 10 ETH borrow (~$24,000)
FLASH_LOAN_THRESHOLD_BPS=50.0              # Min 50 bps (0.5%) edge needed
SLIPPAGE_TOLERANCE_BPS=50                  # 0.5% max slippage
MAX_GAS_PRICE_GWEI=100                     # Max gas price limit
ARB_CONTRACT_ADDRESS=0x8d2DF8b754154A3c16338353Ad9f7875B210D9B0
```

---

## 🚀 How to Start

### Test Mode (Dry Run - Recommended First):
```bash
python run_live_arbitrage.py
```

This will:
- ✅ Scan for flash loan opportunities
- ✅ Show what WOULD be executed
- ✅ Log all opportunities
- ❌ NOT execute real trades

### Live Mode (Real Flash Loans):
```bash
python run_live_arbitrage.py --live
```

This will:
- ✅ Scan for opportunities
- ✅ Execute real flash loan trades
- ⚠️ Use real gas (costs money!)
- 💰 Make real profits (or losses if unprofitable)

---

## 💰 Funding Requirements

### For Flash Loans, You ONLY Need Gas ETH:

```
Minimum:  0.1 ETH  (~$240)  - 2-4 trades
Recommended: 0.3 ETH  (~$720)  - 6-10 trades
Comfortable: 0.5 ETH  (~$1,200) - 15-20 trades
```

**No other capital needed!** The flash loan borrows everything else.

### How to Fund:

1. **Send ETH to your wallet:**
   ```
   Address: (your METAMASK_WALLET_ADDRESS from .env)
   Network: Ethereum Mainnet
   Amount: 0.3-0.5 ETH
   ```

2. **Verify balance:**
   - Go to: https://etherscan.io
   - Enter your wallet address
   - Confirm ETH balance shows

---

## 🎯 How Flash Loans Work

### Normal Arbitrage (What you DON'T need):
```
Your money: $90,000 USDT → Buy 1 BTC on DEX
Your BTC: Sell on CEX → Get $90,400
Profit: $400
Capital needed: $90,000 💰💰💰
```

### Flash Loan Arbitrage (What you WILL do):
```
Step 1: Borrow 1 BTC from Aave (no collateral!)
Step 2: Sell 1 BTC on CEX for $90,400 USDT
Step 3: Buy 1 BTC on DEX for $90,000 USDT
Step 4: Repay 1 BTC + $45 fee to Aave
Step 5: Keep $355 profit!

All in ONE transaction! If any step fails, entire thing reverts.

Capital needed: $50-100 gas only! ⛽
```

---

## 📊 Expected Performance

### Based on Your Paper Trading Results:

#### Your 6 Trades Converted to Flash Loans:

| Trade | Edge (bps) | Gross | Flash Fee | Gas | Net Profit |
|-------|-----------|-------|-----------|-----|------------|
| 1 | 25.11 | $227 | -$45 | -$50 | $132 ✅ |
| 2 | 38.40 | $347 | -$45 | -$50 | $252 ✅ |
| 3 | 38.83 | $351 | -$45 | -$50 | $256 ✅ |
| 4 | 38.83 | $351 | -$45 | -$50 | $256 ✅ |
| 5 | 30.00 | $271 | -$45 | -$50 | $176 ✅ |
| 6 | 28.30 | $256 | -$45 | -$50 | $161 ✅ |

**Total: $1,233 profit (vs $300 with regular arb!)**

**Capital used: $300 gas (vs $541,000!)**

**ROI: 411%** 🚀

---

## ⚠️ Important Notes

### 1. Flash Loans Only Execute for High-Edge Opportunities

Your bot will:
- Use **regular arbitrage** for edges 25-49 bps (if you have capital)
- Use **flash loans** for edges ≥50 bps (no capital needed)

Since you don't have capital, you'll ONLY see flash loan trades.

### 2. Flash Loan Fees

Aave charges **0.05%** flash loan fee:
- 1 ETH borrow = 0.0005 ETH fee (~$1.20)
- 10 ETH borrow = 0.005 ETH fee (~$12)
- 1 BTC borrow = 0.0005 BTC fee (~$45)

### 3. Gas Costs Are Higher

Flash loans use more gas than simple swaps:
- Regular swap: ~150,000 gas (~$30-50)
- Flash loan arb: ~350,000 gas (~$70-100)

### 4. All-or-Nothing

Flash loans are **atomic**:
- ✅ Everything succeeds → You profit
- ❌ Anything fails → Entire transaction reverts (you only lose gas)

### 5. Why You Need 50 bps Minimum

```
Example: 50 bps edge on $90,000:
Gross profit:      $450
Flash loan fee:    -$45  (0.05%)
Gas cost:          -$80
Slippage:          -$100
───────────────────────
Net profit:        $225 ✅ Profitable!

Example: 30 bps edge on $90,000:
Gross profit:      $270
Flash loan fee:    -$45
Gas cost:          -$80
Slippage:          -$100
───────────────────────
Net profit:        $45 ⚠️ Risky! (one gas spike = loss)
```

---

## 🎯 What to Expect

### First Week (Dry Run):

```bash
# Start in test mode
python run_live_arbitrage.py

# You'll see logs like:
flash_arb.opportunity_detected symbol=BTC/USDT edge_bps=52.3
flash_arb.profitability_check_passed net_profit_eth=0.12
flash_arb.dry_run  ← No real execution

# Dashboard will show:
Path: flash_loan  ← Instead of "regular"
```

### Going Live:

```bash
# Make sure you have 0.3-0.5 ETH in your wallet first!
python run_live_arbitrage.py --live

# You'll see:
flash_arb.opportunity_detected symbol=ETH/USDC edge_bps=58.2
flash_arb.profitability_check_passed net_profit_eth=0.15
flash_loan.tx_submitted tx_hash=0x1234abcd...
flash_loan.tx_confirmed status=1 gas_used=348521

# Dashboard will show:
Mode: flash_loan
Tx: 0x1234abcd...  ← Real transaction hash!
```

---

## 📈 Optimization Tips

### 1. Adjust Minimum Profit Based on Gas

```bash
# High gas period (>80 gwei):
MIN_FLASH_PROFIT_ETH=0.1  # Need higher profit

# Low gas period (<30 gwei):
MIN_FLASH_PROFIT_ETH=0.03  # Can take smaller profits
```

### 2. Monitor Gas Prices

Best times for flash loan arb:
- ✅ Early morning UTC (2-6 AM)
- ✅ Weekends
- ✅ Low network activity periods

Worst times:
- ❌ NFT mints
- ❌ Major DeFi protocol launches
- ❌ Market volatility spikes

### 3. Track Your ROI

```bash
# Calculate ROI per trade:
Net Profit / Gas Spent = ROI

# Example:
$200 profit / $80 gas = 250% ROI ✅

# If ROI < 100%, adjust MIN_FLASH_PROFIT_ETH higher
```

---

## 🔍 Monitoring

### Check Your Dashboard:

Recent Opportunities should show:
```
BTC/USDT
52.3 bps
Path: flash_loan  ← Look for this!
CEX: 90824.00
DEX: 90350.12
```

### Check Terminal Logs:

```bash
# Good signs:
flash_arb.opportunity_detected
flash_arb.profitability_check_passed
flash_loan.tx_confirmed

# Warning signs:
flash_arb.not_profitable_after_fees
flash_loan.gas_too_high

# Error signs:
flash_loan.execution_failed
flash_loan.profitability_check_failed
```

---

## 🎬 Quick Start Checklist

- [ ] Contract deployed on mainnet ✅ (You did this!)
- [ ] ARB_CONTRACT_ADDRESS in .env ✅
- [ ] ENABLE_FLASH_LOANS=true ✅
- [ ] Settings configured ✅
- [ ] Wallet has 0.3+ ETH for gas ⚠️ (Do this!)
- [ ] Run dry-run test first ⚠️
- [ ] Monitor for 24-48 hours
- [ ] Go live with --live flag

---

## 💡 Pro Tips

1. **Start conservative:** Keep MIN_FLASH_PROFIT_ETH at 0.05 ETH
2. **Monitor gas:** Only execute when gas < 50 gwei for max profit
3. **Track metrics:** Calculate ROI on every trade
4. **Be patient:** Flash loan opportunities are rarer but more profitable
5. **Keep gas topped up:** Always maintain 0.2+ ETH balance

---

## 🆘 Troubleshooting

### "No flash loan opportunities detected"
- ✅ Normal! Flash loans need ≥50 bps edge
- ✅ Wait for higher volatility
- ✅ Lower FLASH_LOAN_THRESHOLD_BPS to 40 if desperate

### "Profitability check failed"
- ✅ Gas too high - wait for lower gas
- ✅ Edge too small - opportunity not profitable
- ✅ Increase MIN_FLASH_PROFIT_ETH

### "Transaction reverted"
- ✅ Price moved during execution (slippage)
- ✅ Increase SLIPPAGE_TOLERANCE_BPS
- ✅ You only lost gas, not borrowed capital!

---

**Ready to make capital-free profits?** 🚀

Fund your wallet with 0.3-0.5 ETH and let's go!
