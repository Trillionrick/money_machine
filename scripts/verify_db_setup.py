#!/usr/bin/env python3
"""Verify TimescaleDB setup and OANDA schema initialization.

This script:
1. Connects to TimescaleDB
2. Verifies all tables exist
3. Checks hypertable configuration
4. Validates compression policies
5. Tests basic insert/query operations
"""

import asyncio
import sys
from datetime import datetime, timezone
from decimal import Decimal

try:
    import asyncpg
except ImportError:
    print("❌ Error: asyncpg not installed")
    print("Install with: pip install asyncpg")
    sys.exit(1)


async def verify_database_setup():
    """Verify TimescaleDB setup and OANDA schema."""

    # Connection settings
    config = {
        "host": "localhost",
        "port": 5433,
        "user": "trading_user",
        "password": "trading_pass_change_in_production",
        "database": "trading_db",
    }

    print("🔌 Connecting to TimescaleDB...")
    print(f"   Host: {config['host']}:{config['port']}")
    print(f"   Database: {config['database']}")
    print()

    try:
        conn = await asyncpg.connect(**config)
        print("✅ Connected successfully!")
        print()
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print()
        print("Make sure TimescaleDB is running:")
        print("   docker-compose up -d timescaledb")
        return False

    try:
        # Check TimescaleDB extension
        print("🔍 Checking TimescaleDB extension...")
        result = await conn.fetchval(
            "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'"
        )
        if result:
            print(f"✅ TimescaleDB version: {result}")
        else:
            print("❌ TimescaleDB extension not installed")
            return False
        print()

        # Check tables
        print("📋 Checking tables...")
        tables = [
            "oanda_candles",
            "oanda_transactions",
            "oanda_positions",
            "oanda_pricing",
            "oanda_instruments",
        ]

        for table in tables:
            count = await conn.fetchval(
                f"SELECT COUNT(*) FROM information_schema.tables "
                f"WHERE table_name = $1",
                table,
            )
            if count > 0:
                print(f"   ✅ {table}")
            else:
                print(f"   ❌ {table} - NOT FOUND")
        print()

        # Check hypertables
        print("⏱️  Checking hypertables...")
        hypertables = await conn.fetch(
            """
            SELECT hypertable_name, num_chunks
            FROM timescaledb_information.hypertables
            WHERE hypertable_schema = 'public'
            """
        )

        if hypertables:
            for ht in hypertables:
                print(f"   ✅ {ht['hypertable_name']} ({ht['num_chunks']} chunks)")
        else:
            print("   ⚠️  No hypertables found")
        print()

        # Check compression policies
        print("🗜️  Checking compression policies...")
        policies = await conn.fetch(
            """
            SELECT hypertable_name, older_than
            FROM timescaledb_information.jobs j
            JOIN timescaledb_information.hypertables h ON j.hypertable_name = h.hypertable_name
            WHERE proc_name = 'policy_compression'
            """
        )

        if policies:
            for policy in policies:
                print(f"   ✅ {policy['hypertable_name']} - compress after {policy['older_than']}")
        else:
            print("   ⚠️  No compression policies found")
        print()

        # Check continuous aggregates
        print("📊 Checking continuous aggregates...")
        caggs = await conn.fetch(
            """
            SELECT view_name, materialization_hypertable_name
            FROM timescaledb_information.continuous_aggregates
            """
        )

        if caggs:
            for cagg in caggs:
                print(f"   ✅ {cagg['view_name']}")
        else:
            print("   ⚠️  No continuous aggregates found")
        print()

        # Check instruments
        print("🌍 Checking pre-loaded instruments...")
        instrument_count = await conn.fetchval(
            "SELECT COUNT(*) FROM oanda_instruments"
        )
        print(f"   ✅ {instrument_count} instruments loaded")

        if instrument_count > 0:
            instruments = await conn.fetch(
                "SELECT instrument, display_name, type FROM oanda_instruments LIMIT 5"
            )
            for inst in instruments:
                print(f"      • {inst['instrument']} ({inst['display_name']}) - {inst['type']}")
        print()

        # Test insert/query
        print("🧪 Testing insert/query operations...")

        # Insert test candle
        test_time = datetime.now(timezone.utc)
        await conn.execute(
            """
            INSERT INTO oanda_candles
            (time, instrument, granularity, open, high, low, close, volume, complete)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (time, instrument, granularity) DO NOTHING
            """,
            test_time,
            "EUR_USD",
            "M1",
            Decimal("1.09500"),
            Decimal("1.09550"),
            Decimal("1.09480"),
            Decimal("1.09520"),
            1000,
            True,
        )
        print("   ✅ Insert test candle - SUCCESS")

        # Query test candle
        result = await conn.fetchrow(
            """
            SELECT * FROM oanda_candles
            WHERE instrument = 'EUR_USD' AND granularity = 'M1'
            ORDER BY time DESC
            LIMIT 1
            """
        )
        if result:
            print(f"   ✅ Query test candle - SUCCESS")
            print(f"      Time: {result['time']}")
            print(f"      OHLC: {result['open']}/{result['high']}/{result['low']}/{result['close']}")
        else:
            print("   ❌ Query test candle - FAILED")
        print()

        # Summary
        print("=" * 60)
        print("✨ Database setup verification complete!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Update .env with your OANDA credentials")
        print("2. Run: python scripts/fetch_initial_data.py")
        print("3. Start trading!")
        print()

        return True

    except Exception as e:
        print(f"❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await conn.close()


if __name__ == "__main__":
    success = asyncio.run(verify_database_setup())
    sys.exit(0 if success else 1)
