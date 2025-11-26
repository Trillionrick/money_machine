##Examples & Tutorials

This directory contains working examples demonstrating the trading system's capabilities.

## Quick Start

### 1. Complete Backtest Example

The best place to start - demonstrates the entire workflow:

bash
cd /mnt/c/Users/catty/Desktop/money_machine
source .venv/bin/activate
python examples/complete_backtest.py


**What it shows:**
- Loading market data
- Creating a momentum strategy with Kelly sizing
- Running a backtest with realistic execution
- Analyzing performance with comprehensive metrics
- Understanding what the numbers mean

**Expected output:**
- Performance report with Sharpe ratio, drawdowns, trade statistics
- Key insights about strategy quality
- Next steps for improvement

### 2. Strategy Comparison

Compare three different strategy types side-by-side:

bash
python examples/strategy_comparison.py


**Strategies tested:**

1. **Market Making** (House Edge)
   - Philosophy: Be the casino, not the gambler
   - Edge: Capture bid-ask spread on every transaction
   - Best for: Liquid markets, high frequency
   - Win rate: ~60-70%, small consistent wins

2. **Momentum** (Trend Following)
   - Philosophy: Ride behavioral under-reaction to news
   - Edge: Trends persist longer than rational
   - Best for: Trending markets
   - Win rate: ~45-50%, large wins compensate

3. **Pairs Trading** (Statistical Arbitrage)
   - Philosophy: Mean reversion in cointegrated assets
   - Edge: Temporary mispricings correct
   - Best for: Correlated assets
   - Win rate: ~55-60%, market-neutral

**Expected output:**
- Side-by-side performance comparison
- Insights on which strategy works best for which market conditions

## File Descriptions

### `complete_backtest.py`
Full end-to-end backtest example with:
- Synthetic data generation
- Strategy configuration
- Backtest execution
- Performance analysis
- Detailed reporting

**Key concepts:**
- How to set up a backtest
- Configuring strategy parameters
- Reading performance metrics
- Making decisions based on results

### `strategy_comparison.py`
Compare multiple strategies on the same data:
- Market Making strategy
- Momentum strategy
- Pairs Trading strategy

**Key concepts:**
- Different edge types
- Strategy selection by market regime
- Risk/return trade-offs
- Diversification benefits

## Understanding the Output

### Sharpe Ratio
- **> 2.0**: Excellent (institutional quality)
- **1.0-2.0**: Good (retail trader territory)
- **< 1.0**: Needs improvement

### Max Drawdown
- **< 10%**: Very conservative
- **10-20%**: Moderate
- **> 20%**: Aggressive (most can't psychologically handle this)

### Win Rate
- **Market Making**: Expect 60-70%
- **Momentum**: Expect 40-50% (asymmetric payoffs compensate)
- **Mean Reversion**: Expect 55-65%

## Customization

### Modify Strategy Parameters

Edit the config objects:

python
config = MomentumConfig(
    lookback_periods=20,      # Increase for slower signals
    entry_threshold=1.5,      # Increase for more selective entries
    kelly_fraction=0.25,      # Decrease for more conservative sizing
    max_drawdown=0.15,        # Tighten risk control
)


### Use Real Data

Replace synthetic data with real prices:

python
from src.data import DataStore

store = DataStore(Path("./data"))
market_data = {
    "AAPL": store.load_bars("AAPL", "1h"),
    "GOOGL": store.load_bars("GOOGL", "1h"),
}


### Add Risk Management

Wrap your strategy with risk limits:

python
from src.core.risk import RiskManager, RiskLimits

risk_mgr = RiskManager(
    limits=RiskLimits(
        max_position_pct=0.20,
        max_daily_loss_pct=0.05,
    )
)

# Filter orders through risk manager
safe_orders = risk_mgr.filter_orders(orders, portfolio, current_prices)


## Next Steps

1. **Run the examples** - Understand what "good" looks like
2. **Modify parameters** - See how strategy behavior changes
3. **Add your own strategy** - Implement in `src/research/strategies.py`
4. **Backtest thoroughly** - Test on multiple time periods
5. **Paper trade** - Test with live data, no risk
6. **Go live cautiously** - Start small, scale gradually

## Philosophy Refresher

From the design document:

> "Don't look for magic trades; look for game designs where small equity controls large optionality with structurally positive drift."

These examples demonstrate three types of "game design":

1. **Market Making**: Structural edge from liquidity provision
2. **Momentum**: Behavioral edge from under-reaction
3. **Pairs Trading**: Statistical edge from mean reversion

All use Kelly sizing to maximize long-run growth while controlling ruin risk.

## Troubleshooting

### "No data available"
- Check that data files exist in `./data/`
- Or use the synthetic data generators in examples

### "Trading halted"
- Risk manager circuit breaker triggered
- Check `risk_mgr.halt_reason`
- Adjust risk limits or strategy parameters

### Poor performance
- Strategy might not fit market regime
- Try different parameters
- Compare to buy-and-hold benchmark
- Consider transaction costs

### "Insufficient funds"
- Position sizing too aggressive
- Reduce `kelly_fraction`
- Check `max_position_pct` in risk limits

## Resources

- [Kelly Criterion](https://en.wikipedia.org/wiki/Kelly_criterion)
- [Market Microstructure](https://en.wikipedia.org/wiki/Market_microstructure)
- [Statistical Arbitrage](https://en.wikipedia.org/wiki/Statistical_arbitrage)
- [Risk Management](https://en.wikipedia.org/wiki/Risk_management)

## Warning

These examples are for educational purposes. Trading involves substantial risk. Always:
- Backtest thoroughly on historical data
- Paper trade before going live
- Start with small position sizes
- Understand what you're doing
- Never risk money you can't afford to lose

Past performance doesn't guarantee future results.
