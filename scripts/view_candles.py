#!/usr/bin/env python3
"""
Candle Data Viewer
Shows latest candlestick data with charts
"""
import asyncio
import asyncpg
from datetime import datetime


def candlestick_chart(open_price, high, low, close, width=20):
    """Create a simple ASCII candlestick"""
    bullish = close > open_price
    body_char = '█' if bullish else '░'

    # Normalize to chart width
    price_range = high - low
    if price_range == 0:
        return "─" * width

    # Calculate positions
    high_pos = 0
    low_pos = width - 1
    open_pos = int((high - open_price) / price_range * width)
    close_pos = int((high - close) / price_range * width)

    # Build chart
    chart = [' '] * width

    # Draw wick
    for i in range(high_pos, low_pos + 1):
        chart[i] = '│'

    # Draw body
    body_start = min(open_pos, close_pos)
    body_end = max(open_pos, close_pos)
    for i in range(body_start, body_end + 1):
        chart[i] = body_char

    return ''.join(chart)


async def main():
    conn = await asyncpg.connect(
        host='localhost',
        port=5434,
        user='trading_user',
        password='trading_pass_change_in_production',
        database='trading_db'
    )

    print("\n📊 LATEST CANDLESTICK DATA\n")
    print("=" * 100)

    # Get latest candles for each instrument
    rows = await conn.fetch("""
        SELECT
            instrument,
            granularity,
            time,
            open,
            high,
            low,
            close,
            volume,
            CASE WHEN close > open THEN 'Bullish' ELSE 'Bearish' END as direction
        FROM oanda_candles
        WHERE time = (
            SELECT MAX(time)
            FROM oanda_candles c2
            WHERE c2.instrument = oanda_candles.instrument
            AND c2.granularity = oanda_candles.granularity
        )
        ORDER BY instrument, granularity;
    """)

    current_instrument = None
    for row in rows:
        if current_instrument != row['instrument']:
            if current_instrument is not None:
                print()
            current_instrument = row['instrument']
            print(f"\n{row['instrument']} - Latest Candles:")
            print("-" * 100)

        # Color based on direction
        color = '\033[92m' if row['direction'] == 'Bullish' else '\033[91m'
        reset = '\033[0m'

        # Create candlestick chart
        chart = candlestick_chart(
            float(row['open']),
            float(row['high']),
            float(row['low']),
            float(row['close'])
        )

        print(f"{color}{row['granularity']:<4} {row['time'].strftime('%m-%d %H:%M'):<15} "
              f"O:{float(row['open']):<10.5f} H:{float(row['high']):<10.5f} "
              f"L:{float(row['low']):<10.5f} C:{float(row['close']):<10.5f} "
              f"V:{row['volume']:<8} {chart}{reset}")

    # Statistics
    stats = await conn.fetchrow("""
        SELECT
            COUNT(*) as total_candles,
            COUNT(DISTINCT instrument) as instruments,
            MIN(time) as earliest,
            MAX(time) as latest
        FROM oanda_candles
    """)

    print("\n" + "=" * 100)
    print(f"📈 Total Candles: {stats['total_candles']:,} | "
          f"Instruments: {stats['instruments']} | "
          f"Range: {stats['earliest'].strftime('%Y-%m-%d')} to {stats['latest'].strftime('%Y-%m-%d')}")
    print("=" * 100 + "\n")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
