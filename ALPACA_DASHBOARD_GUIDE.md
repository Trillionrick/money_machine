# Alpaca Trading Dashboard Guide

## Overview

The Alpaca Trading Dashboard is a dedicated web interface for algorithmic trading of US stocks and cryptocurrencies using the Alpaca API. It runs on **port 8081** and is completely separate from the main arbitrage dashboard (port 8080).

## Features

- **Real-time Account Monitoring**: View cash, equity, buying power, and PDT status
- **Market & Limit Orders**: Place buy/sell orders with market or limit execution
- **Position Management**: Monitor open positions with P&L tracking
- **Order Tracking**: View and cancel open orders
- **Quick Actions**: Close positions and cancel orders with one click

## Getting Started

### Prerequisites

1. **Alpaca API Keys**: Get your API keys from [alpaca.markets](https://alpaca.markets)
2. **Python Environment**: Ensure you have Python 3.11+ installed
3. **Dependencies**: Make sure `alpaca-py` is installed

### Configuration

Your Alpaca credentials are already configured in `.env`:

```bash
ALPACA_API_KEY=CKK76PKT6YIWGCN64CRIKMTPNA
ALPACA_API_SECRET=AYW6CwJ1gEWiRPkc6RydH6UqE71iPj5GL7VDq5U9WTwG
ALPACA_PAPER=false  # false = live trading, true = paper trading
```

⚠️ **IMPORTANT**: Currently set to `ALPACA_PAPER=false` (LIVE TRADING). Change to `true` for paper trading if you want to test without real money.

### Starting the Dashboard

#### Option 1: Using the startup script (Recommended)
```bash
./start_alpaca_dashboard.sh
```

#### Option 2: Direct Python
```bash
python alpaca_server.py
```

The dashboard will be available at: **http://localhost:8081**

### Access from Other Dashboards

- From **Production Dashboard** (localhost:8080): Click the "📈 Alpaca Trading" link
- From **Classic Dashboard** (localhost:8080/classic): Click the "📈 Alpaca Trading" link

## Dashboard Sections

### Account Summary

Four key metrics displayed at the top:
- **💰 Cash**: Available cash for trading
- **💼 Equity**: Total account value (cash + positions)
- **⚡ Buying Power**: Available buying power (includes margin)
- **📊 PDT Status**: Pattern Day Trader status

### Trading Panel

Three trading cards for placing orders:

1. **Market Order**
   - Executes immediately at current market price
   - Best for high liquidity stocks
   - Example: Buy 10 shares of SPY at market

2. **Limit Order**
   - Executes only at specified price or better
   - Set your desired entry/exit price
   - Example: Buy 10 shares of AAPL at $150.00

3. **Quick Actions**
   - Cancel open orders (all or by symbol)
   - Close positions (market order opposite direction)

### Current Positions

Table showing all open positions with:
- Symbol and quantity
- Average entry price vs current price
- Market value
- Unrealized P&L ($ and %)
- Quick close button

### Open Orders

Table showing all pending orders with:
- Symbol, side (BUY/SELL), type (MARKET/LIMIT)
- Quantity and limit price
- Order status and timestamp
- Cancel button

## Trading Operations

### Placing a Market Order

1. Enter symbol (e.g., `SPY`, `AAPL`, `TSLA`)
2. Enter quantity (number of shares)
3. Select side (Buy or Sell)
4. Click "Place Market Order"

### Placing a Limit Order

1. Enter symbol
2. Enter quantity
3. Enter limit price (e.g., `150.00`)
4. Select side
5. Click "Place Limit Order"

### Closing a Position

**Method 1: From Positions Table**
- Click the "Close" button next to any position

**Method 2: From Quick Actions**
1. Enter symbol in the "Symbol (for cancel)" field
2. Click "Close Position"

### Canceling Orders

**Cancel All Orders**
- Leave symbol field empty
- Click "Cancel Open Orders"

**Cancel by Symbol**
- Enter symbol
- Click "Cancel Open Orders"

## API Endpoints

The dashboard uses these backend endpoints:

- `GET /api/alpaca/account` - Account information
- `GET /api/alpaca/positions` - Current positions
- `GET /api/alpaca/orders` - Open orders
- `POST /api/alpaca/order/market` - Place market order
- `POST /api/alpaca/order/limit` - Place limit order
- `DELETE /api/alpaca/order/{order_id}` - Cancel specific order
- `POST /api/alpaca/orders/cancel` - Cancel all orders
- `DELETE /api/alpaca/position/{symbol}` - Close position

## Safety Features

1. **Paper Trading Mode**: Set `ALPACA_PAPER=true` to test without real money
2. **Confirmation Dialogs**: All destructive actions (cancel, close) require confirmation
3. **Real-time Updates**: Dashboard auto-refreshes every 5 seconds
4. **Error Alerts**: Clear error messages for failed operations

## Troubleshooting

### Dashboard won't start

1. Check if port 8081 is already in use:
   ```bash
   lsof -i :8081
   ```

2. Verify Alpaca credentials are set in `.env`

3. Ensure `alpaca-py` is installed:
   ```bash
   pip install alpaca-py
   ```

### Orders failing

1. Check account buying power
2. Verify symbol is valid (US stocks/crypto only)
3. Check if market is open (stocks trade Mon-Fri 9:30am-4pm EST)
4. Review Alpaca dashboard for account restrictions

### Can't connect to API

1. Verify API keys are correct
2. Check if using correct endpoint (paper vs live)
3. Look at server logs for detailed error messages

## Architecture

```
money_machine/
├── alpaca_server.py              # FastAPI backend (port 8081)
├── alpaca_dashboard.html         # Frontend UI
├── start_alpaca_dashboard.sh     # Startup script
├── src/brokers/alpaca_adapter.py # Alpaca API integration
└── .env                          # API credentials
```

## Development

### Adding New Features

1. **Backend**: Add endpoints to `alpaca_server.py`
2. **Frontend**: Update `alpaca_dashboard.html` JavaScript
3. **Integration**: Use `src/brokers/alpaca_adapter.py` for API calls

### Testing

Run the dashboard in paper trading mode:
```bash
# Set in .env
ALPACA_PAPER=true

# Start dashboard
./start_alpaca_dashboard.sh
```

## Resources

- [Alpaca API Documentation](https://alpaca.markets/docs/)
- [Alpaca-py SDK](https://github.com/alpacahq/alpaca-py)
- [Alpaca Markets](https://alpaca.markets/)

## Support

For issues or questions:
1. Check the [Alpaca API documentation](https://alpaca.markets/docs/)
2. Review server logs in the terminal
3. Check browser console for frontend errors

---

**Remember**: Always test with paper trading (`ALPACA_PAPER=true`) before going live!
