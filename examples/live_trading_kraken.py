#!/usr/bin/env python3
"""Live crypto trading on Kraken exchange.

This example shows how to trade cryptocurrencies on Kraken using your
aggressive ML policy with Kraken-specific configuration.

Before running:
1. Get API keys: https://www.kraken.com/u/security/api
2. Configure .env with Kraken credentials
3. Test connection with: python examples/test_kraken_connection.py
4. Start with small position sizes!

Safety features:
- Crypto-specific risk limits (more conservative)
- Circuit breakers on losses/drawdown
- Order validation
- DRY_RUN mode available
"""

import asyncio

import structlog

from src.brokers.credentials import BrokerCredentials
from src.brokers.kraken_adapter import KrakenAdapter
from src.core.policy import AdaptiveAggressivePolicy
from src.core.risk import RiskLimits, RiskManager
from src.live.engine import LiveTradingEngine

log = structlog.get_logger()


async def main():
    """Run live crypto trading on Kraken."""
    print("🚀 KRAKEN LIVE TRADING")
    print("=" * 80)

    # Load credentials
    creds = BrokerCredentials()
    if not creds.has_kraken():
        print("❌ Kraken credentials not configured!")
        print("\nAdd to .env:")
        print("KRAKEN_API_KEY=your_api_key")
        print("KRAKEN_API_SECRET=your_api_secret")
        return

    print("✓ Loaded Kraken credentials")

    # Initialize Kraken adapter
    adapter = KrakenAdapter(
        api_key=creds.kraken_api_key.get_secret_value(),
        api_secret=creds.kraken_api_secret.get_secret_value(),
    )

    # Check account
    try:
        balances = await adapter.get_account()
        trade_balance = await adapter.get_trade_balance()

        equity = float(trade_balance.get("eb", 0))
        print(f"✓ Account equity: ${equity:,.2f}")

        if equity < 100:
            print("\n⚠️  Warning: Low account balance")
            print(f"   Current: ${equity:,.2f}")
            print("   Recommended: $500+ for crypto trading")
            response = input("\nContinue anyway? (yes/no): ")
            if response.lower() != "yes":
                return

    except Exception as e:
        print(f"❌ Failed to fetch account info: {e}")
        return

    # Crypto-specific risk limits (more conservative)
    risk_limits = RiskLimits(
        max_position_pct=0.20,  # 20% max per position (vs 30% for stocks)
        max_leverage=1.0,  # Spot only - no leverage
        max_daily_loss_pct=0.08,  # 8% daily loss limit
        max_drawdown_pct=0.40,  # 40% max drawdown
    )

    risk_manager = RiskManager(limits=risk_limits)
    print("✓ Risk limits configured (crypto-conservative)")

    # Configure trading policy
    # Kraken symbol format: use standard "BTC/USD" format
    symbols = [
        "BTC/USD",  # Bitcoin
        "ETH/USD",  # Ethereum
        "SOL/USD",  # Solana
    ]

    policy = AdaptiveAggressivePolicy(
        symbols=symbols,
        min_convexity_score=0.15,  # Higher threshold for crypto volatility
        max_leverage=1.0,  # Spot only
    )

    print(f"✓ Trading policy configured")
    print(f"  - Symbols: {', '.join(symbols)}")
    print(f"  - Min convexity: 0.15")
    print(f"  - Leverage: 1x (spot only)")

    # Initialize live trading engine
    engine = LiveTradingEngine(
        policy=policy,
        adapter=adapter,
        risk_manager=risk_manager,
    )

    print("\n" + "=" * 80)
    print("🎯 STARTING LIVE TRADING")
    print("=" * 80)
    print("\n⚠️  IMPORTANT:")
    print("  - This is LIVE trading with REAL MONEY")
    print("  - Crypto is highly volatile (24/7 markets)")
    print("  - You can lose your entire investment")
    print("  - Start with small position sizes")
    print("  - Monitor closely for first few days")
    print("\n✓ Safety features enabled:")
    print("  - Max 20% per position")
    print("  - 8% daily loss circuit breaker")
    print("  - 40% drawdown circuit breaker")
    print("  - No leverage (spot only)")
    print("\n" + "=" * 80)

    # Confirm before starting
    response = input("\nStart live trading? (type 'START' to confirm): ")
    if response != "START":
        print("Cancelled.")
        return

    print("\n🟢 Live trading started!")
    print("Press Ctrl+C to stop\n")

    try:
        # Run live trading loop
        await engine.run()

    except KeyboardInterrupt:
        print("\n\n🛑 Stopping trading...")
        log.info("live.trading.stopped", reason="user_interrupt")

    except Exception as e:
        print(f"\n\n❌ Trading error: {e}")
        log.error("live.trading.error", error=str(e))

    finally:
        # Cleanup
        await adapter.close()
        print("✓ Disconnected from Kraken")
        print("\nFinal stats:")
        # TODO: Print final P&L, win rate, etc.


if __name__ == "__main__":
    # Setup logging
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )

    asyncio.run(main())
