#!/usr/bin/env python3
"""
Quick test for live blockchain monitor functionality.
"""

import asyncio
from src.nft.live_blockchain_monitor import create_monitor


async def test_monitor():
    """Test blockchain monitor with your wallet addresses."""
    print("🔍 Testing Live Blockchain Monitor\n")
    print("=" * 60)

    # Your wallet addresses from .env
    wallets = [
        "0x31fcd43a349ada21f3c5df51d66f399be518a912",  # Metamask
        "0x21E722833CE4C3e8CE68F14D159456744402b48C",  # Rainbow
    ]

    event_count = 0

    async def handle_event(event):
        """Print events as they arrive."""
        nonlocal event_count
        event_count += 1

        emoji = {
            'new_block': '⛓️',
            'nft_transfer': '🖼️',
            'swap': '💱',
            'token_transfer': '💸'
        }.get(event.event_type, '📡')

        if event.event_type != 'new_block':
            print(f"{emoji} {event.summary}")
            print(f"   {event.chain} | Block {event.block_number:,}")
            if event.tx_hash:
                print(f"   TX: {event.tx_hash[:16]}...")
            print()

    # Create Ethereum monitor
    print("Starting Ethereum monitor...")
    eth_monitor = await create_monitor(
        chain="ethereum",
        rpc_url="https://eth-mainnet.g.alchemy.com/v2/vZuXI4mrngK8K5m-FyIQ0",
        wallets=wallets,
        on_event=handle_event,
    )

    print("✓ Monitor started")
    print(f"✓ Watching {len(wallets)} wallets")
    print(f"✓ Monitoring popular NFT contracts and DEX pools")
    print("\nLive activity will appear below (Ctrl+C to stop):\n")
    print("-" * 60)

    try:
        # Run for 30 seconds as a test
        await asyncio.wait_for(eth_monitor.run(), timeout=30.0)
    except asyncio.TimeoutError:
        await eth_monitor.stop()
        print("\n" + "=" * 60)
        print(f"✓ Test complete: {event_count} events detected in 30 seconds")


if __name__ == "__main__":
    asyncio.run(test_monitor())
