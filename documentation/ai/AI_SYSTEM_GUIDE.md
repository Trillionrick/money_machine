# AI-Powered Crypto Arbitrage System - Complete Guide

## Overview

This system implements a **production-grade AI brain** for DEX/CEX arbitrage and flash loan execution. It combines multiple AI techniques for maximum profitability:

- **Advanced Multi-Factor Scoring** - Intelligent opportunity ranking
- **ML-Based Route Prediction** - Success probability estimation
- **Reinforcement Learning** - Adaptive trading strategy
- **Whale Following** - Copy profitable traders via Aqua Protocol

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                     AI ARBITRAGE SYSTEM                        │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │            Advanced AI Decider                        │    │
│  │  • Multi-factor opportunity scoring                   │    │
│  │  • ML route success prediction                        │    │
│  │  • Risk-adjusted position sizing (Kelly criterion)    │    │
│  │  • Adaptive learning from execution results          │    │
│  └──────────────────────────────────────────────────────┘    │
│                          ↓                                     │
│  ┌──────────────────────────────────────────────────────┐    │
│  │        AI Flash Arbitrage Runner                      │    │
│  │  • Integrates AI decider into flash loan execution    │    │
│  │  • Dynamic position sizing based on confidence        │    │
│  │  • Market regime awareness                            │    │
│  │  • Execution result tracking                          │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │        RL-Based Trading Policy                        │    │
│  │  • Q-learning for action selection                    │    │
│  │  • State: edge, position, regime                      │    │
│  │  • Actions: buy, sell, hold, flash_arb                │    │
│  │  • Experience replay for stable learning              │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │        Aqua Opportunity Detector                      │    │
│  │  • Monitor whale deposits/withdrawals                 │    │
│  │  • Track profitable strategies                        │    │
│  │  • Copy trading & counter-trading                     │    │
│  │  • Full execution integration                         │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │        Configuration & Metrics                        │    │
│  │  • Unified config management                          │    │
│  │  • Risk profiles (conservative/balanced/aggressive)   │    │
│  │  • Comprehensive metrics tracking                     │    │
│  │  • Real-time performance monitoring                   │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Advanced AI Decider (`src/ai/advanced_decider.py`)

**Purpose**: Intelligent opportunity evaluation with multi-factor scoring.

**Key Features**:
- **Multi-Factor Scoring** (6 dimensions):
  1. Edge quality (profitability)
  2. Execution risk (gas efficiency, slippage)
  3. Market regime (volatility, trend)
  4. Liquidity (route depth)
  5. Gas efficiency
  6. Historical route performance

- **ML Route Success Predictor**:
  - Gradient boosting classifier
  - 12-dimensional feature vector
  - Predicts execution success probability
  - Trains on historical execution data

- **Risk-Adjusted Sizing**:
  - Kelly criterion for optimal position size
  - Portfolio health constraints
  - Dynamic leverage based on confidence

- **Adaptive Learning**:
  - Records all execution outcomes
  - Updates route success rates (exponential moving average)
  - Triggers model retraining after N samples

**Usage**:
```python
from src.ai.advanced_decider import AdvancedAIDecider, AdvancedAIConfig, MarketRegime
from src.ai.decider import AICandidate

# Initialize
config = AdvancedAIConfig(
    confidence_threshold=0.70,
    enable_ml_scoring=True,
    kelly_fraction=0.25,
)
decider = AdvancedAIDecider(config)

# Set market regime
regime = MarketRegime(
    volatility=0.25,
    liquidity=0.75,
    gas_percentile=0.40,
    regime_label="stable",
)
decider.update_regime(regime)

# Score opportunities
candidates = [
    AICandidate(
        symbol="ETH/USDC",
        edge_bps=65.0,
        notional_quote=10000.0,
        gas_cost_quote=50.0,
        flash_fee_quote=5.0,
        slippage_quote=15.0,
        confidence=0.75,
    ),
]

decision = decider.pick_best(candidates, portfolio_value_eth=100.0)
if decision:
    print(f"Execute {decision.symbol}: ${decision.net_quote:.2f} profit")
```

### 2. AI Flash Arbitrage Runner (`src/live/ai_flash_runner.py`)

**Purpose**: Integrate AI decision-making into flash loan arbitrage execution.

**Key Features**:
- Seamless integration with AdvancedAIDecider
- Market regime detection and updates
- AI-calculated position sizing (Kelly optimal)
- High-confidence execution boost (20% size increase)
- Execution result tracking for learning
- Dry-run mode for safe testing

