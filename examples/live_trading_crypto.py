"""Live cryptocurrency trading with aggressive ML policy.

Trades crypto 24/7 with target-utility optimization.

Key differences from stock trading:
- 24/7 trading (markets never close)
- No margin/leverage (cash only)
- Higher volatility (adjust risk limits)
- GTC time-in-force (not DAY)
- Crypto symbols use "/" format (BTC/USD not BTCUSD)
"""

import asyncio
from collections.abc import AsyncIterator

import polars as pl
import structlog

from src.brokers.alpaca_adapter import AlpacaAdapter
from src.brokers.config import AlpacaConfig, TradingConfig
from src.core.policy import MarketSnapshot, PortfolioState
from src.core.risk import RiskLimits, RiskManager
from src.live.engine import LiveEngine
from src.ml.aggressive_policy import AdaptiveAggressivePolicy

log = structlog.get_logger()


async def create_crypto_data_feed(
    symbols: list[str],
) -> AsyncIterator[MarketSnapshot]:
    """Create live crypto market data feed.

    Crypto markets never close, so this runs 24/7.

    Args:
        symbols: Crypto symbols to track (e.g., ["BTC/USD", "ETH/USD"])

    Yields:
        Market snapshots
    """
    import yfinance as yf  # noqa: PLC0415

    while True:
        try:
            prices = {}
            volumes = {}

            for symbol in symbols:
                # Convert BTC/USD to BTC-USD for yfinance
                yf_symbol = symbol.replace("/", "-")
                ticker = yf.Ticker(yf_symbol)
                data = ticker.history(period="1d", interval="1m")

                if len(data) > 0:
                    prices[symbol] = float(data["Close"].iloc[-1])
                    volumes[symbol] = float(data["Volume"].iloc[-1])

            if prices:
                snapshot = MarketSnapshot(
                    timestamp=int(asyncio.get_event_loop().time() * 1e9),
                    prices=prices,
                    volumes=volumes,
                )
                yield snapshot

            # Update every minute
            await asyncio.sleep(60)

        except Exception:
            log.exception("crypto_data.error")
            await asyncio.sleep(5)


