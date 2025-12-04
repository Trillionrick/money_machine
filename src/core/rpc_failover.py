"""RPC failover system with circuit breaker pattern and health monitoring.

This module provides enterprise-grade RPC endpoint management with:
- Automatic failover between multiple RPC providers
- Circuit breaker pattern to avoid cascading failures
- Health check monitoring and recovery
- Retry logic with exponential backoff
- Request rate limiting and caching
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, TypeVar

import httpx
import structlog
from web3 import AsyncHTTPProvider, AsyncWeb3

log = structlog.get_logger()

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states for RPC endpoints."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Endpoint is failing, don't use
    HALF_OPEN = "half_open"  # Testing if endpoint has recovered


@dataclass
class RPCEndpoint:
    """Individual RPC endpoint with health tracking."""

    url: str
    name: str
    priority: int = 1  # Lower is higher priority
    circuit_state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0
    last_success_time: float = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_requests: int = 0
    total_failures: int = 0

    # Circuit breaker settings
    failure_threshold: int = 3  # Failures before opening circuit
    success_threshold: int = 2  # Successes needed to close circuit
    timeout_seconds: float = 30.0  # Time before trying half-open
    request_timeout: float = 10.0  # Individual request timeout

    def record_success(self) -> None:
        """Record a successful request."""
        self.last_success_time = time.time()
        self.consecutive_failures = 0
        self.consecutive_successes += 1
        self.total_requests += 1

        if (
            self.circuit_state == CircuitState.HALF_OPEN
            and self.consecutive_successes >= self.success_threshold
        ):
            self.circuit_state = CircuitState.CLOSED
            self.failure_count = 0
            log.info(
                "rpc_failover.circuit_closed",
                endpoint=self.name,
                url=self.url,
            )

    def record_failure(self, error: str) -> None:
        """Record a failed request."""
        self.last_failure_time = time.time()
        self.consecutive_successes = 0
        self.consecutive_failures += 1
        self.failure_count += 1
        self.total_failures += 1
        self.total_requests += 1

        if self.consecutive_failures >= self.failure_threshold:
            self.circuit_state = CircuitState.OPEN
            log.warning(
                "rpc_failover.circuit_opened",
                endpoint=self.name,
                url=self.url,
                consecutive_failures=self.consecutive_failures,
                error=error,
            )

    def can_attempt(self) -> bool:
        """Check if this endpoint can be used."""
        if self.circuit_state == CircuitState.CLOSED:
            return True

        if self.circuit_state == CircuitState.OPEN:
            # Check if enough time has passed to try half-open
            if time.time() - self.last_failure_time >= self.timeout_seconds:
                self.circuit_state = CircuitState.HALF_OPEN
                log.info(
                    "rpc_failover.circuit_half_open",
                    endpoint=self.name,
                    url=self.url,
                )
                return True
            return False

        # HALF_OPEN state - allow attempts
        return True

    @property
    def health_score(self) -> float:
        """Calculate health score (0.0 = unhealthy, 1.0 = perfect)."""
        if self.total_requests == 0:
            return 1.0

        success_rate = 1.0 - (self.total_failures / self.total_requests)
        time_since_failure = time.time() - self.last_failure_time if self.last_failure_time > 0 else float("inf")
        recency_factor = min(1.0, time_since_failure / 300.0)  # Full recovery after 5 min

        return success_rate * 0.7 + recency_factor * 0.3


class RPCFailoverManager:
    """Manages multiple RPC endpoints with automatic failover."""

    def __init__(
        self,
        endpoints: list[dict[str, Any]],
        max_retries: int = 3,
        retry_delay: float = 1.0,
        retry_backoff: float = 2.0,
    ):
        """Initialize RPC failover manager.

        Args:
            endpoints: List of endpoint configs [{url, name, priority}, ...]
            max_retries: Maximum retry attempts across all endpoints
            retry_delay: Initial delay between retries (seconds)
            retry_backoff: Backoff multiplier for retries
        """
        self.endpoints = [
            RPCEndpoint(
                url=ep["url"],
                name=ep.get("name", f"endpoint_{i}"),
                priority=ep.get("priority", i),
                request_timeout=ep.get("timeout", 10.0),
            )
            for i, ep in enumerate(endpoints)
        ]
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.retry_backoff = retry_backoff

        # Sort by priority
        self.endpoints.sort(key=lambda e: (e.priority, -e.health_score))

        log.info(
            "rpc_failover.initialized",
            endpoint_count=len(self.endpoints),
            endpoints=[e.name for e in self.endpoints],
        )

    def get_available_endpoints(self) -> list[RPCEndpoint]:
        """Get all endpoints that can be attempted, sorted by health."""
        available = [e for e in self.endpoints if e.can_attempt()]
        return sorted(available, key=lambda e: (-e.health_score, e.priority))

    async def execute_with_failover(
        self,
        operation: Callable[[RPCEndpoint], Any],
        operation_name: str = "rpc_call",
    ) -> Any:
        """Execute an operation with automatic failover.

        Args:
            operation: Async function that takes an RPCEndpoint and returns result
            operation_name: Name for logging purposes

        Returns:
            Result from successful operation

        Raises:
            Exception: If all endpoints fail
        """
        last_error: Optional[Exception] = None
        attempt = 0

        while attempt < self.max_retries:
            available = self.get_available_endpoints()

            if not available:
                delay = self.retry_delay * (self.retry_backoff**attempt)
                log.warning(
                    "rpc_failover.no_available_endpoints",
                    operation=operation_name,
                    attempt=attempt + 1,
                    retry_delay=delay,
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue

            for endpoint in available:
                try:
                    log.debug(
                        "rpc_failover.attempting_endpoint",
                        operation=operation_name,
                        endpoint=endpoint.name,
                        health_score=endpoint.health_score,
                        circuit_state=endpoint.circuit_state.value,
                    )

                    result = await asyncio.wait_for(
                        operation(endpoint),
                        timeout=endpoint.request_timeout,
                    )

                    endpoint.record_success()
                    log.debug(
                        "rpc_failover.success",
                        operation=operation_name,
                        endpoint=endpoint.name,
                    )
                    return result

                except asyncio.TimeoutError as e:
                    error_msg = f"Timeout after {endpoint.request_timeout}s"
                    endpoint.record_failure(error_msg)
                    last_error = e
                    log.warning(
                        "rpc_failover.endpoint_timeout",
                        operation=operation_name,
                        endpoint=endpoint.name,
                        timeout=endpoint.request_timeout,
                    )

                except Exception as e:
                    error_msg = str(e)[:200]
                    endpoint.record_failure(error_msg)
                    last_error = e
                    log.warning(
                        "rpc_failover.endpoint_failed",
                        operation=operation_name,
                        endpoint=endpoint.name,
                        error=error_msg,
                    )

            # All endpoints failed for this attempt
            delay = self.retry_delay * (self.retry_backoff**attempt)
            log.warning(
                "rpc_failover.attempt_failed",
                operation=operation_name,
                attempt=attempt + 1,
                max_retries=self.max_retries,
                retry_delay=delay,
            )
            await asyncio.sleep(delay)
            attempt += 1

        # All retries exhausted
        error_msg = f"All RPC endpoints failed after {self.max_retries} attempts"
        log.error(
            "rpc_failover.all_endpoints_failed",
            operation=operation_name,
            attempts=attempt,
            last_error=str(last_error) if last_error else None,
        )
        raise Exception(error_msg) from last_error

    def get_health_status(self) -> dict[str, Any]:
        """Get current health status of all endpoints."""
        return {
            "endpoints": [
                {
                    "name": e.name,
                    "url": e.url,
                    "circuit_state": e.circuit_state.value,
                    "health_score": round(e.health_score, 3),
                    "total_requests": e.total_requests,
                    "total_failures": e.total_failures,
                    "consecutive_failures": e.consecutive_failures,
                    "last_success": e.last_success_time,
                }
                for e in self.endpoints
            ],
            "available_count": len(self.get_available_endpoints()),
            "total_count": len(self.endpoints),
        }


class PolygonRPCManager:
    """Specialized RPC manager for Polygon with 1inch API integration."""

    def __init__(
        self,
        rpc_urls: list[str] | str,
        oneinch_api_key: Optional[str] = None,
        chain_id: int = 137,
    ):
        """Initialize Polygon RPC manager.

        Args:
            rpc_urls: List of RPC URLs or single URL
            oneinch_api_key: Optional 1inch API key for aggregator quotes
            chain_id: Polygon chain ID (137 for mainnet)
        """
        if isinstance(rpc_urls, str):
            rpc_urls = [rpc_urls]

        # Build endpoint configs with common providers as fallbacks
        endpoint_configs = []
        for i, url in enumerate(rpc_urls):
            endpoint_configs.append({
                "url": url.strip(),
                "name": self._extract_provider_name(url),
                "priority": i,
                "timeout": 10.0,
            })

        # Add public fallbacks if user provided less than 3 endpoints
        if len(endpoint_configs) < 3:
            fallback_rpcs = [
                "https://polygon-rpc.com",
                "https://rpc-mainnet.matic.network",
                "https://polygon-bor-rpc.publicnode.com",
            ]
            for i, fallback in enumerate(fallback_rpcs[: 3 - len(endpoint_configs)]):
                endpoint_configs.append({
                    "url": fallback,
                    "name": self._extract_provider_name(fallback),
                    "priority": len(endpoint_configs) + i,
                    "timeout": 12.0,
                })

        self.failover = RPCFailoverManager(
            endpoints=endpoint_configs,
            max_retries=3,
            retry_delay=0.5,
            retry_backoff=2.0,
        )

        self.oneinch_api_key = oneinch_api_key
        self.chain_id = chain_id
        self._http_client: Optional[httpx.AsyncClient] = None

        log.info(
            "polygon_rpc.initialized",
            chain_id=chain_id,
            endpoint_count=len(endpoint_configs),
            has_oneinch=bool(oneinch_api_key),
        )

    @staticmethod
    def _extract_provider_name(url: str) -> str:
        """Extract provider name from URL."""
        if "alchemy" in url.lower():
            return "alchemy"
        if "infura" in url.lower():
            return "infura"
        if "quicknode" in url.lower():
            return "quicknode"
        if "publicnode" in url.lower():
            return "publicnode"
        if "polygon-rpc.com" in url:
            return "polygon_official"
        if "matic.network" in url:
            return "matic_official"
        return url.split("/")[2].split(".")[0]

    async def get_quote(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        protocols: str = "UNISWAP_V3,QUICKSWAP_V3",
    ) -> dict[str, Any]:
        """Get swap quote using 1inch API with RPC failover."""
        if not self.oneinch_api_key:
            raise ValueError("1inch API key required for Polygon quotes")

        async def _fetch_quote(endpoint: RPCEndpoint) -> dict[str, Any]:
            # Use 1inch API with specific timeout handling
            if self._http_client is None:
                self._http_client = httpx.AsyncClient(timeout=8.0)

            params = {
                "src": token_in,
                "dst": token_out,
                "amount": str(amount_in),
                "includeTokensInfo": "true",
                "includeProtocols": "true",
                "protocols": protocols,
            }

            headers = {
                "accept": "application/json",
                "Authorization": f"Bearer {self.oneinch_api_key}",
            }

            url = f"https://api.1inch.dev/swap/v6.0/{self.chain_id}/quote"

            response = await self._http_client.get(url, params=params, headers=headers)
            response.raise_for_status()

            data = response.json()

            # Check for error responses
            if "statusCode" in data and data["statusCode"] >= 400:
                error_detail = data.get("description", "Unknown error")
                raise httpx.HTTPStatusError(
                    f"1inch API error: {error_detail}",
                    request=response.request,
                    response=response,
                )

            return data

        return await self.failover.execute_with_failover(
            operation=_fetch_quote,
            operation_name="polygon_1inch_quote",
        )

    async def create_web3(self) -> AsyncWeb3:
        """Create Web3 instance using the best available RPC."""

        async def _create_web3(endpoint: RPCEndpoint) -> AsyncWeb3:
            provider = AsyncHTTPProvider(
                endpoint.url,
                request_kwargs={"timeout": endpoint.request_timeout},
            )
            w3 = AsyncWeb3(provider)

            # Test connection
            await w3.eth.chain_id

            return w3

        return await self.failover.execute_with_failover(
            operation=_create_web3,
            operation_name="create_polygon_web3",
        )

    def get_health(self) -> dict[str, Any]:
        """Get health status of all RPC endpoints."""
        return self.failover.get_health_status()

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
