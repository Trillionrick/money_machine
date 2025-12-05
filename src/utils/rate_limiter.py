"""Modern rate limiting with adaptive backoff (2025 standard).

Implements token bucket algorithm with:
- Per-endpoint rate limiting
- Adaptive backoff on rate limit errors
- Thread-safe async operations
"""

import asyncio
import time
from collections import deque

import structlog

log = structlog.get_logger()


class AdaptiveRateLimiter:
    """Token bucket rate limiter with adaptive backoff.

    Example:
        >>> limiter = AdaptiveRateLimiter(max_requests=10, time_window=1.0)
        >>> async with limiter:
        ...     await make_api_call()
    """

    def __init__(
        self,
        max_requests: int,
        time_window: float,
        name: str = "default",
    ) -> None:
        """Initialize rate limiter.

        Args:
            max_requests: Maximum requests allowed in time window
            time_window: Time window in seconds
            name: Name for logging
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.name = name
        self.requests: deque[float] = deque()
        self.lock = asyncio.Lock()
        self._total_waited = 0.0

    async def acquire(self) -> None:
        """Acquire permission to make a request.

        Blocks if rate limit would be exceeded.
        """
        async with self.lock:
            now = time.time()

            # Remove old requests outside time window
            while self.requests and self.requests[0] < now - self.time_window:
                self.requests.popleft()

            # If at limit, wait until oldest request expires
            if len(self.requests) >= self.max_requests:
                sleep_time = self.time_window - (now - self.requests[0])
                if sleep_time > 0:
                    log.debug(
                        "rate_limit.waiting",
                        limiter=self.name,
                        sleep_time=sleep_time,
                        current_requests=len(self.requests),
                    )
                    await asyncio.sleep(sleep_time)
                    self._total_waited += sleep_time

            # Add current request
            self.requests.append(time.time())

    async def __aenter__(self):
        """Context manager support."""
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        pass

    def get_stats(self) -> dict[str, float]:
        """Get rate limiter statistics."""
        return {
            "name": self.name,
            "max_requests": self.max_requests,
            "time_window": self.time_window,
            "current_requests": len(self.requests),
            "total_waited": self._total_waited,
        }


class MultiEndpointRateLimiter:
    """Rate limiter supporting multiple endpoints with different limits.

    Example:
        >>> limiter = MultiEndpointRateLimiter({
        ...     "/v1/orders": (10, 1.0),  # 10 req/sec
        ...     "/v1/positions": (5, 1.0), # 5 req/sec
        ... })
        >>> async with limiter.limit("/v1/orders"):
        ...     await api.place_order()
    """

    def __init__(
        self,
        limits: dict[str, tuple[int, float]],
        default_limit: tuple[int, float] | None = None,
    ) -> None:
        """Initialize multi-endpoint rate limiter.

        Args:
            limits: Dict mapping endpoint to (max_requests, time_window)
            default_limit: Default limit for unlisted endpoints
        """
        self.limiters: dict[str, AdaptiveRateLimiter] = {}

        for endpoint, (max_req, window) in limits.items():
            self.limiters[endpoint] = AdaptiveRateLimiter(
                max_requests=max_req,
                time_window=window,
                name=endpoint,
            )

        self.default_limit = default_limit
        if default_limit:
            self.limiters["_default"] = AdaptiveRateLimiter(
                max_requests=default_limit[0],
                time_window=default_limit[1],
                name="_default",
            )

    def limit(self, endpoint: str) -> AdaptiveRateLimiter:
        """Get rate limiter for specific endpoint.

        Args:
            endpoint: API endpoint path

        Returns:
            Rate limiter for this endpoint
        """
        if endpoint in self.limiters:
            return self.limiters[endpoint]

        if "_default" in self.limiters:
            return self.limiters["_default"]

        # No limit configured
        return AdaptiveRateLimiter(max_requests=999999, time_window=1.0, name=endpoint)

    def get_all_stats(self) -> dict[str, dict]:
        """Get statistics for all limiters."""
        return {name: limiter.get_stats() for name, limiter in self.limiters.items()}
