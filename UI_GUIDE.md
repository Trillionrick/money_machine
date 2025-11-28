# 🎨 Arbitrage Dashboard UI - User Guide

## ✅ What's Been Created

Your beautiful web-based dashboard for monitoring and controlling the arbitrage scanner!

---

## 🚀 How to Launch the Dashboard

### Option 1: Using the Startup Script (Easiest)
```bash
./start_dashboard.sh
```

### Option 2: Manual Start
```bash
source .venv/bin/activate
python web_server.py
```

### Option 3: Windows
```bash
.venv\Scripts\activate
python web_server.py
```

The dashboard will be available at: **http://localhost:8080**

---

## 📊 Dashboard Features

### 1. **Real-Time Status Bar**
Located at the top of the dashboard:
- **Running Status** - Green dot = running, Red dot = stopped
- **Gas Price** - Current Ethereum gas price in Gwei
- **Wallet Balance** - Your current ETH balance

### 2. **Control Panel**
Start and stop the arbitrage scanner with one click:
- **▶️ Start Scanner** - Begin scanning for opportunities
- **⏹️ Stop Scanner** - Stop the scanner

### 3. **Statistics Cards**
Four key metrics displayed in beautiful cards:
- **⏱️ Uptime** - How long the scanner has been running
- **🔍 Opportunities** - Total opportunities found
- **✅ Trades** - Number of trades executed
- **💎 Total Profit** - Net profit in ETH

### 4. **Opportunities List**
Real-time list of arbitrage opportunities detected:
- Symbol being traded
- Profit potential
- CEX vs DEX prices
- Spread percentage
- Timestamp

### 5. **Live Updates**
WebSocket connection provides real-time updates:
- Opportunities as they're found
- Trade executions
- System statistics
- Connection status

---

## 🎯 How to Use

### Starting the Scanner

1. **Open the dashboard** at http://localhost:8080
2. **Check the status** - Should show "Stopped" with red dot
3. **Click "Start Scanner"** button
4. **Watch for opportunities** in the list below

### Monitoring

- **Opportunities** appear in real-time as they're found
- **Statistics** update every 5 seconds
- **Connection status** shows at bottom-right corner

### Stopping the Scanner

1. **Click "Stop Scanner"** button
2. **Scanner will gracefully shut down**
3. **Statistics are preserved**

---

## 🎨 UI Components Explained

### Status Indicators
```
🟢 Green Dot = System Running
🔴 Red Dot = System Stopped
🔄 Spinning = Connecting/Reconnecting
```

### Alerts
```
✅ Green Alert = Success
⚠️ Yellow Alert = Warning
❌ Red Alert = Error
ℹ️ Blue Alert = Information
```

### Cards
- **Hover** over cards to see them lift up
- **Click** on cards (future feature for detailed views)

---

## 🌐 API Endpoints

The web server provides these APIs:

### GET `/`
Returns the dashboard HTML

### GET `/api/status`
Get current system status
```json
{
  "running": true,
  "stats": {
    "uptime_seconds": 120,
    "opportunities_found": 5,
    "trades_executed": 2,
    "total_profit_eth": 0.15
  }
}
```

### POST `/api/start`
Start the arbitrage scanner
```json
{
  "dry_run": true,
  "enable_flash": true
}
```

### POST `/api/stop`
Stop the arbitrage scanner

### WebSocket `/ws`
Real-time updates stream

---

## 🔧 Configuration

### Change Port
Edit `web_server.py`:
```python
# Change from 8080 to your preferred port
start_web_server(host="0.0.0.0", port=8080)
```

### Enable Remote Access
By default, the server binds to `0.0.0.0`, making it accessible on your network.

**Access from another device:**
```
http://YOUR_IP_ADDRESS:8080
```

**⚠️ Security Warning:** For production use, add authentication!

### Customize Colors
Edit `web_dashboard.html` - look for these CSS variables:
```css
/* Primary gradient */
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);

/* Change to your preferred colors */
background: linear-gradient(135deg, #your_color1 0%, #your_color2 100%);
```

---

## 📱 Mobile Responsive

