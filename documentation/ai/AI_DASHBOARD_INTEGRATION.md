# AI Dashboard Integration Guide

✅ What's Been Added

Your dashboard now has 14 new AI endpoints providing real-time access to:

- AI performance metrics (win rate, profit, Sharpe ratio)
- Configuration management (modes, thresholds, settings)
- Model status (training state, accuracy)
- Decision history (recent AI choices)
- Health monitoring (alerts, system status)

🚀 Quick Start
1. Restart Your Dashboard

source .venv/bin/activate
python web_server.py


You should see:

ai_endpoints.mounted


2. Test AI Endpoints
Open browser to test the new API:


Check AI status
curl http://localhost:8080/api/ai/status

Get metrics
curl http://localhost:8080/api/ai/metrics

Get health
curl http://localhost:8080/api/ai/health


3. Add UI Widget to Dashboard

Copy the AI widget to your `web_dashboard.html`:


Insert the widget into your dashboard HTML

cat ai_dashboard_widget.html


Add this section to your dashboard, typically after the main status cards.

📡 Available API Endpoints

Status & Control
| Endpoint               | Method | Description |
|----------              |--------|-------------|
| `/api/ai/status`       | GET    | AI system enabled/disabled, mode |
| `/api/ai/enable`       | POST   | Enable AI system |
| `/api/ai/disable`      | POST   | Disable AI system |
| `/api/ai/mode/{mode}`  | POST   | Set mode (conservative/balanced/aggressive) |
| `/api/ai/health`       | GET    | Health indicators and alerts |

Metrics & Performance

| Endpoint                    | Method | Description |
|----------                   |------  |-------------|
| `/api/ai/metrics`           | GET    | Complete performance metrics |
| `/api/ai/metrics/recent`    | GET    | Recent performance (configurable window) |
| `/api/ai/performance/chart` | GET    | Time-series data for charts |
| `/api/ai/decisions/latest`  | GET    | Recent AI decisions |

Configuration

| Endpoint                | Method | Description |
|----------               |--------|-------------|
| `/api/ai/config`        | GET    | Get current configuration |
| `/api/ai/config/update` | POST   | Update configuration |
| `/api/ai/config/reload` | POST   | Reload from file |

Models

| Endpoint         | Method | Description |
|----------        |--------|-------------|
| `/api/ai/models` | GET    | ML model training status |

💻 Example API Usage

Get AI Metrics

javascript
// Fetch current metrics
const response = await fetch('/api/ai/metrics');
const data = await response.json();

console.log('Win Rate:', data.summary.decisions.win_rate);
console.log('Net Profit:', data.summary.execution.net_profit_usd);
console.log('Sharpe Ratio:', data.summary.decisions.sharpe_ratio);


Update Configuration

javascript
// Switch to conservative mode
await fetch('/api/ai/mode/conservative', { method: 'POST' });

// Update specific settings
await fetch('/api/ai/config/update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        ai_min_confidence: 0.75,
        enable_ml_scoring: true,
        max_leverage: 2.0
    })
});


Monitor Health

javascript
// Check system health
const health = await fetch('/api/ai/health').then(r => r.json());

if (health.status === 'warning') {
    console.warn('AI Health Warnings:', health.alerts);
}

if (health.win_rate < 0.5) {
    console.log('Win rate below 50% - consider adjusting settings');
}


🎨 Dashboard Widget Features

The included widget (`ai_dashboard_widget.html`) provides:

Real-time Metrics Display
- ✅ Win Rate with trade count
- ✅ Net Profit with today's performance
- ✅ Average AI Confidence
- ✅ Execution Success Rate
- ✅ Sharpe Ratio
- ✅ Average Edge (bps)

Interactive Controls
- 🎛️ Mode Selector: Switch between conservative/balanced/aggressive
- ⏯️ Enable/Disable Toggle: Turn AI on/off
- 🔄 Refresh Button: Manual metric updates
- 📊 Export Report: Download JSON performance report

Health Monitoring
- 🟢 Green dot: System healthy
- 🟡 Yellow dot: Warnings present
- 🔴 Red dot: Critical issues
- Real-time alert display

Model Status
- Route Success Predictor training state
- RL Policy training state
- Training data availability (50+ samples needed)

Auto-refresh
- Updates every 10 seconds automatically
- WebSocket integration for real-time updates

📊 Sample Dashboard Layout

html
<!DOCTYPE html>
<html>
<head>
    <title>Arbitrage Dashboard</title>
    <!-- Your existing styles -->
