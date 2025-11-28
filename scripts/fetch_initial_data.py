#!/usr/bin/env python3
"""Fetch initial historical data from OANDA and populate database.

This script:
1. Connects to OANDA API
2. Fetches historical candles for major forex pairs
3. Stores them in TimescaleDB
4. Fetches and stores instrument metadata
"""

import asyncio
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal

try:
    import asyncpg
except ImportError:
    print("❌ Error: asyncpg not installed")
    print("Install with: pip install asyncpg")
    sys.exit(1)


async def fetch_initial_forex_data():
    """Fetch initial historical data from OANDA."""

    print("🚀 Starting initial data fetch from OANDA...")
    print()

    # Import OANDA modules
    try:
        from src.brokers.oanda_config import OandaConfig
        from src.brokers.oanda_adapter import OandaAdapter
        from src.brokers.oanda_market_data import (
            OandaMarketData,
            CandleGranularity,
            PriceComponent,
        )
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure you're in the project root directory")
        return False

    # Load config
    try:
        config = OandaConfig.from_env()
        print(f"✅ Loaded OANDA config")
        print(f"   Environment: {config.oanda_environment.value}")
        print(f"   Account: {config.oanda_account_id}")
        print()
    except Exception as e:
        print(f"❌ Failed to load OANDA config: {e}")
        print("Make sure .env has OANDA_API_TOKEN and OANDA_ACCOUNT_ID")
        return False

    # Connect to database
    try:
        conn = await asyncpg.connect(
            host="localhost",
            port=5433,
            user="trading_user",
            password="trading_pass_change_in_production",
            database="trading_db",
        )
        print("✅ Connected to TimescaleDB")
        print()
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

    try:
        async with OandaAdapter(config) as adapter:
            print("✅ Connected to OANDA API")
            print()

            # Fetch and store instrument metadata
            print("📥 Fetching instrument metadata...")
            instruments_data = await adapter.get_instruments()

            instruments_inserted = 0
            for inst in instruments_data:
                try:
                    await conn.execute(
                        """
                        INSERT INTO oanda_instruments
                        (instrument, display_name, type, pip_location,
                         display_precision, trade_units_precision, margin_rate,
                         minimum_trade_size, maximum_order_units, maximum_position_size)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        ON CONFLICT (instrument) DO UPDATE
                        SET display_name = EXCLUDED.display_name,
                            type = EXCLUDED.type,
                            updated_at = NOW()
                        """,
                        inst.get("name"),
                        inst.get("displayName", inst.get("name")),
                        inst.get("type", "CURRENCY"),
                        inst.get("pipLocation", -4),
                        inst.get("displayPrecision", 5),
                        inst.get("tradeUnitsPrecision", 0),
                        Decimal(str(inst.get("marginRate", "0.03"))),
                        Decimal(str(inst.get("minimumTradeSize", "1"))),
                        Decimal(str(inst.get("maximumOrderUnits", "100000000"))),
                        Decimal(str(inst.get("maximumPositionSize", "100000000"))),
                    )
                    instruments_inserted += 1
                except Exception as e:
                    print(f"   ⚠️  Failed to insert {inst.get('name')}: {e}")

            print(f"✅ Stored {instruments_inserted} instruments")
            print()

            # Fetch historical candles for major pairs
            market_data = OandaMarketData(config, adapter.client)

            major_pairs = [
                "EUR_USD",
                "GBP_USD",
                "USD_JPY",
                "AUD_USD",
                "USD_CAD",
                "USD_CHF",
                "NZD_USD",
                "EUR_GBP",
            ]

            print("📊 Fetching historical candles...")
            print(f"   Pairs: {', '.join(major_pairs)}")
            print(f"   Period: Last 30 days")
            print(f"   Granularity: 1 hour")
            print()

            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=30)

            total_candles = 0

            for instrument in major_pairs:
                print(f"   📈 {instrument}...", end=" ", flush=True)

                try:
                    # Fetch candles
                    candles = await market_data.get_candles_paginated(
                        instrument=instrument,
                        granularity=CandleGranularity.H1,
                        from_time=start_time,
                        to_time=end_time,
                        price=PriceComponent.MBA,  # Mid, Bid, Ask
                    )

                    # Insert into database
                    candles_inserted = 0
                    for candle in candles:
                        if not candle.get("complete"):
                            continue

                        mid = candle.get("mid", {})
                        bid = candle.get("bid", {})
                        ask = candle.get("ask", {})

                        # Calculate spread
                        spread_avg = None
                        if bid and ask:
                            bid_close = Decimal(bid.get("c", "0"))
                            ask_close = Decimal(ask.get("c", "0"))
                            spread_avg = ask_close - bid_close

                        try:
                            await conn.execute(
                                """
                                INSERT INTO oanda_candles
                                (time, instrument, granularity, open, high, low, close, volume,
                                 bid_open, bid_high, bid_low, bid_close,
                                 ask_open, ask_high, ask_low, ask_close,
                                 spread_avg, complete)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                                        $13, $14, $15, $16, $17, $18)
                                ON CONFLICT (time, instrument, granularity) DO NOTHING
                                """,
                                candle["time"],
                                instrument,
                                "H1",
                                Decimal(mid["o"]),
                                Decimal(mid["h"]),
                                Decimal(mid["l"]),
                                Decimal(mid["c"]),
                                int(candle.get("volume", 0)),
                                Decimal(bid["o"]) if bid else None,
                                Decimal(bid["h"]) if bid else None,
                                Decimal(bid["l"]) if bid else None,
                                Decimal(bid["c"]) if bid else None,
                                Decimal(ask["o"]) if ask else None,
                                Decimal(ask["h"]) if ask else None,
                                Decimal(ask["l"]) if ask else None,
                                Decimal(ask["c"]) if ask else None,
                                spread_avg,
                                True,
                            )
                            candles_inserted += 1
                        except Exception as e:
                            print(f"\n   ⚠️  Failed to insert candle: {e}")

                    print(f"{candles_inserted} candles")
                    total_candles += candles_inserted

                    # Small delay to avoid rate limits
                    await asyncio.sleep(0.5)

                except Exception as e:
                    print(f"FAILED - {e}")

            print()
            print(f"✅ Total candles stored: {total_candles}")
            print()

            # Summary
            print("=" * 60)
            print("✨ Initial data fetch complete!")
            print("=" * 60)
            print()
            print("Database statistics:")

            # Count records
            candle_count = await conn.fetchval("SELECT COUNT(*) FROM oanda_candles")
            instrument_count = await conn.fetchval("SELECT COUNT(*) FROM oanda_instruments")

            print(f"   📊 Candles: {candle_count:,}")
            print(f"   🌍 Instruments: {instrument_count}")
            print()

            # Show latest candle for EUR/USD
            latest = await conn.fetchrow(
                """
                SELECT time, open, high, low, close, volume, spread_avg
                FROM oanda_candles
                WHERE instrument = 'EUR_USD' AND granularity = 'H1'
                ORDER BY time DESC
                LIMIT 1
                """
            )

            if latest:
                print(f"Latest EUR/USD candle:")
                print(f"   Time: {latest['time']}")
                print(f"   OHLC: {latest['open']}/{latest['high']}/{latest['low']}/{latest['close']}")
                print(f"   Volume: {latest['volume']}")
                if latest['spread_avg']:
                    print(f"   Spread: {latest['spread_avg']:.5f}")
            print()

            print("Next steps:")
            print("1. Query data: psql -h localhost -p 5433 -U trading_user -d trading_db")
            print("2. Start streaming: python examples/stream_forex_prices.py")
            print("3. Run strategies on forex data")
            print()

            return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await conn.close()


if __name__ == "__main__":
    success = asyncio.run(fetch_initial_forex_data())
    sys.exit(0 if success else 1)
