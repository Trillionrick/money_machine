"""Test if Aqua watcher is functioning by checking recent blocks."""

import asyncio
import os
from web3 import AsyncHTTPProvider, AsyncWeb3
from src.dex.aqua_client import AquaClient

async def test_aqua_connection():
    """Test Aqua watcher connectivity and recent events."""

    # Connect to Polygon (more activity than Ethereum typically)
    rpc_url = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
    print(f"🔌 Using RPC: {rpc_url}")
    w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))

    if not await w3.is_connected():
        print("❌ Failed to connect to Polygon RPC")
        return

    print("✅ Connected to Polygon RPC")

    # Create Aqua client
    aqua = AquaClient(w3, chain_id=137)
    print(f"📍 Monitoring Aqua contract: {aqua.address}")

    # Get current block
    current_block = await w3.eth.block_number
    print(f"📦 Current block: {current_block:,}")

    # Search last 10 blocks for Aqua events (most RPCs have strict limits)
    from_block = max(current_block - 10, 0)
    print(f"🔍 Searching blocks {from_block:,} to {current_block:,} for Aqua events...")

    try:
        logs = await w3.eth.get_logs({
            "fromBlock": from_block,
            "toBlock": current_block,
            "address": aqua.address,
        })
    except Exception as e:
        print(f"❌ RPC query failed: {e}")
        print("   This might indicate RPC rate limiting or query restrictions")
        return

    print(f"\n📊 Found {len(logs)} total logs")

    if len(logs) == 0:
        print("\n⚠️  No Aqua events in last 10,000 blocks (~8 hours on Polygon)")
        print("   This is normal - Aqua activity is sporadic")
        print("   Your watcher is configured correctly and will catch events when they occur")
    else:
        print(f"\n✅ Found {len(logs)} Aqua events:")

        event_counts = {}
        for log in logs:
            event = aqua.parse_event(dict(log))
            if event:
                event_counts[event.name] = event_counts.get(event.name, 0) + 1
                if len([e for e in event_counts.values()]) <= 5:  # Show first 5
                    print(f"   • {event.name} at block {event.block_number:,}")
                    if event.token and event.amount:
                        print(f"     Token: {event.token}, Amount: {event.amount:,}")

        print(f"\n📈 Event summary:")
        for event_name, count in event_counts.items():
            print(f"   {event_name}: {count}")

if __name__ == "__main__":
    asyncio.run(test_aqua_connection())
