"""List available cryptocurrency assets on Alpaca.

Shows all tradable crypto with details:
- Symbol (e.g., BTC/USD)
- Name
- Minimum order size
- Fractionable support
"""

import asyncio

import structlog

from src.brokers.alpaca_adapter import AlpacaAdapter
from src.brokers.config import AlpacaConfig

log = structlog.get_logger()


async def list_crypto_assets() -> None:
    """List all available crypto assets."""
    print("=" * 80)
    print("AVAILABLE CRYPTO ASSETS")
    print("=" * 80)
    print()

    # Load config
    try:
        config = AlpacaConfig.from_env()
        print(f"✓ Loaded config (paper={config.paper})")
    except Exception as e:
        print(f"✗ Configuration error: {e}")
        return

    # Initialize adapter
    adapter = AlpacaAdapter(
        api_key=config.api_key,
        api_secret=config.api_secret,
        paper=config.paper,
    )
    print("✓ Connected to Alpaca")
    print()

    # Get all assets
    try:
        loop = asyncio.get_event_loop()
        assets = await loop.run_in_executor(
            None,
            lambda: adapter.client.get_all_assets(),
        )

        # Filter for crypto
        crypto_assets = [
            asset for asset in assets
            if asset.asset_class == "crypto" and asset.tradable
        ]

        print(f"Found {len(crypto_assets)} tradable cryptocurrencies:")
        print()

        # Group by popularity
        popular = ["BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "DOGE/USD"]
        stablecoins = ["USDC/USD", "USDT/USD"]

        print("POPULAR CRYPTOCURRENCIES:")
        print("-" * 80)
        for asset in crypto_assets:
            if asset.symbol in popular:
                print(f"  {asset.symbol:12} - {asset.name:20} (fractionable)")

        print()
        print("STABLECOINS:")
        print("-" * 80)
        for asset in crypto_assets:
            if asset.symbol in stablecoins:
                print(f"  {asset.symbol:12} - {asset.name:20} (fractionable)")

        print()
        print("ALL CRYPTO ASSETS:")
        print("-" * 80)
        for asset in sorted(crypto_assets, key=lambda x: x.symbol):
            frac = "✓" if asset.fractionable else "✗"
            print(f"  {asset.symbol:15} - {asset.name:25} [fractionable: {frac}]")

        print()
        print(f"Total: {len(crypto_assets)} assets")
        print()

        # Show trading details
        print("TRADING DETAILS:")
        print("-" * 80)
        print("  Minimum Order: $1 (USD pairs) or 0.000000002 (BTC/ETH/USDT pairs)")
        print("  Maximum Order: $200,000 per order")
        print("  Precision: Up to 9 decimal places")
        print("  Margin: Not available (cash only)")
        print("  Shorting: Not available")
        print("  Trading Hours: 24/7/365")
        print("  Time in Force: GTC, IOC (not DAY)")
        print()

    except Exception:
        log.exception("list_crypto.error")
        print("✗ Failed to list crypto assets")


if __name__ == "__main__":
    # Configure logging
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
    )

    asyncio.run(list_crypto_assets())
