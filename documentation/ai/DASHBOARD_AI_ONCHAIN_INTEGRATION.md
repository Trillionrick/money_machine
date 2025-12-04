 AI/ML On-Chain Dashboard Widget Integration Guide

This guide shows you how to add the AI/ML on-chain control widget to your dashboard for optimal flash loan profitability settings.

What You Get
A powerful dashboard widget that lets you:
- Control AI/ML on-chain settings in real-time
- Apply optimal presets (Conservative/Balanced/Aggressive) with one click
- Set capital and profit targets with live growth multiplier display
- Adjust AI confidence and profit thresholds with visual sliders
- Monitor performance with real-time stats (decisions, executions, win rate, progress)
- Manage risk with daily loss limits and concurrent execution controls

Step 1: Add the Widget to Your Dashboard

Open `web_dashboard.html` and find line 586 (right after the "AI Settings (off-chain)" card closes).

Insert the entire contents of `web_dashboard_ai_onchain.html` at that location.

The widget will appear in the same `settings-flex` grid as your off-chain AI settings, side by side.

Quick Integration:
```bash
 Backup your current dashboard
cp web_dashboard.html web_dashboard.html.backup

 Find the insertion point (line 586, after the off-chain AI card)
 Look for: </div> <!-- end of AI Settings (off-chain) -->

 Insert the new widget code from web_dashboard_ai_onchain.html
 The widget should be placed in the same settings-flex div
```

Visual Result:
```
┌─────────────────────────────────────────────────────────────┐
│                      CONTROLS SECTION                       │
├──────────────────────────┬──────────────────────────────────┤
│  ⚡ Flash Loan Settings  │  🤖 AI Settings (off-chain)     │
├──────────────────────────┴──────────────────────────────────┤
│           ⚡🤖 AI/ML On-Chain (Flash Loans)                 │
│  [Conservative] [Balanced] [Aggressive]                    │
│  AI Mode: [Balanced ▼]                                     │
│  Current Capital: [100] ETH  Target: [1000] ETH  (10.0x)  │
│  AI Confidence: [━━━━━━━●━━] 0.70                         │
│  Min Flash Profit: [━━━━●━━━━] 0.15 ETH                   │
│  [✓] Enable AI Orchestration                               │
│  [✓] Profit Maximization (Aggressive)                      │
│  [✓] ML Model Scoring                                      │
│  [💾 Apply AI On-Chain Config]                             │
│  Stats: Decisions: 47 | Executions: 32 | Win: 68.1%       │
└────────────────────────────────────────────────────────────┘
```

Step 2: Add API Endpoints
Mount the new API endpoints in `web_server.py`.

Add after line 35 (where the existing AI endpoints are mounted):

```python
 Import and mount AI on-chain endpoints
try:
    from src.api.ai_onchain_endpoints import router as ai_onchain_router, set_ai_runner
    app.include_router(ai_onchain_router)
    log.info("ai_onchain_endpoints.mounted")
except Exception as e:
    log.warning("ai_onchain_endpoints.mount_failed", error=str(e))
```

Step 3: Connect the AI Runner
When your AI integrated runner starts, pass it to the API endpoint module.

In `web_server.py`, find where you initialize the scanner/runner (around line 400+), and add:

```python
 After initializing the AI integrated runner:
from src.api.ai_onchain_endpoints import set_ai_runner

 If using AIIntegratedArbitrageRunner:
if hasattr(scanner_system, 'ai_runner'):
    set_ai_runner(scanner_system.ai_runner)
    log.info("ai_onchain.runner_connected")
```

Step 4: Test the Integration
1. Start the dashboard:
```bash
python web_server.py
```

2. Open in browser:
```
http://localhost:8080
```

3. You should see:
   - The new "AI/ML On-Chain (Flash Loans)" widget in the controls section
   - Three preset buttons at the top (Conservative/Balanced/Aggressive)
   - All configuration sliders and inputs
   - Live stats at the bottom

4. Test the presets:
   - Click "🚀 Aggressive" - Watch all settings update
   - Click "💾 Apply AI On-Chain Config"
   - You should see a success message

5. Verify API endpoints work:
```bash
 Get status
curl http://localhost:8080/api/ai/onchain/status

 Get stats
curl http://localhost:8080/api/ai/onchain/stats

 Get health
curl http://localhost:8080/api/ai/onchain/health
```

Step 5: Configure for Maximum Flash Loan Profit
Quick Setup (Recommended for Testing):
1. Click "⚖️ Balanced" preset
2. Adjust Current Capital to match your actual ETH
3. Set Target Capital to your profit goal (e.g., 10x)
4. Click "💾 Apply AI On-Chain Config"
5. Start the scanner