**Usage**:
```python
from src.live.ai_flash_runner import AIFlashArbitrageRunner, AIFlashArbConfig

config = AIFlashArbConfig(
    enable_ai_scoring=True,
    ai_min_confidence=0.75,
    enable_flash_loans=True,
    enable_execution=False,  # Dry-run
    portfolio_value_eth=100.0,
)

runner = AIFlashArbitrageRunner(
    router=router,
    dex=dex,
    price_fetcher=price_fetcher,
    token_addresses=TOKEN_ADDRESSES,
    config=config,
)

# Run scanner
symbols = ["ETH/USDC", "WETH/USDC", "BTC/USDT"]
await runner.run(symbols)

# Get stats
stats = runner.get_ai_stats()
print(f"AI Decisions Made: {stats['ai_decisions_made']}")
print(f"Execution Rate: {stats['ai_execution_rate']:.1%}")
```

### 3. RL Trading Policy (`src/ai/rl_policy.py`)

**Purpose**: Reinforcement learning for adaptive trading strategy.

**Key Features**:
- **Q-Learning Algorithm**: Learns optimal action selection
- **State Representation** (6D):
  - Edge quality (bps)
  - Position percentage
  - Portfolio health
  - Volatility
  - Gas percentile
  - Liquidity
- **Actions**: buy, sell, hold, flash_arb
- **Epsilon-Greedy Exploration**: Balances exploration vs exploitation
- **Experience Replay**: Stable learning from past trades
- **Model Persistence**: Save/load trained policies

**Usage**:
```python
from src.ai.rl_policy import RLArbitragePolicy, RLPolicyConfig
from src.core.policy import MarketSnapshot, PortfolioState

config = RLPolicyConfig(
    learning_rate=0.01,
    epsilon_start=0.20,
    max_position_size=10.0,
    target_symbols=["ETH/USDC", "BTC/USDT"],
)

policy = RLArbitragePolicy(config)

# Generate orders
snapshot = MarketSnapshot(...)
portfolio = PortfolioState(...)
orders = policy.decide(portfolio, snapshot)

# Record experience
policy.record_experience(
    state=state,
    action="buy",
    reward=0.05,
    next_state=next_state,
    done=False,
    symbol="ETH/USDC",
)
```

### 4. Aqua Opportunity Detector (`src/ai/aqua_opportunity_detector.py`)

**Purpose**: Monitor Aqua Protocol for whale movements and copy trades.

**Key Features**:
- **Event Monitoring**: Pushed, Pulled, Shipped, Docked
- **Whale Tracking**: Identify profitable traders
- **Opportunity Types**:
  - Whale Entry: Copy whale deposits
  - Whale Exit: Counter-trade on price dips
  - Strategy Copy: Replicate successful strategies
- **Full Execution Integration**:
  - Flash loan arbitrage
  - Spot trading (buy/sell)
  - Strategy copying
- **Safety Features**:
  - Slippage protection
  - Gas price limits
  - Position size caps
  - Strategy cooldown

**Usage**:
```python
from src.ai.aqua_opportunity_detector import AquaOpportunityDetector, AquaOpportunityConfig

config = AquaOpportunityConfig(
    min_pushed_amount_usd=10_000.0,
    enable_copy_trading=False,  # Risky - test first
    enable_counter_trading=True,  # Safer
    max_position_size_usd=5_000.0,
)

detector = AquaOpportunityDetector(
    w3_ethereum=w3_eth,
    w3_polygon=w3_poly,
    config=config,
    ai_decider=ai_decider,
    uniswap_connector=uniswap,
    price_fetcher=price_fetcher,
    flash_executor=flash_executor,
)

# Process events
async for event in aqua_client.watch_events():
    await detector.process_event(event)
```

### 5. Configuration Manager (`src/ai/config_manager.py`)

**Purpose**: Centralized configuration for all AI components.

**Key Features**:
- Unified config loading (JSON + env vars)
- Risk profiles (conservative/balanced/aggressive)
- Dynamic configuration updates
- Validation and defaults
- Hot-reload capability

**Risk Profiles**:

