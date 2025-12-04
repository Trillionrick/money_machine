"""Example: Using 1inch Portfolio API v5.0 to track wallet positions.

This example demonstrates:
1. Fetching current portfolio snapshot
2. Getting historical metrics (PnL, ROI)
3. Analyzing token and protocol performance
4. Using the portfolio tracker service
"""

import asyncio
import os
from decimal import Decimal

import structlog

from src.portfolio import (
    OneInchPortfolioClient,
    PortfolioTracker,
    WalletConfig,
    TimeRange,
)

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)

log = structlog.get_logger()


async def example_direct_client():
    """Example 1: Direct API client usage."""
    print("\n" + "=" * 70)
    print("Example 1: Direct Portfolio API Client")
    print("=" * 70 + "\n")

    api_key = os.getenv("ONEINCH_API_KEY")
    if not api_key:
        print("❌ ONEINCH_API_KEY not set in environment")
        return

    wallet_address = os.getenv("PORTFOLIO_WALLETS", "").split(",")[0].strip()
    if not wallet_address:
        print("❌ PORTFOLIO_WALLETS not set in environment")
        return

    # Initialize client
    client = OneInchPortfolioClient(
        api_key=api_key,
        timeout=15.0,
        max_retries=3,
    )

    try:
        # Check if portfolio is available
        print(f"🔍 Checking portfolio status for {wallet_address[:10]}...")
        status = await client.get_status(wallet_address)
        print(f"   Status: {status.value}\n")

        # Get current snapshot
        print("📸 Fetching current portfolio snapshot...")
        snapshot = await client.get_full_snapshot(wallet_address)

        print(f"   Total Value: ${snapshot.total_value_usd:,.2f}")
        print(f"   Chains: {len(snapshot.chains)}")
        print(f"   Timestamp: {snapshot.timestamp}\n")

        # Show chain breakdown
        for chain_id, chain_data in snapshot.chains.items():
            print(f"   Chain {chain_id}:")
            print(f"     Value: ${chain_data.total_value_usd:,.2f}")
            print(f"     Tokens: {len(chain_data.tokens)}")
            print(f"     Protocols: {len(chain_data.protocols)}")

        # Get metrics for different time ranges
        print("\n📊 Fetching historical metrics...")

        for time_range in [TimeRange.ONE_DAY, TimeRange.ONE_WEEK, TimeRange.ONE_MONTH]:
            metrics = await client.get_full_metrics(wallet_address, time_range)

            print(f"\n   {time_range.value} Metrics:")
            print(f"     Total Profit: ${metrics.total_profit_usd:,.2f}")
            print(f"     ROI: {metrics.total_roi_percentage:.2f}%")

            # Show top performing protocols
            if metrics.protocols:
                top_protocol = max(metrics.protocols, key=lambda p: p.absolute_profit_usd)
                print(f"     Top Protocol: {top_protocol.protocol_name}")
                print(f"       Profit: ${top_protocol.absolute_profit_usd:,.2f}")
                if top_protocol.apr_percentage:
                    print(f"       APR: {top_protocol.apr_percentage:.2f}%")

            # Show top performing tokens
            if metrics.tokens:
                top_token = max(metrics.tokens, key=lambda t: t.absolute_profit_usd)
                print(f"     Top Token: {top_token.symbol}")
                print(f"       Profit: ${top_token.absolute_profit_usd:,.2f}")
                print(f"       ROI: {top_token.roi_percentage:.2f}%")

        # Get value chart for visualization
        print("\n📈 Fetching value chart data...")
        chart_data = await client.get_value_chart(
            wallet_address,
            time_range=TimeRange.ONE_MONTH,
        )
        print(f"   Chart data points: {len(chart_data)}")

    except Exception as e:
        log.exception("example_failed", error=str(e))

    finally:
        await client.close()