</head>
<body>
    <!-- Your existing dashboard header -->

    <!-- MAIN STATUS SECTION -->
    <div class="status-cards">
        <!-- Your existing status cards -->
    </div>

    <!-- ⭐ ADD AI WIDGET HERE ⭐ -->
    <!-- Paste content from ai_dashboard_widget.html -->
    <div class="ai-dashboard" id="aiDashboard">
        <!-- AI widget content -->
    </div>

    <!-- OPPORTUNITIES & TRADES SECTIONS -->
    <div class="opportunities-section">
        <!-- Your existing opportunities table -->
    </div>

    <!-- Your existing footer -->
</body>
</html>


🔧 Integration Steps
Step 1: Verify API is Running

# Start your dashboard
python web_server.py

# In another terminal, test endpoint
curl http://localhost:8080/api/ai/status


Expected response:
json
{
  "enabled": true,
  "mode": "conservative",
  "portfolio_value_eth": 100.0,
  "ml_enabled": true
}


Step 2: Add Widget to HTML
Open `web_dashboard.html` and add the AI widget:

1. Copy entire `<style>` block from `ai_dashboard_widget.html`
2. Paste into your `<head>` section or existing `<style>` tag
3. Copy the `<div class="ai-dashboard">` block
4. Paste into your dashboard body (after main status, before opportunities)
5. Copy the `<script>` block
6. Paste at end of body (before closing `</body>` tag)

Step 3: Test Widget
1. Refresh your dashboard in browser
2. You should see the AI widget with purple gradient
3. Metrics should populate within 10 seconds
4. Try clicking mode buttons to switch modes
5. Test enable/disable toggle

Step 4: Connect to Live Trading
Update your `run_live_arbitrage.py` to use AI runner:

python
from src.live.ai_flash_runner import AIFlashArbitrageRunner, AIFlashArbConfig
from src.ai.metrics import get_metrics_collector

# Create AI config
ai_config = AIFlashArbConfig(
    enable_ai_scoring=True,
    ai_min_confidence=0.75,
    enable_flash_loans=True,
    enable_execution=False,  # Dry-run first
)

# Use AI runner instead of regular runner
runner = AIFlashArbitrageRunner(
    router=router,
    dex=dex,
    price_fetcher=price_fetcher,
    token_addresses=TOKEN_ADDRESSES,
    config=ai_config,
)

# Metrics are automatically tracked
await runner.run(symbols)

# Access metrics via API
metrics = get_metrics_collector()


🎯 Monitoring Best Practices
Critical Metrics to Watch
1. Win Rate - Should be >50%, ideally >60%
   - If <45%, review decision threshold
   - Consider more conservative settings

2. Success Rate - Should be >70%
   - If <70%, check route health
   - ML model may need retraining

3. Net Profit - Should be positive
   - Factor in gas costs
   - Monitor profit per trade trend

4. Sharpe Ratio - Should be >1.0
   - Measures risk-adjusted returns
   - Higher is better (>2.0 excellent)

Alert Thresholds
Built-in alerts trigger when:
- Win rate < 45%
- Success rate < 70%
- Gas costs > 30% of profit
- Drawdown > 20%

Health Status
- 🟢 Healthy: All metrics normal, no alerts
- 🟡 Warning: 1 alert triggered
- 🔴 Critical: 2+ alerts triggered

📈 Performance Optimization

Week 1: Monitoring
- Use dry-run mode
- Collect 50+ execution samples
- Review decision accuracy
- Tune confidence threshold

Week 2: Training
- Train ML models with collected data
- Test in paper trading mode
- Validate model accuracy >60%

Week 3: Deployment
- Enable live trading with small positions
- Monitor closely for anomalies
- Gradually increase position sizes

Week 4: Optimization
- Analyze performance by symbol/time
- Adjust mode based on results
- Consider balanced/aggressive modes

🐛 Troubleshooting

Widget Not Showing
1. Check browser console for errors
2. Verify `/api/ai/status` endpoint works
3. Ensure JavaScript is enabled
4. Check for CSS conflicts

Metrics Not Updating
1. Verify auto-refresh interval (10s default)
2. Check browser Network tab for failed requests
3. Ensure web_server.py is running
4. Look for CORS issues

Configuration Changes Not Applied
1. Check API response for errors
2. Verify validation (confidence 0-1, leverage >1)
3. Try reloading config: `POST /api/ai/config/reload`
4. Restart web server to force reload

Model Status Shows "Untrained"
This is normal at start! Models train after:
- Route predictor: 50+ executions collected
- RL policy: Manual training with collected data

🔐 Security Notes
- API endpoints are currently unprotected
- Consider adding authentication for production
- Rate limit configuration updates
- Sanitize user inputs

📝 Next Steps
1. ✅ Add widget to your dashboard HTML
2. ✅ Test all endpoints
3. ✅ Run in dry-run mode for 24-48 hours
4. ✅ Collect execution data (50+ samples)
5. ✅ Train ML models
6. ✅ Deploy with conservative settings
7. ✅ Scale up gradually

---

Your AI brain is ready for the dashboard! 🧠🚀