async def main() -> None:
    """Run live crypto trading."""
    print("=" * 80)
    print("LIVE CRYPTO TRADING - 24/7 AGGRESSIVE ML POLICY")
    print("=" * 80)
    print()

    # Load configs
    try:
        alpaca_config = AlpacaConfig.from_env()
        trading_config = TradingConfig.from_env()
    except Exception as e:
        print(f"✗ Configuration error: {e}")
        return

    # Verify paper trading
    if not alpaca_config.paper:
        print("⚠️  WARNING: LIVE TRADING MODE DETECTED")
        print()
        response = input("Trade REAL crypto with real money? (yes/no): ").lower()
        if response != "yes":
            print("Exiting for safety. Set ALPACA_PAPER=true for paper trading.")
            return

    # Show configuration
    print("Configuration:")
    print(f"  Mode: {'PAPER' if alpaca_config.paper else '⚠️  LIVE'}")
    print(f"  Starting Capital: ${trading_config.starting_capital:,.2f}")
    print(f"  Target Wealth: ${trading_config.target_wealth:,.2f}")
    print(f"  Time Horizon: {trading_config.time_horizon_days} days")
    print(f"  Max Leverage: 1.0x (crypto is cash-only)")
    print()

    # Initialize broker adapter
    print("Connecting to Alpaca...")
    adapter = AlpacaAdapter(
        api_key=alpaca_config.api_key,
        api_secret=alpaca_config.api_secret,
        paper=alpaca_config.paper,
    )

    # Get account info and check crypto status
    account = await adapter.get_account()
    crypto_status = account.get("crypto_status", "INACTIVE")

    print(f"✓ Connected")
    print(f"  Cash: ${account['cash']:,.2f}")
    print(f"  Equity: ${account['equity']:,.2f}")
    print(f"  Crypto Status: {crypto_status}")
    print()

    if crypto_status != "ACTIVE":
        print("✗ Crypto trading not enabled")
        print("  In paper mode, this should be enabled automatically.")
        print("  Contact Alpaca if this persists.")
        return

    # Crypto symbols to trade
    # Start with most liquid (BTC, ETH)
    symbols = ["BTC/USD", "ETH/USD", "SOL/USD"]
    print(f"Trading Symbols: {', '.join(symbols)}")
    print("  Note: Crypto trades 24/7 (markets never close)")
    print()

    # Initialize risk manager with crypto-adjusted limits
    print("Initializing risk manager...")
    risk_manager = RiskManager(
        limits=RiskLimits(
            max_position_pct=0.20,  # Lower for crypto (more volatile)
            max_leverage=1.0,  # Crypto is cash-only
            max_daily_loss_pct=0.08,  # Tighter for crypto
            max_drawdown_pct=0.40,  # Lower than stocks (crypto is volatile)
        )
    )
    print("✓ Risk manager initialized (crypto-adjusted limits)")
    print("  Max Position: 20% (vs 30% for stocks)")
    print("  Max Leverage: 1.0x (no margin for crypto)")
    print("  Daily Loss Limit: 8% (vs 10% for stocks)")
    print("  Max Drawdown: 40% (vs 50% for stocks)")
    print()

    # Initialize aggressive ML policy
    print("Initializing ML policy...")
    policy = AdaptiveAggressivePolicy(
        symbols=symbols,
        target_wealth=trading_config.target_wealth,
        current_wealth=float(account["equity"]),
        time_horizon_days=trading_config.time_horizon_days,
        max_positions=3,
        min_convexity_score=0.15,  # Higher for crypto (more volatile)
        max_leverage=1.0,  # Crypto is cash-only
    )
    print("✓ Policy initialized")
    print("  Min Convexity Score: 0.15 (higher for crypto volatility)")
    print()

    # Create market data feed
    print("Starting crypto data feed...")
    data_feed = create_crypto_data_feed(symbols)
    print("✓ Data feed started (24/7)")
    print()

    # Create live engine
    print("Initializing trading engine...")
    engine = LiveEngine(
        exec_engine=adapter,
        data_feed=data_feed,
        policy=policy,
        tick_rate_hz=0.017,  # ~1 per minute
    )
    print("✓ Engine initialized")
    print()

    # Final safety check
    print("=" * 80)
    print("FINAL SAFETY CHECK - CRYPTO TRADING")
    print("=" * 80)
    print()
    print("Crypto Trading Acknowledgments:")
    print("  [✓] Crypto is MORE volatile than stocks (50-80% drawdowns possible)")
    print("  [✓] Markets are open 24/7 (large moves can happen anytime)")
    print("  [✓] No margin/leverage available (cash-only trading)")
    print("  [✓] This is aggressive + crypto = HIGHEST RISK")
    print("  [✓] I can afford to lose 100% of this capital")
    print("  [✓] I will monitor continuously (or accept gap risk)")
    print("  [✓] I have exit criteria defined")
    print()

    response = input("Start crypto trading? (yes/no): ").lower()
    if response != "yes":
        print("Trading cancelled")
        return

    # Run trading engine
    print()
    print("=" * 80)
    print("CRYPTO TRADING STARTED - 24/7 OPERATION")
    print("=" * 80)
    print()
    print("Trading cryptocurrencies with aggressive ML policy")
    print("Markets never close - system will run continuously")
    print("Press Ctrl+C to stop")
    print()

    try:
        async with engine.lifecycle():
            await engine.run()

    except KeyboardInterrupt:
        print()
        print("=" * 80)
        print("CRYPTO TRADING STOPPED BY USER")
        print("=" * 80)
        print()

        # Show final status
        final_account = await adapter.get_account()
        print("Final Account Status:")
        print(f"  Cash: ${final_account['cash']:,.2f}")
        print(f"  Equity: ${final_account['equity']:,.2f}")
        print()

        positions = await adapter.get_positions()
        crypto_positions = {
            sym: qty for sym, qty in positions.items()
            if "/" in sym  # Crypto symbols have "/"
        }
        print(f"Crypto Positions: {len(crypto_positions)}")
        for symbol, qty in crypto_positions.items():
            print(f"  {symbol}: {qty}")
        print()

    except Exception:
        log.exception("crypto_trading.error")
        print()
        print("✗ Crypto trading stopped due to error")
        print("  Check logs for details")


if __name__ == "__main__":
    # Configure logging
    from src.live.engine import configure_logging

    configure_logging(json_output=False, level="INFO")

    # Run
    asyncio.run(main())
