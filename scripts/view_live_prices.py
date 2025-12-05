#!/usr/bin/env python3
"""Live Forex Price Monitor - Shows real-time prices from database."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

import asyncpg
import structlog

# Ensure project root on sys.path for src imports when running as script
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.db_config import DatabaseSettings

log = structlog.get_logger()


async def main() -> None:
    """Monitor live forex prices from database."""
    db_config = DatabaseSettings().asyncpg_kwargs()

    try:
        conn = await asyncpg.connect(**db_config)
        log.info("database.connected", **db_config)
    except Exception as e:
        log.error("database.connection_failed", error=str(e))
        sys.exit(1)

    print("🔴 LIVE FOREX PRICES (Press Ctrl+C to exit)\n")
    print("=" * 80)

    try:
        while True:
            # Clear screen (works on Linux/Mac/Windows)
            os.system('clear' if os.name != 'nt' else 'cls')

            print(f"🔴 LIVE FOREX PRICES - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            print("=" * 80)

            # Get latest price for each instrument
            rows = await conn.fetch("""
                SELECT DISTINCT ON (instrument)
                    instrument,
                    time,
                    bid,
                    ask,
                    spread
                FROM oanda_pricing
                ORDER BY instrument, time DESC
            """)

            if rows:
                print(f"{'Instrument':<12} {'Time':<12} {'Bid':<12} {'Ask':<12} {'Spread':<10}")
                print("-" * 80)

                for row in rows:
                    age = (datetime.now(timezone.utc) - row['time']).total_seconds()
                    age_str = f"{age:.1f}s ago" if age < 60 else f"{age/60:.1f}m ago"

                    # Color code based on age (green if fresh, yellow if old)
                    color = '\033[92m' if age < 10 else '\033[93m' if age < 60 else '\033[91m'
                    reset = '\033[0m'

                    print(f"{color}{row['instrument']:<12} {age_str:<12} "
                          f"{float(row['bid']):<12.5f} {float(row['ask']):<12.5f} "
                          f"{float(row['spread']):<10.5f}{reset}")
            else:
                print("No data yet... waiting for prices to arrive...")

            # Get statistics
            stats = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_ticks,
                    COUNT(DISTINCT instrument) as instruments,
                    MAX(time) as latest_update
                FROM oanda_pricing
            """)

            print("\n" + "=" * 80)
            print(f"📊 Total Ticks: {stats['total_ticks']:,} | "
                  f"Instruments: {stats['instruments']} | "
                  f"Latest: {stats['latest_update'].strftime('%H:%M:%S') if stats['latest_update'] else 'N/A'}")
            print("=" * 80)

            # Update every 2 seconds
            await asyncio.sleep(2)

    except KeyboardInterrupt:
        print("\n\n✅ Stopped monitoring")
        log.info("monitor.stopped")
    except Exception as e:
        log.error("monitor.error", error=str(e))
        raise
    finally:
        await conn.close()
        log.info("database.disconnected")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        log.error("monitor.failed", error=str(e))
        sys.exit(1)