async def example_tracker_service():
    """Example 2: Portfolio tracker service with auto-updates."""
    print("\n" + "=" * 70)
    print("Example 2: Portfolio Tracker Service")
    print("=" * 70 + "\n")

    api_key = os.getenv("ONEINCH_API_KEY")
    if not api_key:
        print("❌ ONEINCH_API_KEY not set in environment")
        return

    # Parse wallet configuration
    wallet_addresses = [
        addr.strip()
        for addr in os.getenv("PORTFOLIO_WALLETS", "").split(",")
        if addr.strip()
    ]

    if not wallet_addresses:
        print("❌ PORTFOLIO_WALLETS not set in environment")
        return

    wallet_names_str = os.getenv("PORTFOLIO_WALLET_NAMES", "")
    wallet_names = [
        name.strip() for name in wallet_names_str.split(",") if name.strip()
    ]

    # Create wallet configs
    wallets = []
    for i, address in enumerate(wallet_addresses):
        name = wallet_names[i] if i < len(wallet_names) else f"Wallet {i + 1}"
        wallets.append(
            WalletConfig(
                address=address,
                name=name,
                enabled=True,
            )
        )

    # Initialize tracker
    tracker = PortfolioTracker(
        api_key=api_key,
        wallets=wallets,
        snapshot_interval=30.0,  # Update every 30 seconds for demo
        metrics_interval=60.0,  # Update metrics every 60 seconds
        enabled=True,
    )

    print(f"🚀 Starting portfolio tracker for {len(wallets)} wallet(s)...")
    print(f"   Snapshot interval: 30s")
    print(f"   Metrics interval: 60s\n")

    # Start tracker in background
    tracker_task = asyncio.create_task(tracker.start())

    try:
        # Monitor for 2 minutes
        for i in range(12):  # 12 * 10 seconds = 2 minutes
            await asyncio.sleep(10)

            print(f"\n⏱️  Update {i + 1}/12")

            # Get total portfolio value
            total_value = tracker.get_total_portfolio_value()
            print(f"   Total Portfolio Value: ${total_value:,.2f}\n")

            # Get individual wallet snapshots
            all_snapshots = tracker.get_all_snapshots()
            for address, snapshot in all_snapshots.items():
                wallet_name = next(
                    (w.name for w in wallets if w.address == address), "Unknown"
                )
                print(f"   {wallet_name} ({address[:10]}...):")
                print(f"     Value: ${snapshot.total_value_usd:,.2f}")
                print(f"     Chains: {len(snapshot.chains)}")

            # Get metrics for first wallet
            if wallets:
                metrics = tracker.get_cached_metrics(
                    wallets[0].address, TimeRange.ONE_MONTH
                )
                if metrics:
                    print(f"\n   30-day Performance ({wallets[0].name}):")
                    print(f"     Profit: ${metrics.total_profit_usd:,.2f}")
                    print(f"     ROI: {metrics.total_roi_percentage:.2f}%")

            # Show health status
            health = tracker.get_health_status()
            print(f"\n   Health Status:")
            print(f"     Active Wallets: {health['active_wallet_count']}")
            for wallet_status in health["wallets"]:
                if wallet_status["enabled"]:
                    snapshot_age = wallet_status.get("last_snapshot_age_seconds")
                    metrics_age = wallet_status.get("last_metrics_age_seconds")
                    print(f"     {wallet_status['name']}:")
                    print(f"       Updates: {wallet_status['update_count']}")
                    print(f"       Errors: {wallet_status['error_count']}")
                    if snapshot_age is not None:
                        print(f"       Last Snapshot: {snapshot_age:.0f}s ago")
                    if metrics_age is not None:
                        print(f"       Last Metrics: {metrics_age:.0f}s ago")

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    finally:
        print("\n🛑 Stopping tracker...")
        await tracker.stop()
        tracker_task.cancel()
        try:
            await tracker_task
        except asyncio.CancelledError:
            pass

        print("✅ Tracker stopped cleanly\n")


async def example_compare_wallets():
    """Example 3: Compare performance across multiple wallets."""
    print("\n" + "=" * 70)
    print("Example 3: Multi-Wallet Comparison")
    print("=" * 70 + "\n")

    api_key = os.getenv("ONEINCH_API_KEY")
    if not api_key:
        print("❌ ONEINCH_API_KEY not set in environment")
        return

    wallet_addresses = [
        addr.strip()
        for addr in os.getenv("PORTFOLIO_WALLETS", "").split(",")
        if addr.strip()
    ]

    if len(wallet_addresses) < 2:
        print("❌ Need at least 2 wallets in PORTFOLIO_WALLETS for comparison")
        return

    client = OneInchPortfolioClient(api_key=api_key)

    try:
        print("📊 Comparing wallet performance...\n")

        results = []
        for address in wallet_addresses:
            print(f"   Analyzing {address[:10]}...")

            snapshot = await client.get_full_snapshot(address)
            metrics = await client.get_full_metrics(address, TimeRange.ONE_MONTH)

            results.append({
                "address": address,
                "value": snapshot.total_value_usd,
                "profit_30d": metrics.total_profit_usd,
                "roi_30d": metrics.total_roi_percentage,
            })

        # Sort by total value
        results.sort(key=lambda x: x["value"], reverse=True)

        print("\n🏆 Rankings by Total Value:")
        for i, result in enumerate(results, 1):
            print(f"\n   #{i} {result['address'][:10]}...")
            print(f"      Value: ${result['value']:,.2f}")
            print(f"      30d Profit: ${result['profit_30d']:,.2f}")
            print(f"      30d ROI: {result['roi_30d']:.2f}%")

        # Calculate totals
        total_value = sum(r["value"] for r in results)
        total_profit = sum(r["profit_30d"] for r in results)
        avg_roi = sum(r["roi_30d"] for r in results) / len(results)

        print(f"\n📈 Aggregate Stats:")
        print(f"   Total Value: ${total_value:,.2f}")
        print(f"   Total 30d Profit: ${total_profit:,.2f}")
        print(f"   Average 30d ROI: {avg_roi:.2f}%")

    finally:
        await client.close()


async def main():
    """Run all examples."""
    print("\n" + "=" * 70)
    print("1INCH PORTFOLIO API v5.0 - EXAMPLES")
    print("=" * 70)

    # Run examples
    await example_direct_client()
    await example_tracker_service()

    # Only run comparison if multiple wallets configured
    wallet_count = len([
        addr.strip()
        for addr in os.getenv("PORTFOLIO_WALLETS", "").split(",")
        if addr.strip()
    ])
    if wallet_count >= 2:
        await example_compare_wallets()

    print("\n" + "=" * 70)
    print("✅ All examples completed!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
