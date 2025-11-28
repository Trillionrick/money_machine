#!/usr/bin/env python3
"""Real-time forex price data collector for OANDA.

This script:
1. Streams real-time prices for major forex pairs
2. Stores tick data in TimescaleDB
3. Periodically fetches and stores candle data
4. Handles reconnections and errors gracefully
5. Provides monitoring metrics
"""

import asyncio
import signal
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any

import asyncpg
import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer(),
    ],
)

log = structlog.get_logger()


class ForexDataCollector:
    """Collects and stores forex price data from OANDA."""

    def __init__(self):
        """Initialize the collector."""
        self.running = False
        self.db_pool: asyncpg.Pool | None = None
        self.oanda_adapter = None
        self.streaming_client = None

        # Major forex pairs to collect
        self.instruments = [
            "EUR_USD",
            "GBP_USD",
            "USD_JPY",
            "AUD_USD",
            "USD_CAD",
            "USD_CHF",
            "NZD_USD",
            "EUR_GBP",
            "EUR_JPY",
            "GBP_JPY",
        ]

        # Statistics
        self.stats = {
            "prices_received": 0,
            "prices_stored": 0,
            "candles_stored": 0,
            "errors": 0,
            "last_price_time": None,
            "start_time": datetime.now(timezone.utc),
        }

    async def initialize(self):
        """Initialize database connection and OANDA adapter."""
        log.info("initializing_collector")

        # Import OANDA modules
        from src.brokers.oanda_config import OandaConfig
        from src.brokers.oanda_adapter import OandaAdapter
        from src.brokers.oanda_streaming import OandaStreamingClient

        # Load OANDA config
        try:
            config = OandaConfig.from_env()
            log.info(
                "oanda_config_loaded",
                environment=config.oanda_environment.value,
                account_id=config.oanda_account_id,
            )
        except Exception as e:
            log.error("failed_to_load_config", error=str(e))
            raise

        # Create database connection pool
        try:
            self.db_pool = await asyncpg.create_pool(
                host="localhost",
                port=5434,
                user="trading_user",
                password="trading_pass_change_in_production",
                database="trading_db",
                min_size=2,
                max_size=10,
            )
            log.info("database_pool_created")
        except Exception as e:
            log.error("database_connection_failed", error=str(e))
            raise

        # Initialize OANDA adapter
        try:
            self.oanda_adapter = OandaAdapter(config)
            account = await self.oanda_adapter.get_account()
            log.info(
                "oanda_connected",
                balance=str(account["balance"]),
                currency=account["currency"],
            )
        except Exception as e:
            log.error("oanda_connection_failed", error=str(e))
            raise

        # Initialize streaming client
        self.streaming_client = OandaStreamingClient(
            config=config,
            stream_client=self.oanda_adapter.stream_client,
        )

        log.info("initialization_complete")

    async def store_price_tick(
        self,
        instrument: str,
        time: str,
        bid: str,
        ask: str,
        bid_liquidity: int | None = None,
        ask_liquidity: int | None = None,
        tradeable: bool = True,
    ):
        """Store price tick in database.

        Args:
            instrument: Instrument name (e.g., "EUR_USD")
            time: ISO timestamp
            bid: Bid price
            ask: Ask price
            bid_liquidity: Bid liquidity (optional)
            ask_liquidity: Ask liquidity (optional)
            tradeable: Whether instrument is tradeable
        """
        try:
            # Parse timestamp (OANDA returns Unix timestamp as string)
            price_time = time
            if isinstance(price_time, str):
                # Convert Unix timestamp string to datetime
                timestamp = float(price_time)
                price_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)

            bid_decimal = Decimal(bid)
            ask_decimal = Decimal(ask)
            spread = ask_decimal - bid_decimal

            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO oanda_pricing
                    (time, instrument, bid, ask, spread, bid_liquidity, ask_liquidity, tradeable)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (time, instrument) DO NOTHING
                    """,
                    price_time,
                    instrument,
                    bid_decimal,
                    ask_decimal,
                    spread,
                    bid_liquidity,
                    ask_liquidity,
                    tradeable,
                )

            self.stats["prices_stored"] += 1

        except Exception as e:
            log.error("failed_to_store_price", instrument=instrument, error=str(e))
            self.stats["errors"] += 1

    async def stream_prices(self):
        """Stream real-time prices and store in database."""
        log.info("starting_price_stream", instruments=self.instruments)

        try:
            async for price_update in self.streaming_client.stream_prices(
                self.instruments
            ):
                if not self.running:
                    break

                msg_type = price_update.get("type")

                if msg_type == "HEARTBEAT":
                    log.debug("heartbeat_received")
                    continue

                if msg_type == "PRICE":
                    self.stats["prices_received"] += 1
                    self.stats["last_price_time"] = datetime.now(timezone.utc)

                    instrument = price_update.get("instrument", "")
                    time = price_update.get("time", "")
                    bids = price_update.get("bids", [])
                    asks = price_update.get("asks", [])
                    tradeable = price_update.get("tradeable", True)

                    if bids and asks:
                        bid_price = bids[0].get("price", "0")
                        ask_price = asks[0].get("price", "0")
                        bid_liquidity = bids[0].get("liquidity")
                        ask_liquidity = asks[0].get("liquidity")

                        # Store in database
                        await self.store_price_tick(
                            instrument=instrument,
                            time=time,
                            bid=bid_price,
                            ask=ask_price,
                            bid_liquidity=bid_liquidity,
                            ask_liquidity=ask_liquidity,
                            tradeable=tradeable,
                        )

                        # Log every 100 prices
                        if self.stats["prices_stored"] % 100 == 0:
                            log.info(
                                "price_batch_stored",
                                count=self.stats["prices_stored"],
                                instrument=instrument,
                                bid=bid_price,
                                ask=ask_price,
                            )

        except Exception as e:
            log.error("price_stream_error", error=str(e))
            self.stats["errors"] += 1
            # Will reconnect automatically via streaming client

    async def fetch_and_store_candles(
        self,
        instrument: str,
        granularity: str = "H1",
        count: int = 100,
    ):
        """Fetch and store historical candles.

        Args:
            instrument: Instrument name
            granularity: Candle granularity
            count: Number of candles to fetch
        """
        from src.brokers.oanda_market_data import (
            OandaMarketData,
            CandleGranularity,
            PriceComponent,
        )

        try:
            market_data = OandaMarketData(
                config=self.oanda_adapter.config,
                client=self.oanda_adapter.client,
            )

            # Fetch candles
            candles = await market_data.get_latest_candles(
                instrument=instrument,
                granularity=CandleGranularity(granularity),
                count=count,
                price=PriceComponent.MBA,
            )

            # Store in database
            stored = 0
            async with self.db_pool.acquire() as conn:
                for candle in candles:
                    if not candle.get("complete"):
                        continue

                    # Parse timestamp (OANDA returns Unix timestamp as string)
                    candle_time = candle["time"]
                    if isinstance(candle_time, str):
                        # Convert Unix timestamp string to datetime
                        timestamp = float(candle_time)
                        candle_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)

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
                            ON CONFLICT (time, instrument, granularity) DO UPDATE
                            SET open = EXCLUDED.open,
                                high = EXCLUDED.high,
                                low = EXCLUDED.low,
                                close = EXCLUDED.close,
                                volume = EXCLUDED.volume,
                                bid_open = EXCLUDED.bid_open,
                                bid_high = EXCLUDED.bid_high,
                                bid_low = EXCLUDED.bid_low,
                                bid_close = EXCLUDED.bid_close,
                                ask_open = EXCLUDED.ask_open,
                                ask_high = EXCLUDED.ask_high,
                                ask_low = EXCLUDED.ask_low,
                                ask_close = EXCLUDED.ask_close,
                                spread_avg = EXCLUDED.spread_avg,
                                complete = EXCLUDED.complete
                            """,
                            candle_time,
                            instrument,
                            granularity,
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
                        stored += 1
                    except Exception as e:
                        log.error("failed_to_store_candle", error=str(e))

            self.stats["candles_stored"] += stored
            log.info(
                "candles_fetched_and_stored",
                instrument=instrument,
                granularity=granularity,
                count=stored,
            )

        except Exception as e:
            log.error(
                "failed_to_fetch_candles",
                instrument=instrument,
                error=str(e),
            )
            self.stats["errors"] += 1

    async def periodic_candle_fetch(self):
        """Periodically fetch candles for all instruments."""
        log.info("starting_periodic_candle_fetch", interval_minutes=15)

        while self.running:
            try:
                # Fetch 1-hour candles for all instruments
                for instrument in self.instruments:
                    if not self.running:
                        break

                    await self.fetch_and_store_candles(
                        instrument=instrument,
                        granularity="H1",
                        count=50,  # Last 50 hours
                    )

                    # Small delay between instruments
                    await asyncio.sleep(2)

                # Fetch 5-minute candles (more frequently)
                for instrument in self.instruments[:3]:  # Top 3 pairs
                    if not self.running:
                        break

                    await self.fetch_and_store_candles(
                        instrument=instrument,
                        granularity="M5",
                        count=100,
                    )

                    await asyncio.sleep(1)

                # Wait 15 minutes before next fetch
                await asyncio.sleep(900)

            except Exception as e:
                log.error("periodic_fetch_error", error=str(e))
                await asyncio.sleep(60)  # Wait 1 minute on error

    async def print_statistics(self):
        """Periodically print collection statistics."""
        while self.running:
            await asyncio.sleep(60)  # Every minute

            uptime = datetime.now(timezone.utc) - self.stats["start_time"]
            prices_per_min = (
                self.stats["prices_stored"] / uptime.total_seconds() * 60
                if uptime.total_seconds() > 0
                else 0
            )

            log.info(
                "collector_statistics",
                uptime_minutes=int(uptime.total_seconds() / 60),
                prices_received=self.stats["prices_received"],
                prices_stored=self.stats["prices_stored"],
                candles_stored=self.stats["candles_stored"],
                errors=self.stats["errors"],
                prices_per_minute=f"{prices_per_min:.1f}",
                last_price=self.stats["last_price_time"].isoformat()
                if self.stats["last_price_time"]
                else "Never",
            )

    async def run(self):
        """Run the data collector."""
        self.running = True

        try:
            await self.initialize()

            # Start concurrent tasks
            tasks = [
                asyncio.create_task(self.stream_prices(), name="price_stream"),
                asyncio.create_task(
                    self.periodic_candle_fetch(), name="candle_fetch"
                ),
                asyncio.create_task(self.print_statistics(), name="statistics"),
            ]

            log.info("collector_started", tasks=len(tasks))

            # Wait for tasks (they run forever or until stopped)
            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            log.error("collector_error", error=str(e))
            raise

        finally:
            await self.cleanup()

    async def cleanup(self):
        """Clean up resources."""
        log.info("cleaning_up")

        self.running = False

        if self.oanda_adapter:
            await self.oanda_adapter.close()

        if self.db_pool:
            await self.db_pool.close()

        log.info("cleanup_complete")

    def handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        log.info("shutdown_signal_received", signal=signum)
        self.running = False


async def main():
    """Main entry point."""
    collector = ForexDataCollector()

    # Handle shutdown signals
    signal.signal(signal.SIGINT, collector.handle_signal)
    signal.signal(signal.SIGTERM, collector.handle_signal)

    try:
        await collector.run()
    except KeyboardInterrupt:
        log.info("interrupted_by_user")
    except Exception as e:
        log.error("collector_failed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
