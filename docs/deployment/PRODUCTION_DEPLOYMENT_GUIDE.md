# 🚀 Production Deployment Guide

**Complete guide for deploying the AI trading system with real capital.**

---

## ⚠️ Critical Warning

**This system will trade with REAL money on mainnet Ethereum.**

- You may lose all deployed capital
- Smart contract risks exist
- Market conditions may be unfavorable
- MEV bots may frontrun your trades
- Gas fees can be substantial

**Only deploy capital you can afford to lose completely.**

---

## 📋 Pre-Deployment Checklist

### 1. System Requirements ✅

- [x] Linux/WSL2 environment
- [x] Python 3.10+
- [x] Node.js (for some dependencies)
- [x] Minimum 2 GB RAM
- [x] Stable internet connection

### 2. Wallet Setup ✅

- [x] Ethereum wallet with private key
- [x] Minimum 1 ETH balance (gas + trading capital)
- [x] Funded with gas money (0.1-0.2 ETH reserve)

### 3. API Access ✅

- [x] Alchemy API key (RPC access)
- [x] The Graph API key (on-chain data)
- [x] Optional: Discord webhook for alerts

### 4. Configuration ✅

- [x] `.env` file configured with all keys
- [x] `WALLET_PRIVATE_KEY` set correctly
- [x] RPC endpoints configured
- [x] Safety limits reviewed

---

## 🔧 Quick Start - One Command Deployment

### Step 1: Navigate to Project

```bash
cd /mnt/c/Users/catty/Desktop/money_machine
```

### Step 2: Run Deployment Script

```bash
./scripts/deploy_production.sh
```

The script will:
1. ✅ Validate configuration
2. ✅ Check wallet balance
3. ✅ Review safety limits
4. ✅ Configure AI mode
5. ✅ Setup monitoring
6. ✅ Enable alerts
7. ✅ Deploy system

---

## 🎯 AI Trading Modes

### Conservative Mode (Recommended for Start)

```
Confidence Threshold: 75%
Kelly Fraction: 0.15
Max Leverage: 2.0x
Min Flash Profit: 0.20 ETH
```

**Best for:**
- First time deployment
- Risk-averse traders
- Smaller capital (<5 ETH)

### Balanced Mode (Default)

```
Confidence Threshold: 70%
Kelly Fraction: 0.25
Max Leverage: 3.0x
Min Flash Profit: 0.15 ETH
```

**Best for:**
- Experienced users
- Medium capital (5-20 ETH)
- Stable market conditions

### Aggressive Mode ⚠️

```
Confidence Threshold: 65%
Kelly Fraction: 0.35
Max Leverage: 5.0x
Min Flash Profit: 0.10 ETH
```

**Best for:**
- Advanced users only
- Larger capital (20+ ETH)
- High risk tolerance
- Volatile markets

---

## 🛡️ Safety Mechanisms

### Production Safety Guard

**Pre-Trade Validation (ALL must pass):**

✅ Position size < 2.0 ETH per trade
✅ Net profit after gas > 0.01 ETH
✅ Gas price < 300 gwei
✅ Pool liquidity > 20x position size
✅ Slippage < 2%
✅ Hourly loss < 0.3 ETH
✅ Daily loss < 1.0 ETH
✅ Total drawdown < 5.0 ETH
✅ Rate limit: 10 trades/hour, 50/day

### Emergency Shutdown

Automatically triggers on:
- Daily loss exceeds 1.0 ETH
- Total drawdown exceeds 5.0 ETH
- Hourly loss exceeds 0.3 ETH

**Manual shutdown:**
```bash
curl -X POST http://localhost:8080/api/ai/disable
```

### Circuit Breakers

- **Win Rate**: Halts if win rate < 40% (last 20 trades)
- **Drawdown**: Stops at 15% drawdown from peak
- **Gas Costs**: Pauses if gas > 40% of profits
- **Consecutive Failures**: Stops after 5 failures in a row
- **Volatility Spike**: Halts on 3x normal volatility
- **Execution Failures**: Stops at 80% failure rate (15 min)

---

## 📊 Monitoring Dashboard

### Start Live Monitor

```bash
cd /mnt/c/Users/catty/Desktop/money_machine
./scripts/live_monitor.sh
```

**Dashboard shows:**
- Real-time P&L
- System status (enabled/disabled)
- Trade execution stats
- Win rate & confidence
- ML model performance
- Active alerts
- Latest decisions

### Check Status via API

