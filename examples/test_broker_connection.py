"""Test broker connections before going live.

This script:
1. Loads credentials from .env
2. Connects to broker
3. Checks account status
4. Tests order submission (with safety checks)
5. Validates everything works

Run this BEFORE live trading!
"""

import asyncio

import structlog

from src.brokers.alpaca_adapter import AlpacaAdapter
from src.brokers.binance_adapter import BinanceAdapter
from src.brokers.config import AlpacaConfig, BinanceConfig, TradingConfig
from src.core.execution import Order, OrderType, Side

log = structlog.get_logger()


async def test_alpaca() -> None:
    """Test Alpaca connection."""
    print("=" * 80)
    print("TESTING ALPACA CONNECTION")
    print("=" * 80)
    print()

    try:
        # Load config
        config = AlpacaConfig.from_env()
        print(f"✓ Loaded config (paper={config.paper})")

        # Initialize adapter
        adapter = AlpacaAdapter(
            api_key=config.api_key,
            api_secret=config.api_secret,
            paper=config.paper,
        )
        print("✓ Initialized adapter")

        # Get account info
        account = await adapter.get_account()
        print()
        print("Account Information:")
        print(f"  Cash: ${account['cash']:,.2f}")
        print(f"  Equity: ${account['equity']:,.2f}")
        print(f"  Buying Power: ${account['buying_power']:,.2f}")
        print(f"  Pattern Day Trader: {account['pattern_day_trader']}")
        print()

        # Get positions
        positions = await adapter.get_positions()
        print(f"Current Positions: {len(positions)}")
        for symbol, qty in positions.items():
            print(f"  {symbol}: {qty} shares")
        print()

        # Get open orders
        open_orders = await adapter.get_open_orders()
        print(f"Open Orders: {len(open_orders)}")
        for order in open_orders:
            print(f"  {order.symbol} {order.side.value} {order.quantity}")
        print()

        print("✓ Alpaca connection successful!")
        print()

        # Prompt for test order
        if config.paper:
            response = input("Submit test order? (yes/no): ").lower()
            if response == "yes":
                await test_alpaca_order(adapter)

    except Exception:
        log.exception("alpaca.test_failed")
        print("✗ Alpaca connection failed")


async def test_alpaca_order(adapter: AlpacaAdapter) -> None:
    """Submit a test order to Alpaca.

    Args:
        adapter: Alpaca adapter
    """
    print()
    print("Submitting test order...")
    print("  Symbol: AAPL")
    print("  Side: BUY")
    print("  Quantity: 1 share")
    print("  Type: MARKET")
    print()

    # Create test order
    test_order = Order(
        symbol="AAPL",
        side=Side.BUY,
        quantity=1.0,
        order_type=OrderType.MARKET,
    )

    try:
        # Submit
        await adapter.submit_orders([test_order])
        print("✓ Order submitted successfully!")

        # Wait a moment
        await asyncio.sleep(2)

        # Check positions
        positions = await adapter.get_positions()
        if "AAPL" in positions:
            print(f"✓ Position updated: AAPL = {positions['AAPL']} shares")
        else:
            print("⚠ Order pending or not yet filled")

    except Exception:
        log.exception("alpaca.order_test_failed")
        print("✗ Order submission failed")


async def test_binance() -> None:
    """Test Binance connection."""
    print("=" * 80)
    print("TESTING BINANCE CONNECTION")
    print("=" * 80)
    print()

    try:
        # Load config
        config = BinanceConfig.from_env()
        print(f"✓ Loaded config (testnet={config.testnet})")

        # Initialize adapter
        adapter = BinanceAdapter(
            api_key=config.api_key,
            api_secret=config.api_secret,
            testnet=config.testnet,
        )
        print("✓ Initialized adapter")

        # Get account info
        account = await adapter.get_account()
        print()
        print("Account Information:")
        print(f"  Can Trade: {account['can_trade']}")
        print(f"  Can Withdraw: {account['can_withdraw']}")
        print(f"  Can Deposit: {account['can_deposit']}")
        print()

        # Get positions (balances)
        positions = await adapter.get_positions()
        print(f"Balances: {len(positions)}")
        for symbol, qty in list(positions.items())[:10]:  # First 10
            print(f"  {symbol}: {qty}")
        print()

        # Get open orders
        open_orders = await adapter.get_open_orders()
        print(f"Open Orders: {len(open_orders)}")
        for order in open_orders:
            print(f"  {order.symbol} {order.side.value} {order.quantity}")
        print()

        print("✓ Binance connection successful!")
        print()

    except Exception:
        log.exception("binance.test_failed")
        print("✗ Binance connection failed")


async def main() -> None:
    """Test all brokers."""
    print()
    print("BROKER CONNECTION TESTS")
    print("=" * 80)
    print()
    print("This will test your broker connections.")
    print("Make sure you have:")
    print("  1. Created a .env file from .env.example")
    print("  2. Filled in your API keys")
    print("  3. Enabled paper/testnet trading")
    print()
    print("=" * 80)
    print()

    # Load trading config
    try:
        trading_config = TradingConfig.from_env()
        print("Trading Configuration:")
        print(f"  Mode: {trading_config.trading_mode}")
        print(f"  Starting Capital: ${trading_config.starting_capital:,.2f}")
        print(f"  Target: ${trading_config.target_wealth:,.2f}")
        print(f"  Dry Run: {trading_config.dry_run}")
        print()
    except Exception as e:
        print(f"✗ Failed to load trading config: {e}")
        print("  Create .env from .env.example and configure it")
        return

    # Test Alpaca
    print()
    response = input("Test Alpaca connection? (yes/no): ").lower()
    if response == "yes":
        await test_alpaca()

    # Test Binance
    print()
    response = input("Test Binance connection? (yes/no): ").lower()
    if response == "yes":
        await test_binance()

    print()
    print("=" * 80)
    print("TESTS COMPLETE")
    print("=" * 80)
    print()
    print("If all tests passed, you're ready for paper trading!")
    print("Next step: Run examples/live_trading_example.py")
    print()


if __name__ == "__main__":
    # Configure logging
    import structlog

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
    )

    asyncio.run(main())
