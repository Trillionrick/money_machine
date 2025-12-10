# 🚀 Quick Reference Card - Production Trading

## One-Command Deployment
```bash
cd /mnt/c/Users/catty/Desktop/money_machine
./scripts/deploy_production.sh
```

## Critical Commands

### Emergency Stop
```bash
curl -X POST http://localhost:8080/api/ai/disable
```

### Check Status
```bash
curl http://localhost:8080/api/ai/status | jq .
```

### Live Dashboard
```bash
./scripts/live_monitor.sh
```

### View Recent Trades
```bash
tail -20 logs/trades/trades_*.csv
```

---

## AI Mode Control

```bash
# Conservative (safest)
curl -X POST http://localhost:8080/api/ai/mode/conservative

# Balanced (default)
curl -X POST http://localhost:8080/api/ai/mode/balanced

# Aggressive (risky)
curl -X POST http://localhost:8080/api/ai/mode/aggressive
```

---

## Quick Checks

### Performance
```bash
curl http://localhost:8080/api/ai/metrics | jq '.summary.decisions'
```

### Health
```bash
curl http://localhost:8080/api/ai/health | jq .
```

### Latest 5 Decisions
```bash
curl http://localhost:8080/api/ai/decisions/latest?limit=5 | jq .
```

### On-Chain Stats
```bash
curl http://localhost:8080/api/ai/onchain/stats | jq .
```

---

## Safety Limits (Default)

| Limit | Value |
|-------|-------|
| Max Position Size | 2.0 ETH |
| Max Loss Per Trade | 0.1 ETH |
| Max Hourly Loss | 0.3 ETH |
| Max Daily Loss | 1.0 ETH |
| Max Total Drawdown | 5.0 ETH |
| Max Gas Price | 300 gwei |
| Min Profit After Gas | 0.01 ETH |
| Max Trades/Hour | 10 |
| Max Trades/Day | 50 |

---

## Log Locations

```
logs/trades/trades_*.csv          # Trade history (Excel compatible)
logs/trades/summary_*.json        # Session summaries
logs/system/server.log            # System logs
```

---

## Key Endpoints

- **API Docs**: http://localhost:8080/docs
- **Status**: http://localhost:8080/api/ai/status
- **Metrics**: http://localhost:8080/api/ai/metrics
- **Health**: http://localhost:8080/api/ai/health
- **Config**: http://localhost:8080/api/ai/config

---

## Update Configuration

```bash
curl -X POST http://localhost:8080/api/ai/config/update \
  -H "Content-Type: application/json" \
  -d '{
    "ai_mode": "balanced",
    "ai_min_confidence": 0.75,
    "kelly_fraction": 0.25
  }'
```

---

## Troubleshooting

### System Not Responding
```bash
ps aux | grep uvicorn
pkill -f uvicorn
./run.sh
```

### Check Wallet Balance
```bash
python3 check_wallet.py
```

### Restart Everything
```bash
pkill -f uvicorn
./scripts/deploy_production.sh
```

---

## Daily Checklist

**Morning:**
- [ ] Check status
- [ ] Review overnight trades
- [ ] Verify P&L
- [ ] Check alerts

**Evening:**
- [ ] Review daily summary
- [ ] Withdraw profits (if >0.5 ETH)
- [ ] Adjust mode if needed

---

## Success Metrics

| Metric | Minimum | Good | Excellent |
|--------|---------|------|-----------|
| Win Rate | >50% | >60% | >70% |
| Daily P&L | +0.01 ETH | +0.1 ETH | +0.5 ETH |
| Execution Rate | >10% | >20% | >30% |
| Confidence | >0.70 | >0.75 | >0.80 |

---

**📖 Full Guide**: `PRODUCTION_DEPLOYMENT_GUIDE.md`