```bash
# System status
curl http://localhost:8080/api/ai/status | jq .

# Performance metrics
curl http://localhost:8080/api/ai/metrics | jq .

# Latest decisions
curl http://localhost:8080/api/ai/decisions/latest | jq .

# Health check
curl http://localhost:8080/api/ai/health | jq .
```

---

## 🔔 Alert Configuration

### Discord Alerts (Recommended)

1. Create Discord webhook:
   - Go to Server Settings → Integrations → Webhooks
   - Create webhook, copy URL

2. Add to `.env`:
   ```bash
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK
   ```

3. Alerts sent for:
   - ✅ Profitable trades
   - ❌ Losing trades
   - ⚠️ Circuit breakers
   - 🚨 Emergency shutdowns
   - 📊 Daily summaries

### Telegram Alerts (Optional)

1. Create bot with @BotFather
2. Get chat ID
3. Add to `.env`:
   ```bash
   TELEGRAM_BOT_TOKEN=your_bot_token
   TELEGRAM_CHAT_ID=your_chat_id
   ```

---

## 📈 Capital Scaling Strategy

### Week 1: Small Capital Testing

```
Capital: 1-2 ETH
Mode: Conservative
Goal: Validate system works in production
Profit Target: 0.1-0.2 ETH
```

### Week 2-3: Increase if Profitable

```
Capital: 3-5 ETH (if Week 1 profitable)
Mode: Balanced
Goal: Optimize for consistent returns
Profit Target: 0.3-0.5 ETH/week
```

### Month 2+: Scale Up

```
Capital: 10-20 ETH (if consistently profitable)
Mode: Balanced or Aggressive
Goal: Maximize returns while managing risk
Profit Target: 1-2 ETH/week
```

**Rules:**
- Only scale after 7 consecutive profitable days
- If losing day occurs, pause scaling for 48 hours
- Never deploy >20% of total capital
- Withdraw profits weekly (take money off table)

---

## 🔍 Transaction Logs

### Log Locations

```
logs/trades/                      # Trade execution logs
  ├── trades_YYYYMMDD_HHMMSS.csv # CSV format (Excel compatible)
  ├── trades_YYYYMMDD_HHMMSS.jsonl # JSON lines (programmatic)
  └── summary_YYYYMMDD_HHMMSS.json # Session summary

logs/system/                      # System logs
  └── server.log                 # FastAPI server logs
```

### Analyze Performance

```bash
# View recent trades (CSV)
tail -20 logs/trades/trades_*.csv

# Session summary
cat logs/trades/summary_*.json | jq .

# Calculate total P&L
grep -h "," logs/trades/trades_*.csv | awk -F',' '{sum+=$17} END {print "Total PnL:", sum, "ETH"}'
```

---

## 🚨 Emergency Procedures

### System Acting Strange

```bash
# 1. Disable AI immediately
curl -X POST http://localhost:8080/api/ai/disable

# 2. Check recent trades
curl http://localhost:8080/api/ai/decisions/latest | jq .

# 3. Review logs
tail -100 logs/system/server.log

# 4. Check health
curl http://localhost:8080/api/ai/health | jq .
```

### Large Unexpected Loss

```bash
# 1. Emergency shutdown
curl -X POST http://localhost:8080/api/ai/disable

# 2. Review transaction history
grep -h "," logs/trades/trades_*.csv | tail -50

# 3. Check circuit breaker status
curl http://localhost:8080/api/ai/status | jq .

# 4. Analyze what went wrong
# Check Etherscan for transaction details
```

### System Not Responding

```bash
# 1. Check if server is running
ps aux | grep uvicorn

# 2. Restart server
pkill -f uvicorn
./run.sh

# 3. Verify configuration
python3 check_env.py

# 4. Re-deploy
./scripts/deploy_production.sh
```

---

## 📝 Daily Operations Checklist

### Morning Routine

- [ ] Check system status: `curl http://localhost:8080/api/ai/status`
- [ ] Review overnight trades: `tail logs/trades/trades_*.csv`
- [ ] Check P&L: `curl http://localhost:8080/api/ai/metrics | jq .summary.decisions`
- [ ] Verify wallet balance matches expectations
- [ ] Check for any alerts (Discord/Telegram)

### Evening Routine

- [ ] Review daily summary
- [ ] Export session stats: Check `logs/trades/summary_*.json`
- [ ] Withdraw profits (if >0.5 ETH accumulated)
- [ ] Adjust AI mode if needed based on performance
- [ ] Plan next day's capital allocation

---

