# AI System - Quick Start Guide

## ✅ System Status: OPERATIONAL

All AI components successfully integrated and tested.

## Run the Demo

```bash
source .venv/bin/activate
python examples/ai_integration_example.py
```

This demonstrates:
- ✅ **AI Flash Arbitrage** with multi-factor scoring
- ✅ **RL Policy** with Q-learning
- ✅ **Aqua Whale Following** with copy trading
- ✅ **Unified Metrics** tracking

## Integration into Your Live System

### Option 1: AI Flash Arbitrage (Recommended Start)

Replace your current `FlashArbitrageRunner` with AI-enhanced version:

```python
from src.live.ai_flash_runner import AIFlashArbitrageRunner, AIFlashArbConfig
from src.ai.config_manager import get_ai_config_manager

# Initialize config
config_manager = get_ai_config_manager()
config_manager.update_config({"ai_mode": "conservative"})

# Create AI runner
ai_config = AIFlashArbConfig(
    enable_ai_scoring=True,
    ai_min_confidence=0.75,
    enable_flash_loans=True,
    enable_execution=False,  # DRY RUN FIRST
    portfolio_value_eth=100.0,
)

runner = AIFlashArbitrageRunner(
    router=your_router,
    dex=your_dex,
    price_fetcher=your_price_fetcher,
    token_addresses=your_token_addresses,
    config=ai_config,
)

# Run scanner
await runner.run(["ETH/USDC", "WETH/USDC", "BTC/USDT"])
```

### Option 2: RL Policy for LiveEngine

```python
from src.ai.rl_policy import RLArbitragePolicy, RLPolicyConfig
from src.live.engine import LiveEngine

# Create RL policy
policy = RLArbitragePolicy(RLPolicyConfig(
    learning_rate=0.01,
    epsilon_start=0.20,
    target_symbols=["ETH/USDC", "BTC/USDT"],
))

# Use with LiveEngine
engine = LiveEngine(
    policy=policy,
    execution_engine=your_execution_engine,
)

await engine.run()
```

## Configuration Modes

### Conservative (Recommended Start)
- Confidence: 0.75+
- Kelly Fraction: 0.15
- Max Leverage: 2x
- Max Borrow: 50 ETH
- Copy Trading: DISABLED

```bash
export AI_MODE=conservative
export AI_MIN_CONFIDENCE=0.75
```

### Balanced (After Testing)
- Confidence: 0.70+
- Kelly Fraction: 0.25
- Max Leverage: 3x
- Max Borrow: 100 ETH

```bash
export AI_MODE=balanced
export AI_MIN_CONFIDENCE=0.70
```

### Aggressive (Experienced Only)
- Confidence: 0.60+
- Kelly Fraction: 0.35
- Max Leverage: 5x
- Max Borrow: 200 ETH
- Copy Trading: ENABLED

```bash
export AI_MODE=aggressive
export AI_MIN_CONFIDENCE=0.60
```

## Monitor Performance

```python
from src.ai.metrics import get_metrics_collector

metrics = get_metrics_collector()

# Get current stats
summary = metrics.get_summary()
print(f"Win Rate: {summary['decisions']['win_rate']:.1%}")
print(f"Net Profit: ${summary['execution']['net_profit_usd']:.2f}")
print(f"Sharpe: {summary['decisions']['sharpe_ratio']:.2f}")

# Get recent performance
recent = metrics.get_recent_performance(window_minutes=60)
print(f"Last Hour: ${recent['total_profit']:.2f}")
```

## Safety Checklist

- [ ] Run `examples/ai_integration_example.py` successfully
- [ ] Test in dry-run mode for 24-48 hours
- [ ] Start with conservative profile
- [ ] Monitor metrics for anomalies
- [ ] Gradually increase position sizes
- [ ] Collect 100+ executions for ML training

## Key Features Working

✅ **Multi-factor scoring** - 6 dimensions analyzed per opportunity
✅ **ML route prediction** - Success probability estimation
✅ **Kelly sizing** - Optimal risk-adjusted positions
✅ **Adaptive learning** - Updates from every execution
✅ **Market regime awareness** - Adjusts to volatility/gas/liquidity
✅ **RL policy** - Q-learning for strategy evolution
✅ **Aqua integration** - Whale following with full execution
✅ **Comprehensive metrics** - Real-time performance tracking
✅ **Alert system** - Triggers on low win rate / high costs

## Next Steps

1. **Week 1**: Run examples, test in dry-run mode
2. **Week 2**: Deploy with small positions ($100-500)
3. **Week 3**: Collect execution data (100+ samples)
4. **Week 4**: Train ML models, optimize thresholds
5. **Month 2+**: Scale up, transition to balanced/aggressive

## Support Files

- **Full Guide**: `AI_SYSTEM_GUIDE.md`
- **Examples**: `examples/ai_integration_example.py`
- **Configuration**: `src/ai/config_manager.py`
- **Metrics API**: `src/ai/metrics.py`

---

**System tested and ready for deployment** 🚀