| Setting | Conservative | Balanced | Aggressive |
|---------|-------------|----------|------------|
| Confidence Threshold | 0.75 | 0.70 | 0.60 |
| Kelly Fraction | 0.15 | 0.25 | 0.35 |
| Max Leverage | 2.0x | 3.0x | 5.0x |
| Max Flash Borrow | 50 ETH | 100 ETH | 200 ETH |
| Min Profit ETH | 0.20 | 0.15 | 0.10 |
| Copy Trading | Disabled | Disabled | Enabled |

**Usage**:
```python
from src.ai.config_manager import AIConfigManager

# Load config
manager = AIConfigManager(config_path="config/ai_config.json")

# Apply risk profile
manager.update_config({"ai_mode": "conservative"})

# Get config
config = manager.get_config()
print(f"AI Enabled: {config.enable_ai_system}")

# Save config
manager.save_config()
```

### 6. Metrics Collector (`src/ai/metrics.py`)

**Purpose**: Comprehensive performance tracking and monitoring.

**Metrics Tracked**:
- **Decision Metrics**: Total decisions, execution rate, avg confidence, win rate, Sharpe ratio
- **Execution Metrics**: Success rate, profit, gas costs, execution time
- **Opportunity Metrics**: Detection rate, conversion rate, quality scores
- **Model Metrics**: Training status, accuracy, confidence

**Usage**:
```python
from src.ai.metrics import get_metrics_collector

metrics = get_metrics_collector()

# Record decision
metrics.record_decision(
    confidence=0.75,
    edge_bps=50.0,
    predicted_profit=100.0,
    executed=True,
)

# Record execution
metrics.record_execution(
    success=True,
    actual_profit=95.0,
    gas_cost=15.0,
    execution_time_ms=450.0,
)

# Get summary
summary = metrics.get_summary()
print(f"Win Rate: {summary['decisions']['win_rate']:.1%}")
print(f"Net Profit: ${summary['execution']['net_profit_usd']:.2f}")
```

## Quick Start

### 1. Installation

```bash
# Install dependencies (if not already installed)
pip install -r requirements.txt
```

### 2. Configuration

Create `config/ai_config.json`:
```json
{
  "enable_ai_system": true,
  "ai_mode": "conservative",
  "portfolio_value_eth": 100.0,
  "advanced_decider": {
    "confidence_threshold": 0.75,
    "enable_ml_scoring": true,
    "kelly_fraction": 0.25
  },
  "flash_runner": {
    "enable_ai_scoring": true,
    "ai_min_confidence": 0.75
  }
}
```

### 3. Environment Variables

```bash
# AI Settings
export AI_ENABLED=true
export AI_MODE=conservative
export AI_MIN_CONFIDENCE=0.75

# Aqua Settings
export AQUA_ENABLE_COPY_TRADING=false
export AQUA_ENABLE_COUNTER_TRADING=true
```

### 4. Run Examples

```bash
# Test AI integration
python examples/ai_integration_example.py

# Start AI-powered flash arbitrage
python run_live_arbitrage.py --enable-ai --ai-mode conservative
```

## Integration Patterns

### Pattern 1: Drop-in AI Enhancement

Enhance existing arbitrage runner with AI:

```python
# Before: Rule-based
runner = FlashArbitrageRunner(...)

# After: AI-powered
runner = AIFlashArbitrageRunner(
    ...,
    config=AIFlashArbConfig(enable_ai_scoring=True),
)
```

### Pattern 2: RL Policy with LiveEngine

Use RL policy for intelligent order generation:

```python
from src.live.engine import LiveEngine
from src.ai.rl_policy import RLArbitragePolicy

policy = RLArbitragePolicy(config)
engine = LiveEngine(policy=policy, ...)

await engine.run()
```

### Pattern 3: Aqua + Flash Loans

Combine whale following with flash loan execution:

```python
detector = AquaOpportunityDetector(
    ...,
    flash_executor=flash_executor,
)

# Detector automatically executes flash loans for large opportunities
await detector.process_event(whale_deposit_event)
```

## Performance Optimization

### 1. Model Training

Train ML models on historical data for better predictions:

```python
from src.ai.advanced_decider import RouteSuccessPredictor

predictor = RouteSuccessPredictor()

# Load historical executions
history = load_execution_history()

# Train model
predictor.train_model(history)
predictor.save_model()
```

### 2. RL Policy Training

Train RL policy in simulation before live trading:

```python
policy = RLArbitragePolicy(config)

# Simulate episodes
for episode in range(1000):
    # Run episode
    total_reward = simulate_episode(policy)

    # End episode
    policy.end_episode(total_reward)

# Model automatically saves every 100 episodes
```

