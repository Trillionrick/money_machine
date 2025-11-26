#!/usr/bin/env python3
"""Test Kraken exchange connection.

Before running:
1. Get API keys from https://www.kraken.com/u/security/api
2. Add to .env:
   KRAKEN_API_KEY=your_api_key
   KRAKEN_API_SECRET=your_api_secret
3. Ensure API key has permissions:
   - Query Funds
   - Query Open Orders & Trades
   - Create & Modify Orders (optional for testing)
"""

import asyncio

from src.brokers.credentials import BrokerCredentials
from src.brokers.kraken_adapter import KrakenAdapter


async def test_connection():
    """Test Kraken connection and API calls."""
    print("🔌 TESTING KRAKEN CONNECTION")
    print("=" * 80)

    # Load credentials
    try:
        creds = BrokerCredentials()
        if not creds.has_kraken():
            print("❌ Kraken credentials not configured in .env")
            print("\nAdd these to your .env file:")
            print("KRAKEN_API_KEY=your_api_key")
            print("KRAKEN_API_SECRET=your_api_secret")
            return False
        print("✓ Loaded credentials")
    except Exception as e:
        print(f"❌ Error loading credentials: {e}")
        return False

    # Initialize adapter
    async with KrakenAdapter(
        api_key=creds.kraken_api_key.get_secret_value(),
        api_secret=creds.kraken_api_secret.get_secret_value(),
    ) as adapter:
        print("✓ Adapter initialized")

        try:
            # Test 1: Server time (public endpoint)
            print("\n" + "=" * 80)
            print("TEST 1: Server Time (Public Endpoint)")
            print("=" * 80)

            server_time = await adapter.get_server_time()
            print(f"✓ Server Time: {server_time}")

            # Test 2: Ticker (public endpoint)
            print("\n" + "=" * 80)
            print("TEST 2: Ticker - BTC/USD")
            print("=" * 80)

            ticker = await adapter.get_ticker("XXBTZUSD")
            if ticker:
                btc_data = ticker.get("XXBTZUSD", {})
                if btc_data:
                    ask = btc_data.get("a", ["0"])[0]
                    bid = btc_data.get("b", ["0"])[0]
                    last = btc_data.get("c", ["0"])[0]
                    print(f"✓ BTC/USD Price:")
                    print(f"  - Last: ${float(last):,.2f}")
                    print(f"  - Bid:  ${float(bid):,.2f}")
                    print(f"  - Ask:  ${float(ask):,.2f}")

            # Test 3: Account balance (private endpoint)
            print("\n" + "=" * 80)
            print("TEST 3: Account Balance (Private Endpoint)")
            print("=" * 80)

            balances = await adapter.get_account()
            print(f"✓ Account balances retrieved")
            print(f"\n📊 Balances ({len(balances)} assets):")

            for asset, amount in balances.items():
                amount_float = float(amount)
                if amount_float > 0:
                    print(f"  - {asset}: {amount_float:,.8f}")

            # Test 4: Trade balance
            print("\n" + "=" * 80)
            print("TEST 4: Trade Balance")
            print("=" * 80)

            trade_balance = await adapter.get_trade_balance()
            print(f"✓ Trade balance retrieved")
            print(f"\n💰 Trade Balance:")
            print(f"  - Equity: ${float(trade_balance.get('eb', 0)):,.2f}")
            print(f"  - Free Margin: ${float(trade_balance.get('mf', 0)):,.2f}")
            print(
                f"  - Margin Used: ${float(trade_balance.get('m', 0)):,.2f}"
            )

            # Test 5: Open orders
            print("\n" + "=" * 80)
            print("TEST 5: Open Orders")
            print("=" * 80)

            open_orders = await adapter.get_orders(status="open")
            print(f"✓ Open orders: {len(open_orders)}")

            if open_orders:
                for order in open_orders[:5]:  # Show first 5
                    print(f"  - {order.get('descr', {}).get('order', 'N/A')}")

            # Test 6: Open positions
            print("\n" + "=" * 80)
            print("TEST 6: Open Positions")
            print("=" * 80)

            positions = await adapter.get_positions()
            print(f"✓ Open positions: {len(positions)}")

            if positions:
                for pos in positions:
                    print(f"  - Position: {pos}")

            print("\n" + "=" * 80)
            print("✅ ALL TESTS PASSED!")
            print("=" * 80)
            print("\n🎯 Kraken connection is working!")
            print("\nYou can now:")
            print("  - Trade cryptocurrencies on Kraken")
            print("  - Access 200+ crypto pairs")
            print("  - Use fiat currencies (USD, EUR, GBP, CAD)")
            print("\nNext steps:")
            print("  - Review BROKERAGE_CONNECTIONS.md for full guide")
            print("  - Start with small test trades")
            print("  - Enable rate limiting for production")

            return True

        except Exception as e:
            print(f"\n❌ Connection test failed: {e}")
            import traceback

            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = asyncio.run(test_connection())
    exit(0 if success else 1)
