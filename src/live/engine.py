"""Live trading engine with async event loop and structured concurrency.

Uses Python 3.11+ asyncio.TaskGroup for clean lifecycle management.
All concurrent tasks are properly structured with automatic cleanup on errors.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog

from src.core.execution import ExecutionEngine
from src.core.policy import MarketSnapshot, Policy, PortfolioState

log = structlog.get_logger()


class LiveEngine:
    """Async trading engine with clean lifecycle management.

    This engine:
    1. Consumes market data from an async feed
    2. Calls policy.decide() to generate orders
    3. Submits orders via execution engine
    4. Processes fills asynchronously
    5. Monitors system health

    Uses structured concurrency (TaskGroup) for automatic cleanup.

    Example:
        >>> async def run():
        ...     engine = LiveEngine(exec_engine, data_feed, policy)
        ...     async with engine.lifecycle():
        ...         await engine.run()
    """

    def __init__(
        self,
        exec_engine: ExecutionEngine,
        data_feed: AsyncIterator[MarketSnapshot],
        policy: Policy,
        *,
        tick_rate_hz: float = 1.0,
    ) -> None:
        """Initialize live engine.

        Args:
            exec_engine: Execution engine for order submission
            data_feed: Async iterator of market snapshots
            policy: Trading policy
            tick_rate_hz: Policy evaluation rate (trades per second)
        """
        self.exec_engine = exec_engine
        self.data_feed = data_feed
        self.policy = policy
        self.tick_interval = 1.0 / tick_rate_hz
        self._shutdown = asyncio.Event()
        self._last_portfolio: PortfolioState | None = None

    @asynccontextmanager
    async def lifecycle(self) -> AsyncIterator["LiveEngine"]:
        """Context manager for clean startup/shutdown.

        Example:
            >>> async with engine.lifecycle():
            ...     await engine.run()
        """
        log.info("engine.starting", tick_rate_hz=1.0 / self.tick_interval)
        try:
            yield self
        finally:
            log.info("engine.shutting_down")
            self._shutdown.set()
            # Allow time for graceful shutdown
            await asyncio.sleep(0.1)

    async def run(self) -> None:
        """Main event loop with TaskGroup for structured concurrency.

        All tasks run concurrently and are automatically cleaned up if any fails.
        """
        try:
            async with asyncio.TaskGroup() as tg:
                # Launch concurrent tasks
                tg.create_task(self._market_data_loop(), name="market_data")
                tg.create_task(self._fill_handler_loop(), name="fill_handler")
                tg.create_task(self._health_monitor(), name="health_monitor")

        except* Exception as eg:  # Catch exception group from TaskGroup
            log.exception("engine.error", exceptions=[str(e) for e in eg.exceptions])
            raise

    async def _market_data_loop(self) -> None:
        """Process market data and generate orders."""
        try:
            async for snapshot in self.data_feed:
                if self._shutdown.is_set():
                    break

                # Fetch current portfolio state
                portfolio = await self._fetch_portfolio()

                # Call policy to decide orders
                try:
                    orders = self.policy.decide(portfolio, snapshot)
                except Exception:
                    log.exception(
                        "policy.error",
                        timestamp=snapshot.timestamp,
                    )
                    continue

                # Submit orders if any
                if orders:
                    try:
                        await self.exec_engine.submit_orders(orders)
                        log.info(
                            "orders.submitted",
                            count=len(orders),
                            symbols=[o.symbol for o in orders],
                        )
                    except Exception:
                        log.exception("orders.submit_failed", count=len(orders))

                # Rate limiting
                await asyncio.sleep(self.tick_interval)

        except asyncio.CancelledError:
            log.info("market_data_loop.cancelled")
            raise

    async def _fill_handler_loop(self) -> None:
        """Process execution fills asynchronously."""
        try:
            async for fill in self.exec_engine.stream_fills():
                if self._shutdown.is_set():
                    break

                # Notify policy of fill
                try:
                    self.policy.on_fill(fill)
                except Exception:
                    log.exception("policy.on_fill_error", fill=fill)

                log.info(
                    "fill.received",
                    symbol=fill.symbol,
                    side=fill.side,
                    quantity=fill.quantity,
                    price=fill.price,
                )

        except asyncio.CancelledError:
            log.info("fill_handler_loop.cancelled")
            raise

    async def _health_monitor(self) -> None:
        """Periodic health checks and system monitoring."""
        try:
            while not self._shutdown.is_set():
                await asyncio.sleep(60.0)  # Check every minute

                try:
                    # Check basic system health
                    portfolio = await self._fetch_portfolio()

                    log.info(
                        "health.check",
                        status="ok",
                        equity=portfolio.equity,
                        positions=len(portfolio.positions),
                    )

                except Exception:
                    log.exception("health.check_failed")

        except asyncio.CancelledError:
            log.info("health_monitor.cancelled")
            raise

    async def _fetch_portfolio(self) -> PortfolioState:
        """Fetch current portfolio state from execution engine.

        TODO: Implement actual cash/equity calculation from broker.
        """
        positions = await self.exec_engine.get_positions()

        # Calculate total equity (simplified - real impl would query broker)
        # For now, return last known state or create new one
        if self._last_portfolio is not None:
            self._last_portfolio = PortfolioState(
                positions=positions,
                cash=self._last_portfolio.cash,
                equity=self._last_portfolio.equity,
                timestamp=asyncio.get_event_loop().time_ns(),
            )
        else:
            self._last_portfolio = PortfolioState(
                positions=positions,
                cash=100_000.0,  # Default starting cash
                equity=100_000.0,
                timestamp=asyncio.get_event_loop().time_ns(),
            )

        return self._last_portfolio

    async def stop(self) -> None:
        """Signal engine to stop gracefully."""
        log.info("engine.stop_requested")
        self._shutdown.set()


# Configure structured logging
def configure_logging(*, json_output: bool = True, level: str = "INFO") -> None:
    """Configure structlog for production use.

    Args:
        json_output: If True, output JSON logs (for production)
        level: Log level (DEBUG, INFO, WARNING, ERROR)
    """
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