## ⚙️ Advanced Configuration

### Modify Safety Limits

Edit: `src/ai/production_safety.py`

```python
@dataclass
class ProductionSafetyConfig:
    max_loss_per_trade_eth: float = 0.1      # Increase for larger trades
    max_daily_loss_eth: float = 1.0          # Increase risk tolerance
    max_position_size_eth: float = 2.0        # Allow larger positions
    min_profit_after_gas_eth: float = 0.01   # Lower for more opportunities
    # ... etc
```

After changes:
```bash
# Restart system to apply
pkill -f uvicorn
./run.sh
```

### Change AI Confidence Threshold

```bash
# Via API (temporary)
curl -X POST http://localhost:8080/api/ai/config/update \
  -H "Content-Type: application/json" \
  -d '{"ai_min_confidence": 0.80}'

# Via .env (permanent)
echo "AI_MIN_CONFIDENCE=0.80" >> .env
# Then restart system
```

### Switch AI Mode On-The-Fly

```bash
# Conservative
curl -X POST http://localhost:8080/api/ai/mode/conservative

# Balanced
curl -X POST http://localhost:8080/api/ai/mode/balanced

# Aggressive
curl -X POST http://localhost:8080/api/ai/mode/aggressive
```

---

## 🎯 Success Metrics

### Minimum Viable Performance

```
Win Rate: >50%
Daily P&L: +0.01 ETH/day (covers gas + risk)
Execution Rate: >10% (AI approves 10% of opportunities)
Average Confidence: >0.70
```

### Good Performance

```
Win Rate: >60%
Daily P&L: +0.1 ETH/day
Execution Rate: >20%
Average Confidence: >0.75
Sharpe Ratio: >1.0
```

### Excellent Performance

```
Win Rate: >70%
Daily P&L: +0.5 ETH/day
Execution Rate: >30%
Average Confidence: >0.80
Sharpe Ratio: >2.0
```

---

## 🛠️ Troubleshooting

### No Trades Executing

**Possible causes:**
1. Confidence threshold too high → Lower via `/api/ai/config/update`
2. Gas prices too high → Wait for lower gas or increase `max_gas_price_gwei`
3. No profitable opportunities → Normal during low volatility
4. Circuit breaker triggered → Check `/api/ai/health`

### High Gas Costs Eating Profits

**Solutions:**
1. Increase `min_profit_after_gas_eth` to 0.02-0.05 ETH
2. Only trade during low gas periods (<50 gwei)
3. Increase minimum profit thresholds
4. Use Flashbots RPC to reduce MEV

### Getting Frontrun by MEV Bots

**Solutions:**
1. Use private RPC (Flashbots, Eden Network)
2. Reduce trade size to be less attractive
3. Increase slippage tolerance slightly
4. Focus on less competitive pairs

### Low Win Rate

**Actions:**
1. Switch to Conservative mode
2. Increase confidence threshold to 0.80+
3. Review losing trades in logs
4. Ensure ML models are trained
5. Check for market regime changes

---

## 📞 Support & Resources

### Documentation
- API Docs: http://localhost:8080/docs
- This Guide: `PRODUCTION_DEPLOYMENT_GUIDE.md`
- System Architecture: `PROJECT_SUMMARY.md`

### Logs
- System: `logs/system/server.log`
- Trades: `logs/trades/trades_*.csv`

### API Endpoints
- Status: http://localhost:8080/api/ai/status
- Metrics: http://localhost:8080/api/ai/metrics
- Health: http://localhost:8080/api/ai/health

---

## 🎓 Best Practices

1. **Start Small**: Begin with 1-2 ETH, scale gradually
2. **Monitor Closely**: Check dashboard multiple times daily (first week)
3. **Take Profits**: Withdraw profits weekly, don't compound everything
4. **Stay Conservative**: Better to miss opportunities than lose capital
5. **Review Regularly**: Analyze performance weekly, adjust strategy
6. **Keep Reserves**: Always maintain 20-30% capital in stablecoins
7. **Use Alerts**: Set up Discord/Telegram for real-time notifications
8. **Document Changes**: Keep notes on configuration changes and results
9. **Respect Limits**: Don't override safety mechanisms without good reason
10. **Have Exit Plan**: Know when to stop (e.g., -20% total capital)

---

## 🚀 You're Ready!

Run the deployment script when ready:

```bash
cd /mnt/c/Users/catty/Desktop/money_machine
./scripts/deploy_production.sh
```

**Good luck and trade safely! 💰**
