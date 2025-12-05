"""Tests for resilience and rate limiter utilities."""

import asyncio
import time

import pytest

from src.utils.rate_limiter import AdaptiveRateLimiter, MultiEndpointRateLimiter
from src.utils.resilience import (
    CircuitBreaker,
    CircuitBreakerError,
    ConnectionPool,
    with_exponential_backoff,
    with_timeout,
)


@pytest.mark.asyncio
async def test_adaptive_rate_limiter_enforces_window() -> None:
    limiter = AdaptiveRateLimiter(max_requests=2, time_window=0.05, name="test")
    start = time.perf_counter()
    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()  # should wait for window to roll
    elapsed = time.perf_counter() - start
    assert elapsed >= 0.05
    assert limiter.get_stats()["total_waited"] > 0


def test_multi_endpoint_rate_limiter_returns_specific_limiters() -> None:
    multi = MultiEndpointRateLimiter(
        {"/orders": (1, 1.0)},
        default_limit=(2, 1.0),
    )
    assert multi.limit("/orders").name == "/orders"
    assert multi.limit("/unknown").name == "_default"
    # Ensure missing default creates permissive limiter
    multi_no_default = MultiEndpointRateLimiter({})
    assert multi_no_default.limit("/foo").max_requests > 1000


@pytest.mark.asyncio
async def test_with_exponential_backoff_retries_then_succeeds() -> None:
    attempts = 0

    @with_exponential_backoff(max_retries=3, base_delay=0.01, max_delay=0.02, jitter=False)
    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("fail")
        return "ok"

    start = time.perf_counter()
    result = await flaky()
    elapsed = time.perf_counter() - start
    assert result == "ok"
    assert attempts == 3
    assert elapsed >= 0.03


@pytest.mark.asyncio
async def test_circuit_breaker_opens_and_recovers() -> None:
    breaker = CircuitBreaker(failure_threshold=2, timeout=0.01, success_threshold=1, name="cb")

    # First failure
    with pytest.raises(RuntimeError):
        async with breaker:
            raise RuntimeError("boom")
    # Second failure should open
    with pytest.raises(RuntimeError):
        async with breaker:
            raise RuntimeError("boom")

    # Now circuit is open, should reject immediately
    with pytest.raises(CircuitBreakerError):
        async with breaker:
            pass

    # Fast-forward timeout and allow half-open
    breaker.last_failure_time = time.monotonic() - 1.0
    async with breaker:
        pass
    assert breaker.state == "CLOSED"


@pytest.mark.asyncio
async def test_with_timeout_raises_on_slow_coroutine() -> None:
    async def slow():
        await asyncio.sleep(0.05)

    with pytest.raises(TimeoutError):
        await with_timeout(slow(), timeout=0.01)


@pytest.mark.asyncio
async def test_connection_pool_limits_concurrency() -> None:
    pool = ConnectionPool(max_connections=1)
    acquired = 0

    async def task():
        nonlocal acquired
        async with pool:
            acquired += 1
            await asyncio.sleep(0.01)

    await asyncio.gather(task(), task())
    assert acquired == 2