### 3. Backtesting

Test AI decisions on historical data:

```python
from src.research.simulator import Simulator

simulator = Simulator(
    policy=RLArbitragePolicy(config),
    data=historical_data,
)

results = await simulator.run()
print(f"Sharpe Ratio: {results['sharpe']:.2f}")
print(f"Win Rate: {results['win_rate']:.1%}")
```

## Monitoring & Alerts

### Real-time Metrics

```python
# Get current performance
metrics = get_metrics_collector()
summary = metrics.get_summary()

# Recent performance (last hour)
recent = metrics.get_recent_performance(window_minutes=60)
print(f"Hourly Profit: ${recent['total_profit']:.2f}")
```

### Alert Thresholds

Built-in alerts trigger when:
- Win rate < 45%
- Gas costs > 30% of profit
- Success rate < 70%
- Drawdown > 20%

### Dashboard Integration

Metrics are dashboard-ready:

```python
# API endpoint example
@app.get("/api/ai/metrics")
async def get_ai_metrics():
    metrics = get_metrics_collector()
    return metrics.get_summary()
```

## Safety Guidelines

### Testing Progression

1. **Simulation Mode**: Test with historical data
2. **Dry-Run Mode**: Monitor live opportunities without execution
3. **Small Position Mode**: Execute with minimal capital
4. **Conservative Mode**: Full deployment with conservative settings
5. **Balanced/Aggressive**: Increase risk after proven track record

### Risk Management

- **Always start in dry-run mode**
- **Use conservative profile initially**
- **Monitor for 24-48 hours before live trading**
- **Start with small position sizes**
- **Set stop-loss thresholds**
- **Keep emergency shutdown ready**

### Model Validation

Before deploying ML models:
1. Validate on holdout test set
2. Check prediction accuracy > 60%
3. Verify calibration (predicted vs actual)
4. Test in simulation mode
5. Monitor for model drift

## Troubleshooting

### Low Win Rate

If win rate drops below expected:
1. Check market regime (high volatility?)
2. Increase confidence threshold
3. Review failed execution logs
4. Retrain ML models on recent data
5. Switch to conservative mode

### High Gas Costs

If gas costs eating into profits:
1. Increase gas efficiency weight in scoring
2. Raise minimum profit threshold
3. Filter opportunities during high gas
4. Use gas oracle for better estimates
5. Consider L2 chains (Polygon)

### Model Performance Degradation

If ML model accuracy drops:
1. Retrain with recent data
2. Check for market regime changes
3. Add new features to model
4. Increase training sample size
5. Consider ensemble methods

## File Structure

```
src/ai/
├── advanced_decider.py       # Multi-factor AI scoring
├── aqua_opportunity_detector.py  # Whale following
├── config_manager.py          # Configuration management
├── decider.py                 # Basic AI decider (legacy)
├── metrics.py                 # Performance tracking
└── rl_policy.py              # Reinforcement learning

src/live/
└── ai_flash_runner.py        # AI-enhanced flash arbitrage

examples/
└── ai_integration_example.py # Complete integration examples

config/
└── ai_config.json            # AI system configuration

models/
├── route_success_model.pkl   # Trained route predictor
└── rl_policy_model.pkl       # Trained RL policy
```

## Next Steps

### Phase 1: Testing (Week 1-2)
- [x] Run examples and verify outputs
- [ ] Test in dry-run mode for 48 hours
- [ ] Monitor metrics and validate behavior
- [ ] Tune confidence thresholds

### Phase 2: Training (Week 2-3)
- [ ] Collect execution history (100+ samples)
- [ ] Train ML route predictor
- [ ] Train RL policy in simulation
- [ ] Validate model performance

### Phase 3: Deployment (Week 3-4)
- [ ] Deploy in conservative mode
- [ ] Monitor for 1 week with small positions
- [ ] Gradually increase position sizes
- [ ] Transition to balanced mode

### Phase 4: Optimization (Ongoing)
- [ ] Continuous model retraining
- [ ] Feature engineering improvements
- [ ] Ensemble method integration
- [ ] Multi-chain expansion

## Support

For questions or issues:
- Review examples: `examples/ai_integration_example.py`
- Check logs: `logs/arbitrage.log`
- Monitor metrics: AI metrics API
- Refer to: `CLAUDE.md` for system architecture

---

**Built with production-grade ML/RL for maximum profitability on a grand scale.**
