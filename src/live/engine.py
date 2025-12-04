"""Live trading engine with async event loop and structured concurrency.

Uses Python 3.11+ asyncio.TaskGroup for clean lifecycle management.
All concurrent tasks are properly structured with automatic cleanup on errors.
"""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import time

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
        initial_cash: float | None = None,
    ) -> None:
        """Initialize live engine.

        Args:
            exec_engine: Execution engine for order submission
            data_feed: Async iterator of market snapshots
            policy: Trading policy
            tick_rate_hz: Policy evaluation rate (trades per second)
            initial_cash: Starting cash if broker does not report (defaults to INITIAL_CASH env or 0)
        """
        self.exec_engine = exec_engine
        self.data_feed = data_feed
        self.policy = policy
        self.tick_interval = 1.0 / tick_rate_hz
        env_initial_cash = os.getenv("INITIAL_CASH")
        self.initial_cash = (
            initial_cash
            if initial_cash is not None
            else float(env_initial_cash) if env_initial_cash is not None else 0.0
        )
        self._shutdown = asyncio.Event()
        self._last_portfolio: PortfolioState | None = None
        self._last_snapshot: MarketSnapshot | None = None

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
                self._last_snapshot = snapshot

                # Fetch current portfolio state
                portfolio = await self._fetch_portfolio(snapshot)

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
            fill_stream = await self.exec_engine.stream_fills()
            async for fill in fill_stream:
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

    async def _fetch_portfolio(self, snapshot: MarketSnapshot | None = None) -> PortfolioState:
        """Fetch current portfolio state from execution engine."""
        positions = await self.exec_engine.get_positions()
        snapshot = snapshot or self._last_snapshot

        # Try to get actual account info from broker
        try:
            account_info = await self.exec_engine.get_account()
            cash = account_info.get("cash", self.initial_cash)
            equity = account_info.get("equity", cash)

            log.debug(
                "portfolio.broker_sync",
                cash=cash,
                equity=equity,
                positions=len(positions),
            )
        except (NotImplementedError, AttributeError):
            # Fallback: estimate from positions and previous cash
            log.debug("portfolio.estimating", reason="broker_account_unavailable")

            positions_value = 0.0
            if snapshot:
                for symbol, qty in positions.items():
                    price = snapshot.prices.get(symbol)
                    if price is None:
                        continue
                    positions_value += qty * price

            # Use previous cash balance if known; otherwise start at configured initial cash.
            cash = self._last_portfolio.cash if self._last_portfolio else self.initial_cash
            equity = cash + positions_value

        self._last_portfolio = PortfolioState(
            positions=positions,
            cash=cash,
            equity=equity,
            timestamp=time.time_ns(),
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
    processors = [ # type: ignore[attr-defined]
        structlog.contextvars.merge_contextvars,  # type: ignore[attr-defined]
        structlog.processors.add_log_level,  # type: ignore[attr-defined]
        structlog.processors.TimeStamper(fmt="iso"), # type: ignore[attr-defined]
    ]

    if json_output:
        processors.append(structlog.processors.JSONRenderer())  # type: ignore[attr-defined]
    else:
        processors.append(structlog.dev.ConsoleRenderer())  # type: ignore[attr-defined]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