The dashboard is fully responsive and works on:
- 💻 Desktop computers
- 📱 Mobile phones
- 🖥️ Tablets
- 📺 Large displays

---

## 🛠️ Troubleshooting

### Dashboard won't load
**Problem:** Browser shows "Can't connect"
**Solution:**
1. Check if server is running
2. Verify port 8080 is not in use
3. Check firewall settings

### WebSocket not connecting
**Problem:** "Reconnecting..." message persists
**Solution:**
1. Refresh the page
2. Check browser console for errors
3. Restart the server

### No opportunities showing
**Problem:** Opportunities list stays empty
**Solution:**
1. Check if scanner is running (green dot)
2. Market may not have opportunities
3. Check console for errors
4. Verify your .env configuration

---

## 🎓 Advanced Usage

### Running on a Server

Deploy to a cloud server for 24/7 access:

```bash
# Install on server
git clone your_repo
cd money_machine
source .venv/bin/activate
pip install -r requirements.txt

# Run with nohup (keeps running after logout)
nohup python web_server.py &

# Or use systemd service (more reliable)
sudo systemctl enable arbitrage-dashboard
sudo systemctl start arbitrage-dashboard
```

### Adding Authentication

For production use, add authentication:

```python
# In web_server.py, add:
from fastapi.security import HTTPBasic, HTTPBasicCredentials
security = HTTPBasic()

@app.get("/")
async def get_dashboard(credentials: HTTPBasicCredentials = Depends(security)):
    # Verify credentials
    if credentials.username != "admin" or credentials.password != "your_password":
        raise HTTPException(status_code=401)
    # ... rest of code
```

### Monitoring Multiple Strategies

Modify `web_server.py` to run multiple scanners:
```python
scanners = {
    "triangular": ArbitrageSystem(strategy="triangular"),
    "cex_dex": ArbitrageSystem(strategy="cex_dex"),
    "flash_loan": ArbitrageSystem(strategy="flash_loan"),
}
```

---

## 📊 Dashboard Screenshots

### Main Dashboard
```
┌────────────────────────────────────────────────────┐
│ 💰 Arbitrage Scanner Dashboard                    │
│ Real-time monitoring and control                   │
│                                                     │
│ [🟢 Running] [⛽ 15.2 Gwei] [💼 0.5 ETH]          │
└────────────────────────────────────────────────────┘

┌──────────────────────────┐ ┌──────────────────────┐
│ ⏱️ Uptime                │ │ 🔍 Opportunities     │
│ 2h 15m 30s              │ │ 47                   │
└──────────────────────────┘ └──────────────────────┘

┌──────────────────────────┐ ┌──────────────────────┐
│ ✅ Trades                │ │ 💎 Total Profit      │
│ 12                      │ │ 0.2500 ETH          │
└──────────────────────────┘ └──────────────────────┘

🎯 Recent Opportunities
┌────────────────────────────────────────────────────┐
│ ETH/USDC              +0.0125 ETH    2 mins ago   │
│ CEX: $3,500 | DEX: $3,510 | Spread: 0.28%        │
└────────────────────────────────────────────────────┘
```

---

## 🚀 Future Enhancements

Planned features:
- [ ] Interactive charts (profit over time)
- [ ] Trade history with filtering
- [ ] Email/SMS alerts for opportunities
- [ ] Mobile app (iOS/Android)
- [ ] Multi-strategy comparison
- [ ] Performance analytics
- [ ] Risk metrics dashboard

---

## 📞 Support

### Files Created
1. `web_server.py` - FastAPI backend server
2. `web_dashboard.html` - Beautiful frontend UI
3. `start_dashboard.sh` - Easy startup script
4. `UI_GUIDE.md` - This guide

### Quick Commands
```bash
# Start dashboard
./start_dashboard.sh

# Or manually
python web_server.py

# Access in browser
http://localhost:8080
```

---

**Enjoy your beautiful arbitrage dashboard!** 🎉💰

*Created: 2025-11-28*
*Status: ✅ Production Ready*
*Tech Stack: FastAPI + WebSocket + Modern CSS*
