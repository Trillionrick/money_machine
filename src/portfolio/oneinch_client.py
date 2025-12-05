"""1inch Portfolio API v5.0 client for tracking positions, profits, and performance.

Migration from v4 to v5.0:
- v5 uses snapshot (current state) and metrics (historical analytics)
- Snapshot: token amounts, prices, values at specific point in time
- Metrics: PnL, ROI, APR over selected time ranges

2025 Update: Full v5.0 implementation with failover support.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

import httpx
import structlog

log = structlog.get_logger()


class TimeRange(Enum):
    """Time ranges for metrics queries."""

    ONE_DAY = "1day"
    ONE_WEEK = "1week"
    ONE_MONTH = "1month"
    THREE_MONTHS = "3months"
    ONE_YEAR = "1year"
    ALL_TIME = "all"


class PortfolioStatus(Enum):
    """Portfolio availability status."""

    AVAILABLE = "available"
    PROCESSING = "processing"
    UNAVAILABLE = "unavailable"


@dataclass
class ChainSnapshot:
    """Snapshot of positions on a specific chain."""

    chain_id: str
    total_value_usd: Decimal
    protocols: list[dict[str, Any]] = field(default_factory=list)
    tokens: list[dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PortfolioSnapshot:
    """Current state of entire portfolio across all chains."""

    address: str
    total_value_usd: Decimal
    chains: dict[str, ChainSnapshot]
    timestamp: datetime
    native_tokens_value_usd: Decimal = Decimal("0")
    erc20_tokens_value_usd: Decimal = Decimal("0")
    protocol_positions_value_usd: Decimal = Decimal("0")


@dataclass
class TokenMetrics:
    """Historical metrics for a specific token."""

    token_address: str
    symbol: str
    chain_id: str
    absolute_profit_usd: Decimal
    roi_percentage: Decimal
    current_balance: Decimal
    current_value_usd: Decimal


@dataclass
class ProtocolMetrics:
    """Historical metrics for a specific protocol position."""

    protocol_id: str
    protocol_name: str
    chain_id: str
    absolute_profit_usd: Decimal
    roi_percentage: Decimal
    apr_percentage: Decimal | None = None
    current_value_usd: Decimal = Decimal("0")


@dataclass
class PortfolioMetrics:
    """Historical performance metrics for entire portfolio."""

    address: str
    time_range: TimeRange
    total_profit_usd: Decimal
    total_roi_percentage: Decimal
    protocols: list[ProtocolMetrics] = field(default_factory=list)
    tokens: list[TokenMetrics] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class OneInchPortfolioClient:
    """Client for 1inch Portfolio API v5.0.

    Provides portfolio tracking with:
    - Snapshots: Current state of positions (tokens, amounts, values)
    - Metrics: Historical analytics (PnL, ROI, APR)
    - Multi-chain support
    - Automatic retries and failover
    """

    BASE_URL = "https://api.1inch.dev/portfolio/v5.0"

    def __init__(
        self,
        api_key: str,
        timeout: float = 10.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """Initialize Portfolio API client.

        Args:
            api_key: 1inch API key (Bearer token)
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries in seconds
        """
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self._client: httpx.AsyncClient | None = None
        self._headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        log.info(
            "portfolio.client_initialized",
            api_version="v5.0",
            timeout=timeout,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._headers,
            )
        return self._client

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        retry_count: int = 0,
    ) -> dict[str, Any]:
        """Make API request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            retry_count: Current retry attempt

        Returns:
            JSON response data

        Raises:
            httpx.HTTPStatusError: On HTTP errors after retries
            httpx.TimeoutException: On timeout after retries
        """
        url = f"{self.BASE_URL}{endpoint}"
        client = await self._get_client()

        try:
            response = await client.request(method, url, params=params)
            response.raise_for_status()

            log.debug(
                "portfolio.api_success",
                endpoint=endpoint,
                status=response.status_code,
            )

            return response.json()

        except httpx.HTTPStatusError as e:
            log.warning(
                "portfolio.api_http_error",
                endpoint=endpoint,
                status=e.response.status_code,
                detail=e.response.text[:200],
                retry=retry_count,
            )

            # Retry on 5xx errors
            if e.response.status_code >= 500 and retry_count < self.max_retries:
                await asyncio.sleep(self.retry_delay * (2**retry_count))
                return await self._request(method, endpoint, params, retry_count + 1)

            raise

        except httpx.TimeoutException as e:
            log.warning(
                "portfolio.api_timeout",
                endpoint=endpoint,
                retry=retry_count,
            )

            if retry_count < self.max_retries:
                await asyncio.sleep(self.retry_delay * (2**retry_count))
                return await self._request(method, endpoint, params, retry_count + 1)

            raise

        except Exception as e:
            log.error(
                "portfolio.api_error",
                endpoint=endpoint,
                error=str(e)[:200],
            )
            raise

    # ========== General Endpoints ==========

    async def get_status(self, address: str) -> PortfolioStatus:
        """Check if portfolio data is available for an address.

        Migrated from: /portfolio/v4/general/is_available
        Now uses: /portfolio/v5.0/general/status

        Args:
            address: Wallet address (checksummed)

        Returns:
            Portfolio availability status
        """
        data = await self._request("GET", f"/general/status/{address}")

        status_value = data.get("result", "unavailable")
        try:
            return PortfolioStatus(status_value)
        except ValueError:
            log.warning("portfolio.unknown_status", status=status_value)
            return PortfolioStatus.UNAVAILABLE

    async def get_supported_chains(self) -> list[dict[str, Any]]:
        """Get list of supported blockchain networks.

        Same as v4: /portfolio/v4/general/supported_chains

        Returns:
            List of supported chains with IDs and names
        """
        data = await self._request("GET", "/general/supported_chains")
        return data.get("result", [])

    async def get_supported_protocols(self) -> list[dict[str, Any]]:
        """Get list of supported DeFi protocols.

        Same as v4: /portfolio/v4/general/supported_protocols

        Returns:
            List of supported protocols
        """
        data = await self._request("GET", "/general/supported_protocols")
        return data.get("result", [])

    async def get_current_value(self, address: str) -> Decimal:
        """Get total portfolio value in USD.

        Migrated from: /portfolio/v4/general/current_value
        Now uses: /portfolio/v5.0/general/current_value (wrapped response)

        Args:
            address: Wallet address

        Returns:
            Total value in USD
        """
        data = await self._request("GET", f"/general/current_value/{address}")

        # v5.0 has wrapped response structure
        result = data.get("result", {})
        value_str = result.get("value_usd", "0")

        return Decimal(value_str)

    async def get_value_chart(
        self,
        address: str,
        time_range: TimeRange = TimeRange.ONE_MONTH,
        chain_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get historical portfolio value chart data.

        Migrated from: /portfolio/v4/general/value_chart
        Now uses: /portfolio/v5.0/general/chart

        Args:
            address: Wallet address
            time_range: Time period for chart
            chain_id: Optional chain filter

        Returns:
            List of {timestamp, value_usd} data points
        """
        params = {"timerange": time_range.value}
        if chain_id:
            params["chain_id"] = chain_id

        data = await self._request("GET", f"/general/chart/{address}", params=params)
        return data.get("result", [])

    async def check_address(self, address: str) -> dict[str, Any]:
        """Check if an address is valid and has activity.

        New in v5.0: /portfolio/v5.0/general/address_check

        Args:
            address: Wallet address to check

        Returns:
            Address validation info
        """
        data = await self._request("GET", f"/general/address_check/{address}")
        return data.get("result", {})

    # ========== Token Snapshot Endpoints ==========

    async def get_tokens_snapshot(
        self,
        address: str,
        chain_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get current snapshot of all token balances and values.

        Migrated from: /portfolio/v4/overview/erc20/current_value
        Now uses: /portfolio/v5.0/tokens/snapshot

        Provides current state: token amounts, prices, values in USD.

        Args:
            address: Wallet address
            chain_ids: Optional list of chain IDs to filter

        Returns:
            Token snapshot data with balances and values
        """
        params = {}
        if chain_ids:
            params["chain_ids"] = ",".join(chain_ids)

        data = await self._request("GET", f"/tokens/snapshot/{address}", params=params)
        return data.get("result", {})

    async def get_tokens_metrics(
        self,
        address: str,
        time_range: TimeRange = TimeRange.ONE_MONTH,
        chain_ids: list[str] | None = None,
    ) -> list[TokenMetrics]:
        """Get historical metrics for token holdings (profits, ROI).

        Migrated from: /portfolio/v4/overview/erc20/profit_and_loss
        Now uses: /portfolio/v5.0/tokens/metrics

        Provides historical analytics: profits, ROI over time range.

        Args:
            address: Wallet address
            time_range: Period for metrics calculation
            chain_ids: Optional list of chain IDs to filter

        Returns:
            List of token metrics with PnL and ROI
        """
        params = {"timerange": time_range.value}
        if chain_ids:
            params["chain_ids"] = ",".join(chain_ids)

        data = await self._request("GET", f"/tokens/metrics/{address}", params=params)

        # Parse response into TokenMetrics objects
        result = data.get("result", {})
        tokens_data = result.get("tokens", [])

        metrics = []
        for token in tokens_data:
            metrics.append(
                TokenMetrics(
                    token_address=token.get("address", ""),
                    symbol=token.get("symbol", ""),
                    chain_id=token.get("chain_id", ""),
                    absolute_profit_usd=Decimal(str(token.get("absolute_profit_usd", 0))),
                    roi_percentage=Decimal(str(token.get("roi_percentage", 0))),
                    current_balance=Decimal(str(token.get("balance", 0))),
                    current_value_usd=Decimal(str(token.get("value_usd", 0))),
                )
            )

        return metrics

    # ========== Protocol Snapshot Endpoints ==========

    async def get_protocols_snapshot(
        self,
        address: str,
        chain_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get current snapshot of all protocol positions.

        Migrated from: /portfolio/v4/overview/protocols/current_value
        Now uses: /portfolio/v5.0/protocols/snapshot

        Provides current state: underlying tokens, amounts, values.

        Args:
            address: Wallet address
            chain_ids: Optional list of chain IDs to filter

        Returns:
            Protocol positions snapshot
        """
        params = {}
        if chain_ids:
            params["chain_ids"] = ",".join(chain_ids)

        data = await self._request("GET", f"/protocols/snapshot/{address}", params=params)
        return data.get("result", {})

    async def get_protocols_metrics(
        self,
        address: str,
        time_range: TimeRange = TimeRange.ONE_MONTH,
        chain_ids: list[str] | None = None,
    ) -> list[ProtocolMetrics]:
        """Get historical metrics for protocol positions (PnL, ROI, APR).

        Migrated from: /portfolio/v4/overview/protocols/profit_and_loss
        Now uses: /portfolio/v5.0/protocols/metrics

        Provides historical analytics: profits, ROI, APR.

        Args:
            address: Wallet address
            time_range: Period for metrics calculation
            chain_ids: Optional list of chain IDs to filter

        Returns:
            List of protocol metrics with PnL, ROI, APR
        """
        params = {"timerange": time_range.value}
        if chain_ids:
            params["chain_ids"] = ",".join(chain_ids)

        data = await self._request("GET", f"/protocols/metrics/{address}", params=params)

        # Parse response into ProtocolMetrics objects
        result = data.get("result", {})
        protocols_data = result.get("protocols", [])

        metrics = []
        for protocol in protocols_data:
            apr = protocol.get("apr_percentage")
            metrics.append(
                ProtocolMetrics(
                    protocol_id=protocol.get("id", ""),
                    protocol_name=protocol.get("name", ""),
                    chain_id=protocol.get("chain_id", ""),
                    absolute_profit_usd=Decimal(str(protocol.get("absolute_profit_usd", 0))),
                    roi_percentage=Decimal(str(protocol.get("roi_percentage", 0))),
                    apr_percentage=Decimal(str(apr)) if apr is not None else None,
                    current_value_usd=Decimal(str(protocol.get("value_usd", 0))),
                )
            )

        return metrics

    # ========== High-Level Composite Methods ==========

    async def get_full_snapshot(
        self,
        address: str,
        chain_ids: list[str] | None = None,
    ) -> PortfolioSnapshot:
        """Get complete portfolio snapshot (tokens + protocols).

        Combines:
        - /tokens/snapshot
        - /protocols/snapshot
        - /general/current_value

        Args:
            address: Wallet address
            chain_ids: Optional list of chain IDs to filter

        Returns:
            Complete portfolio snapshot
        """
        # Fetch all data in parallel
        current_value_task = self.get_current_value(address)
        tokens_task = self.get_tokens_snapshot(address, chain_ids)
        protocols_task = self.get_protocols_snapshot(address, chain_ids)

        current_value, tokens_data, protocols_data = await asyncio.gather(
            current_value_task,
            tokens_task,
            protocols_task,
        )

        # Organize by chain
        chains: dict[str, ChainSnapshot] = {}

        # Process token data
        for chain_id, chain_tokens in tokens_data.items():
            if chain_id not in chains:
                chains[chain_id] = ChainSnapshot(
                    chain_id=chain_id,
                    total_value_usd=Decimal("0"),
                )

            chains[chain_id].tokens = chain_tokens.get("tokens", [])

        # Process protocol data
        for chain_id, chain_protocols in protocols_data.items():
            if chain_id not in chains:
                chains[chain_id] = ChainSnapshot(
                    chain_id=chain_id,
                    total_value_usd=Decimal("0"),
                )

            chains[chain_id].protocols = chain_protocols.get("protocols", [])

        # Calculate chain totals
        for chain in chains.values():
            token_value = sum(
                (Decimal(str(t.get("value_usd", 0))) for t in chain.tokens),
                Decimal("0"),
            )
            protocol_value = sum(
                (Decimal(str(p.get("value_usd", 0))) for p in chain.protocols),
                Decimal("0"),
            )
            chain.total_value_usd = token_value + protocol_value

        return PortfolioSnapshot(
            address=address,
            total_value_usd=current_value,
            chains=chains,
            timestamp=datetime.utcnow(),
        )

    async def get_full_metrics(
        self,
        address: str,
        time_range: TimeRange = TimeRange.ONE_MONTH,
        chain_ids: list[str] | None = None,
    ) -> PortfolioMetrics:
        """Get complete portfolio metrics (tokens + protocols).

        Combines:
        - /tokens/metrics
        - /protocols/metrics

        Args:
            address: Wallet address
            time_range: Period for metrics
            chain_ids: Optional list of chain IDs to filter

        Returns:
            Complete portfolio metrics
        """
        # Fetch all data in parallel
        tokens_task = self.get_tokens_metrics(address, time_range, chain_ids)
        protocols_task = self.get_protocols_metrics(address, time_range, chain_ids)

        tokens_metrics, protocols_metrics = await asyncio.gather(
            tokens_task,
            protocols_task,
        )

        # Calculate total profit
        total_profit = sum(
            (t.absolute_profit_usd for t in tokens_metrics),
            Decimal("0"),
        ) + sum(
            (p.absolute_profit_usd for p in protocols_metrics),
            Decimal("0"),
        )

        # Calculate weighted ROI
        total_value = sum(
            (t.current_value_usd for t in tokens_metrics),
            Decimal("0"),
        ) + sum(
            (p.current_value_usd for p in protocols_metrics),
            Decimal("0"),
        )

        if total_value > 0:
            total_roi = (total_profit / total_value) * 100
        else:
            total_roi = Decimal("0")

        return PortfolioMetrics(
            address=address,
            time_range=time_range,
            total_profit_usd=total_profit,
            total_roi_percentage=total_roi,
            protocols=protocols_metrics,
            tokens=tokens_metrics,
            timestamp=datetime.utcnow(),
        )

    async def close(self) -> None:
        """Close HTTP client and cleanup resources."""
        if self._client:
            await self._client.aclose()
            self._client = None
            log.debug("portfolio.client_closed")
