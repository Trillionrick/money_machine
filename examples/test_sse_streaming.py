"""Test real-time SSE streaming from Alpaca.

This demonstrates the low-latency event streaming capabilities:
- Real-time trade fills (vs 1-second polling)
- Account status updates
- Non-trade activities (dividends, splits)

Run this to verify SSE is working before live trading.
"""

import asyncio
from datetime import datetime

import structlog

from src.brokers.alpaca_sse import AlpacaSSEClient
from src.brokers.config import AlpacaConfig

log = structlog.get_logger()


async def test_trade_events(client: AlpacaSSEClient, duration_seconds: int = 30) -> None:
    """Monitor trade events for a short duration.

    Args:
        client: SSE client
        duration_seconds: How long to monitor
    """
    print("\n" + "=" * 80)
    print("TESTING TRADE EVENT STREAM")
    print("=" * 80)
    print()
    print(f"Monitoring for {duration_seconds} seconds...")
    print("Submit a test order in another terminal to see events")
    print()

    event_count = 0
    start_time = asyncio.get_event_loop().time()

    try:
        async for event in client.stream_trade_events():
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > duration_seconds:
                break

            event_count += 1
            event_type = event.get("event")
            order = event.get("order", {})
            symbol = order.get("symbol", "unknown")
            side = order.get("side", "")
            qty = order.get("qty", "")
            status = order.get("status", "")

            # Format timestamp
            at = event.get("at", "")
            try:
                dt = datetime.fromisoformat(at.replace("Z", "+00:00"))
                timestamp = dt.strftime("%H:%M:%S.%f")[:-3]
            except Exception:
                timestamp = at

            print(f"[{timestamp}] {event_type.upper()}: {symbol} {side} {qty} - {status}")

            # Show fill details if it's a fill
            if event_type == "fill":
                fill_price = event.get("price")
                fill_qty = event.get("qty")
                position_qty = event.get("position_qty")
                print(f"           Fill: {fill_qty} @ ${fill_price}, Position: {position_qty}")

            print()

    except KeyboardInterrupt:
        print("\nStopped by user")

    print(f"Received {event_count} events in {duration_seconds} seconds")
    print()


async def test_account_status(client: AlpacaSSEClient, duration_seconds: int = 10) -> None:
    """Monitor account status changes.

    Args:
        client: SSE client
        duration_seconds: How long to monitor
    """
    print("\n" + "=" * 80)
    print("TESTING ACCOUNT STATUS STREAM")
    print("=" * 80)
    print()
    print(f"Monitoring for {duration_seconds} seconds...")
    print()

    event_count = 0
    start_time = asyncio.get_event_loop().time()

    try:
        async for event in client.stream_account_status():
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > duration_seconds:
                break

            event_count += 1
            account_id = event.get("account_id", "")
            status_from = event.get("status_from", "")
            status_to = event.get("status_to", "")
            at = event.get("at", "")

            print(f"[{at}] Account {account_id[:8]}... : {status_from} → {status_to}")

    except KeyboardInterrupt:
        print("\nStopped by user")

    if event_count == 0:
        print("No account status changes (this is normal)")
    else:
        print(f"Received {event_count} status changes")
    print()


async def test_nta_events(client: AlpacaSSEClient, duration_seconds: int = 10) -> None:
    """Monitor non-trade activity events.

    Args:
        client: SSE client
        duration_seconds: How long to monitor
    """
    print("\n" + "=" * 80)
    print("TESTING NON-TRADE ACTIVITY STREAM")
    print("=" * 80)
    print()
    print(f"Monitoring for {duration_seconds} seconds...")
    print()

    event_count = 0
    start_time = asyncio.get_event_loop().time()

    try:
        async for event in client.stream_nta_events():
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > duration_seconds:
                break

            event_count += 1
            entry_type = event.get("entry_type", "")
            symbol = event.get("symbol", "")
            description = event.get("description", "")
            net_amount = event.get("net_amount", 0)

            print(f"{entry_type}: {symbol}")
            print(f"  {description}")
            print(f"  Amount: ${net_amount:.2f}")
            print()

    except KeyboardInterrupt:
        print("\nStopped by user")

    if event_count == 0:
        print("No non-trade activities (this is normal for new accounts)")
    else:
        print(f"Received {event_count} events")
    print()


async def main() -> None:
    """Run SSE streaming tests."""
    print()
    print("ALPACA SSE STREAMING TEST")
    print("=" * 80)
    print()
    print("This will test real-time event streaming from Alpaca.")
    print("You should see events as they happen (no polling delay).")
    print()

    # Load config
    try:
        config = AlpacaConfig.from_env()
        print(f"✓ Loaded config (paper={config.paper})")
    except Exception as e:
        print(f"✗ Configuration error: {e}")
        print("  Create .env file from .env.example")
        return

    # Create SSE client
    client = AlpacaSSEClient(
        api_key=config.api_key,
        api_secret=config.api_secret,
        paper=config.paper,
    )
    print("✓ SSE client initialized")
    print()

    # Test trade events
    await test_trade_events(client, duration_seconds=30)

    # Test account status (brief)
    await test_account_status(client, duration_seconds=10)

    # Test NTA events (brief)
    await test_nta_events(client, duration_seconds=10)

    print("=" * 80)
    print("SSE STREAMING TESTS COMPLETE")
    print("=" * 80)
    print()
    print("If you saw trade events appear instantly after submitting orders,")
    print("SSE is working correctly! This is much faster than polling.")
    print()


if __name__ == "__main__":
    # Configure logging
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
    )

    asyncio.run(main())
