"""Resilience patterns for production trading systems (2025 standard).

Implements:
- Exponential backoff with jitter
- Circuit breakers
- Automatic retry decorators
- Timeout management
"""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

import structlog

log = structlog.get_logger()

P = ParamSpec("P")
T = TypeVar("T")


def with_exponential_backoff(
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator for automatic retry with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff (default 2.0)
        jitter: Add random jitter to prevent thundering herd

    Example:
        >>> @with_exponential_backoff(max_retries=3)
        ... async def fetch_data():
        ...     return await api.get_data()
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            delay = base_delay

            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)

                except Exception as e:
                    # Last attempt - re-raise
                    if attempt == max_retries - 1:
                        log.error(
                            "retry.exhausted",
                            function=func.__name__,
                            attempts=max_retries,
                            error=str(e),
                        )
                        raise

                    # Calculate backoff with optional jitter
                    current_delay = delay
                    if jitter:
                        # Add random jitter ±25%
                        current_delay *= random.uniform(0.75, 1.25)

                    current_delay = min(current_delay, max_delay)

                    log.warning(
                        "retry.attempt",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay=current_delay,
                        error=str(e),
                    )

                    await asyncio.sleep(current_delay)
                    delay *= exponential_base

        return wrapper

    return decorator


class CircuitBreaker:
    """Circuit breaker pattern for fault tolerance.

    Prevents cascading failures by stopping requests to failing services.

    States:
    - CLOSED: Normal operation
    - OPEN: Service is failing, reject all requests
    - HALF_OPEN: Test if service recovered

    Example:
        >>> breaker = CircuitBreaker(failure_threshold=5)
        >>> async with breaker:
        ...     await api_call()
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        success_threshold: int = 2,
        name: str = "default",
    ) -> None:
        """Initialize circuit breaker.

        Args:
            failure_threshold: Failures before opening circuit
            timeout: Seconds before attempting half-open
            success_threshold: Successes needed to close circuit
            name: Circuit breaker name for logging
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.success_threshold = success_threshold
        self.name = name

        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float | None = None
        self.state = "CLOSED"

    async def __aenter__(self):
        """Check circuit state before proceeding."""
        if self.state == "OPEN":
            # Check if timeout expired
            if (
                self.last_failure_time
                and time.monotonic() - self.last_failure_time
                > self.timeout
            ):
                log.info("circuit_breaker.half_open", name=self.name)
                self.state = "HALF_OPEN"
                self.success_count = 0
            else:
                msg = f"Circuit breaker {self.name} is OPEN"
                raise CircuitBreakerError(msg)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Update circuit state based on result."""
        if exc_type is None:
            # Success
            self._on_success()
        else:
            # Failure
            self._on_failure()

    def _on_success(self) -> None:
        """Handle successful request."""
        if self.state == "HALF_OPEN":
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                log.info("circuit_breaker.closed", name=self.name)
                self.state = "CLOSED"
                self.failure_count = 0
                self.success_count = 0
        elif self.state == "CLOSED":
            self.failure_count = max(0, self.failure_count - 1)

    def _on_failure(self) -> None:
        """Handle failed request."""
        self.failure_count += 1
        self.last_failure_time = time.monotonic()

        if self.failure_count >= self.failure_threshold:
            log.warning(
                "circuit_breaker.opened",
                name=self.name,
                failures=self.failure_count,
            )
            self.state = "OPEN"
            self.success_count = 0


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""

    pass


async def with_timeout(
    coro: Awaitable[T],
    timeout: float,
    error_message: str = "Operation timed out",
) -> T:
    """Execute coroutine with timeout.

    Args:
        coro: Coroutine to execute
        timeout: Timeout in seconds
        error_message: Error message for timeout

    Returns:
        Coroutine result

    Raises:
        TimeoutError: If operation times out

    Example:
        >>> result = await with_timeout(slow_api_call(), timeout=5.0)
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError as e:
        log.error("timeout", timeout=timeout, message=error_message)
        raise TimeoutError(error_message) from e


class ConnectionPool:
    """Async connection pool for resource management.

    Maintains a pool of connections for efficient reuse.

    Example:
        >>> pool = ConnectionPool(max_connections=10)
        >>> async with pool.acquire() as conn:
        ...     await conn.execute_query()
    """

    def __init__(self, max_connections: int = 10) -> None:
        """Initialize connection pool.

        Args:
            max_connections: Maximum number of connections
        """
        self.max_connections = max_connections
        self.semaphore = asyncio.Semaphore(max_connections)
        self.connections: list[Any] = []

    async def acquire(self):
        """Acquire connection from pool."""
        await self.semaphore.acquire()
        return self

    async def release(self) -> None:
        """Release connection back to pool."""
        self.semaphore.release()

    async def __aenter__(self):
        """Context manager entry."""
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.release()