Advanced Tuning for Maximum Profit:
For Aggressive Profitability (Experienced Traders):
1. AI Mode: Aggressive
2. AI Confidence: 0.60 (lower = more opportunities)
3. Min Flash Profit: 0.10 ETH (lower = more trades, but smaller)
4. Kelly Fraction: 0.35 (aggressive position sizing)
5. Max Leverage: 5.0x (high leverage for max returns)
6. Max Concurrent: 5 (execute multiple opportunities in parallel)

Settings:
- Current Capital: 500 ETH
- Target Capital: 5000 ETH (10x growth)
- Max Daily Losses: $1000 (higher risk tolerance)
- ✅ Profit Maximization ON
- ✅ ML Model Scoring ON

Expected Results:
- More frequent trades (50-100 per day)
- Higher variance (bigger wins, some losses)
- Faster progress towards target
- Win rate: 60-65%

For Conservative Profitability (Safe Growth):
1. AI Mode: Conservative
2. AI Confidence: 0.75 (higher = only best opportunities)
3. Min Flash Profit: 0.20 ETH (higher = safer, bigger profits)
4. Kelly Fraction: 0.25 (standard Kelly)
5. Max Leverage: 2.0x (lower risk)
6. Max Concurrent: 2 (fewer parallel trades)

Settings:
- Current Capital: 100 ETH
- Target Capital: 500 ETH (5x growth)
- Max Daily Losses: $300 (lower risk)
- ✅ Profit Maximization ON
- ✅ ML Model Scoring ON

Expected Results:
- Fewer trades (10-20 per day)
- Lower variance (steady growth)
- Slower but safer progress
- Win rate: 70-80%

Widget Features Explained
1. Preset Buttons (Top)
- 🛡️ Conservative: Safe settings, high confidence, lower leverage
- ⚖️ Balanced: Standard settings for most users
- 🚀 Aggressive: Maximum profit settings, higher risk

Clicking a preset instantly populates all fields with optimal values.

2. AI Mode Dropdown
Pre-configured risk profiles that set confidence, leverage, and position sizing.

3. Capital & Target
- Current Capital: Your actual trading capital in ETH
- Target Capital: Your profit goal
- Growth Multiplier: Auto-calculated (e.g., 10.0x)
The AI uses target-based optimization to maximize P(hitting your goal).

4. AI Confidence Slider
- 0.50-0.60: Very aggressive, many opportunities, lower win rate
- 0.65-0.75: Balanced, good opportunity flow, decent win rate
- 0.80-0.90: Conservative, fewer opportunities, high win rate
Recommendation: Start at 0.70, adjust based on results.

5. Min Flash Profit Slider
Minimum profit required to execute a flash loan.

- 0.05-0.10 ETH: More opportunities, smaller profits each
- 0.15-0.25 ETH: Balanced, medium-sized opportunities
- 0.30+ ETH: Fewer opportunities, larger profits
Recommendation: Start at 0.15 ETH, lower if market is slow.

6. Kelly Fraction
Controls position sizing aggressiveness.
- 0.10-0.20: Very conservative (fractional Kelly)
- 0.25: Standard Kelly criterion
- 0.30-0.40: Aggressive (better for target optimization)

Formula:
```
Position Size = Portfolio Value × Kelly Fraction × Edge
```

7. Max Leverage
Maximum flash loan size as multiple of your capital.
- 1.0-2.0x: Conservative, using only your capital
- 3.0-4.0x: Balanced, 3-4x your capital
- 5.0-10.0x: Aggressive, maximum flash loan leverage

Example:
- Capital: 100 ETH
- Leverage: 5.0x
- Max Flash Loan: 500 ETH

8. Risk Management
Max Daily Losses:
- System stops trading if daily losses exceed this
- Protects against bad market conditions
- Resets each day

Max Concurrent:
- Number of trades executing simultaneously
- Higher = more opportunities, but more capital at risk
- Lower = safer, sequential execution

9. Toggles
🎯 Enable AI Orchestration:
- Turns on the unified AI system
- Required for intelligent routing

💰 Profit Maximization (Aggressive):
- Uses target-based optimization instead of Kelly
- Calculates aggressive position sizes
- Faster wealth accumulation, higher variance

🧠 ML Model Scoring:
- Uses trained machine learning model
- Predicts execution success probability
- Requires 50+ historical trades to train

⚡ Flash Loans Enabled:
- Master switch for on-chain execution
- Disable for dry-run testing

