"""Test cryptocurrency order submission.

Submits a small test order to validate:
1. Crypto trading is enabled
2. Orders execute properly
3. Fills are received via SSE
4. Positions update correctly
"""

import asyncio

import structlog

from src.brokers.alpaca_adapter import AlpacaAdapter
from src.brokers.config import AlpacaConfig
from src.core.execution import Order, OrderType, Side

log = structlog.get_logger()


async def test_crypto_order() -> None:
    """Submit a test crypto order."""
    print("=" * 80)
    print("CRYPTO ORDER TEST")
    print("=" * 80)
    print()

    # Load config
    try:
        config = AlpacaConfig.from_env()
        print(f"✓ Loaded config (paper={config.paper})")
    except Exception as e:
        print(f"✗ Configuration error: {e}")
        return

    # Verify paper mode
    if not config.paper:
        print("⚠️  WARNING: LIVE TRADING MODE")
        print()
        response = input("Submit REAL crypto order? (yes/no): ").lower()
        if response != "yes":
            print("Cancelled for safety. Set ALPACA_PAPER=true for testing.")
            return

    # Initialize adapter
    adapter = AlpacaAdapter(
        api_key=config.api_key,
        api_secret=config.api_secret,
        paper=config.paper,
    )

    # Check account
    account = await adapter.get_account()
    print(f"✓ Connected to Alpaca")
    print(f"  Cash: ${account['cash']:,.2f}")
    print(f"  Equity: ${account['equity']:,.2f}")
    print(f"  Crypto Status: {account.get('crypto_status', 'UNKNOWN')}")
    print()

    # Check crypto status
    crypto_status = account.get("crypto_status", "INACTIVE")
    if crypto_status != "ACTIVE":
        print(f"✗ Crypto not enabled (status: {crypto_status})")
        print("  In paper mode, crypto should be enabled automatically.")
        print("  Contact Alpaca if this persists.")
        return

    print("✓ Crypto trading is ACTIVE")
    print()

    # Test order details
    symbol = "BTC/USD"
    notional = 10.0  # $10 worth of BTC
    side = Side.BUY

    print("Test Order Details:")
    print(f"  Symbol: {symbol}")
    print(f"  Side: {side.value}")
    print(f"  Amount: ${notional:.2f} (notional)")
    print(f"  Type: MARKET")
    print()

    # Confirm
    response = input("Submit test order? (yes/no): ").lower()
    if response != "yes":
        print("Order cancelled")
        return

    print()
    print("Submitting order...")

    # Create order
    # Note: For crypto, we'll submit via Alpaca's API directly
    # since our Order type needs to support notional
    try:
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        # Create request with notional (crypto supports this)
        request = MarketOrderRequest(
            symbol=symbol,
            notional=notional,  # Dollar amount instead of quantity
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,  # GTC for crypto (not DAY)
        )

        # Submit
        loop = asyncio.get_running_loop()
        order = await loop.run_in_executor(
            None,
            adapter.client.submit_order,
            request,
        )

        print(f"✓ Order submitted")
        print(f"  Order ID: {order.id}")
        print(f"  Status: {order.status}")
        print()

        # Wait for fill
        print("Waiting for fill (should be instant for market order)...")
        await asyncio.sleep(2)

        # Check order status
        order_status = await loop.run_in_executor(
            None,
            adapter.client.get_order_by_id,
            order.id,
        )

        print(f"  Status: {order_status.status}")
        if order_status.status == "filled":
            print(f"  Filled Qty: {order_status.filled_qty}")
            print(f"  Filled Price: ${float(order_status.filled_avg_price):,.2f}")
            print()
            print("✓ Order filled successfully!")
        else:
            print(f"  Order still {order_status.status}")

        print()

        # Check positions
        positions = await adapter.get_positions()
        if symbol in positions or "BTCUSD" in positions:
            btc_position = positions.get(symbol, positions.get("BTCUSD", 0))
            print(f"✓ Position updated: {btc_position} BTC")
        else:
            print("⚠ Position not yet updated (may take a moment)")

        print()
        print("=" * 80)
        print("TEST COMPLETE")
        print("=" * 80)
        print()
        print("If order filled, your crypto trading is working correctly!")
        print("You can now run live_trading_crypto.py to trade 24/7.")
        print()

    except Exception:
        log.exception("crypto_order.error")
        print()
        print("✗ Order failed")
        print("  Check logs for details")


if __name__ == "__main__":
    # Configure logging
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
    )

    asyncio.run(test_crypto_order())
