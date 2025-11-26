#!/usr/bin/env python3
"""Quick non-interactive broker connection test."""

import asyncio

from src.brokers.alpaca_adapter import AlpacaAdapter
from src.brokers.config import AlpacaConfig


async def test_connection():
    """Test Alpaca connection."""
    print("🔌 TESTING ALPACA CONNECTION")
    print("=" * 80)

    # Load config
    config = AlpacaConfig.from_env()
    print(f"✓ Loaded config (paper={config.paper})")

    # Initialize adapter
    adapter = AlpacaAdapter(config.api_key, config.api_secret, paper=config.paper)
    print("✓ Adapter initialized")

    # Test connection by getting account info
    try:
        account = await adapter.get_account()
        print(f"✓ Connected to Alpaca!")
        print(f"\n📊 Account Info:")
        print(f"  - Buying Power: ${account.buying_power:,.2f}")
        print(f"  - Cash: ${account.cash:,.2f}")
        print(f"  - Portfolio Value: ${account.portfolio_value:,.2f}")
        print(f"  - Pattern Day Trader: {account.pattern_day_trader}")

        # Test getting positions
        positions = await adapter.get_positions()
        print(f"\n📈 Positions: {len(positions)}")
        for pos in positions:
            print(f"  - {pos.symbol}: {pos.quantity} shares @ ${pos.avg_price:.2f}")

        # Test getting orders
        orders = await adapter.get_orders(status="open")
        print(f"\n📝 Open Orders: {len(orders)}")

        print("\n" + "=" * 80)
        print("✅ All connection tests passed!")
        return True

    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_connection())
    exit(0 if success else 1)