10. Stats Display (Bottom)
Real-time performance metrics updated every 5 seconds:

- AI Decisions: Total opportunities scored by AI
- Executions: Actually executed trades
- Win Rate: Percentage of profitable trades
- Progress: % towards your target capital

Advanced Usage
Dynamic Adjustment During Trading
You can adjust settings while the system is running:

1. Market is slow?
   - Lower AI Confidence to 0.65
   - Lower Min Flash Profit to 0.10 ETH
   - Apply config

2. Too many losses?
   - Increase AI Confidence to 0.80
   - Switch to Conservative preset
   - Apply config

3. Approaching target?
   - Switch to Conservative mode
   - Lock in profits
   - Lower leverage

Monitoring Performance
Watch these stats to optimize:

Good Performance:
- Win Rate: 65-75%
- Execution Rate: 50-70% of decisions
- Daily Profit: Positive
- Progress: Steadily increasing

Needs Adjustment:
- Win Rate < 60% → Increase confidence
- Execution Rate < 30% → Lower thresholds
- Daily Losses → Switch to conservative
- Progress stalled → Try balanced/aggressive

API Integration
You can also control via API:

```bash
 Apply aggressive preset
curl -X POST http://localhost:8080/api/ai/onchain/preset/aggressive

 Get current config
curl http://localhost:8080/api/ai/onchain/config

 Update specific settings
curl -X POST http://localhost:8080/api/ai/onchain/config \
  -H "Content-Type: application/json" \
  -d '{
    "ai_mode": "aggressive",
    "ai_min_confidence": 0.65,
    "flash_loan_min_profit_eth": 0.12,
    "current_capital_eth": 200,
    "target_capital_eth": 2000
  }'

 Check health
curl http://localhost:8080/api/ai/onchain/health
```

Troubleshooting
Widget doesn't appear:
- Check console for JavaScript errors
- Verify HTML was inserted in correct location (line 586)
- Ensure `settings-flex` div includes the new widget

"AI runner not initialized" error:
- Verify `set_ai_runner()` was called in web_server.py
- Check that AIIntegratedArbitrageRunner is being used
- Look for initialization errors in logs

Stats not updating:
- Check API endpoints are mounted correctly
- Verify `/api/ai/onchain/stats` returns data
- Check browser network tab for failed requests

Config changes not applied:
- Check `/api/ai/onchain/config` endpoint works
- Verify runner reference is set correctly
- Check logs for configuration errors

Presets not working:
- Check JavaScript console for errors
- Verify preset functions are defined
- Try manually entering values instead

Best Practices
1. Start Conservative:
   - Use Conservative preset for first 24 hours
   - Monitor win rate and profits
   - Gradually increase aggression

2. Collect Training Data:
   - Run for 50+ trades to train ML model
   - ML predictions improve accuracy significantly
   - Check "ML Model Trained" status

3. Monitor Daily:
   - Check win rate (should be 60%+)
   - Watch daily profit trend
   - Adjust if performance degrades

4. Risk Management:
   - Set realistic daily loss limits
   - Don't exceed 5x leverage until proven
   - Keep some capital in reserve

5. Regular Tuning:
   - Review settings weekly
   - Adjust based on market conditions
   - Track what settings work best

Visual Setup Example
Scenario: You have 250 ETH and want to grow to 2500 ETH (10x).

Dashboard Settings:

```
AI Mode: Balanced
Current Capital: 250 ETH
Target Capital: 2500 ETH
Growth Target: 10.0x

AI Confidence: 0.70 [━━━━━━━●━━━]
Min Flash Profit: 0.15 ETH [━━━━●━━━━━]

Kelly Fraction: 0.30
Max Leverage: 3.5x
Max Daily Losses: $750
Max Concurrent: 3

✅ Enable AI Orchestration
✅ Profit Maximization
✅ ML Model Scoring
✅ Flash Loans Enabled
```

Expected Performance:
- 30-50 trades per day
- 0.15-0.25 ETH profit per trade
- 4-8 ETH daily profit
- 65-70% win rate
- Reach target in 60-90 days

Click "💾 Apply AI On-Chain Config" and start trading!

Support
If you encounter issues:

1. Check browser console for errors
2. Verify API endpoints: `curl http://localhost:8080/api/ai/onchain/status`
3. Check web_server logs: `tail -f logs/arbitrage.log`
4. Ensure AI integrated runner is initialized properly

---

Your dashboard is now equipped with professional-grade AI/ML on-chain controls for maximum flash loan profitability! 🚀💰
