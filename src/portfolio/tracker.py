"""Portfolio tracking service with periodic updates and caching.

Provides real-time monitoring of portfolio positions across multiple wallets
and chains with configurable update intervals.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import structlog

from .oneinch_client import (
    OneInchPortfolioClient,
    PortfolioMetrics,
    PortfolioSnapshot,
    TimeRange,
)

log = structlog.get_logger()


@dataclass
class WalletConfig:
    """Configuration for a tracked wallet."""

    address: str
    name: str
    chains: Optional[list[str]] = None  # None = all chains
    enabled: bool = True


@dataclass
class PortfolioCache:
    """Cached portfolio data with timestamp."""

    snapshot: Optional[PortfolioSnapshot] = None
    metrics_1d: Optional[PortfolioMetrics] = None
    metrics_1w: Optional[PortfolioMetrics] = None
    metrics_1m: Optional[PortfolioMetrics] = None
    last_snapshot_update: Optional[datetime] = None
    last_metrics_update: Optional[datetime] = None
    update_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None


@dataclass
class PortfolioTracker:
    """Tracks portfolio positions with periodic updates.

    Features:
    - Multi-wallet support
    - Configurable update intervals
    - Automatic retry on errors
    - In-memory caching
    - Performance tracking
    """

    api_key: str
    wallets: list[WalletConfig] = field(default_factory=list)
    snapshot_interval: float = 60.0  # seconds
    metrics_interval: float = 300.0  # seconds (5 min)
    cache_ttl: float = 3600.0  # seconds (1 hour)
    enabled: bool = True

    _client: Optional[OneInchPortfolioClient] = field(default=None, init=False, repr=False)
    _cache: dict[str, PortfolioCache] = field(default_factory=dict, init=False, repr=False)
    _stop: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)
    _tasks: list[asyncio.Task] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize portfolio client."""
        self._client = OneInchPortfolioClient(
            api_key=self.api_key,
            timeout=15.0,
            max_retries=3,
        )

        # Initialize cache for each wallet
        for wallet in self.wallets:
            self._cache[wallet.address] = PortfolioCache()

        log.info(
            "portfolio_tracker.initialized",
            wallet_count=len(self.wallets),
            snapshot_interval=self.snapshot_interval,
            metrics_interval=self.metrics_interval,
        )

    async def start(self) -> None:
        """Start periodic portfolio tracking."""
        if not self.enabled:
            log.info("portfolio_tracker.disabled")
            return

        if not self.wallets:
            log.warning("portfolio_tracker.no_wallets_configured")
            return

        try:
            # Create tracking tasks for each wallet
            for wallet in self.wallets:
                if wallet.enabled:
                    snapshot_task = asyncio.create_task(
                        self._snapshot_loop(wallet),
                        name=f"portfolio_snapshot_{wallet.name}",
                    )
                    metrics_task = asyncio.create_task(
                        self._metrics_loop(wallet),
                        name=f"portfolio_metrics_{wallet.name}",
                    )

                    self._tasks.extend([snapshot_task, metrics_task])

            log.info(
                "portfolio_tracker.started",
                active_wallets=len([w for w in self.wallets if w.enabled]),
            )

            # Wait for stop signal
            await self._stop.wait()

        except asyncio.CancelledError:
            log.info("portfolio_tracker.cancelled")
        finally:
            await self.cleanup()

    async def stop(self) -> None:
        """Stop portfolio tracking gracefully."""
        log.info("portfolio_tracker.stopping")
        self._stop.set()

        # Cancel all tracking tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()

    async def cleanup(self) -> None:
        """Cleanup resources."""
        if self._client:
            await self._client.close()
            self._client = None

    async def _snapshot_loop(self, wallet: WalletConfig) -> None:
        """Periodic snapshot updates for a wallet."""
        while not self._stop.is_set():
            try:
                await self._update_snapshot(wallet)

                # Wait for next update
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.snapshot_interval,
                )
            except asyncio.TimeoutError:
                # Expected timeout, continue loop
                continue
            except asyncio.CancelledError:
                log.debug("portfolio_tracker.snapshot_loop_cancelled", wallet=wallet.name)
                break
            except Exception as e:
                log.exception(
                    "portfolio_tracker.snapshot_loop_error",
                    wallet=wallet.name,
                    error=str(e)[:200],
                )
                # Continue after error with backoff
                await asyncio.sleep(30.0)

    async def _metrics_loop(self, wallet: WalletConfig) -> None:
        """Periodic metrics updates for a wallet."""
        while not self._stop.is_set():
            try:
                await self._update_metrics(wallet)

                # Wait for next update
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.metrics_interval,
                )
            except asyncio.TimeoutError:
                # Expected timeout, continue loop
                continue
            except asyncio.CancelledError:
                log.debug("portfolio_tracker.metrics_loop_cancelled", wallet=wallet.name)
                break
            except Exception as e:
                log.exception(
                    "portfolio_tracker.metrics_loop_error",
                    wallet=wallet.name,
                    error=str(e)[:200],
                )
                # Continue after error with backoff
                await asyncio.sleep(60.0)

    async def _update_snapshot(self, wallet: WalletConfig) -> None:
        """Update portfolio snapshot for a wallet."""
        if not self._client:
            return

        cache = self._cache[wallet.address]

        try:
            log.debug("portfolio_tracker.updating_snapshot", wallet=wallet.name)

            snapshot = await self._client.get_full_snapshot(
                address=wallet.address,
                chain_ids=wallet.chains,
            )

            cache.snapshot = snapshot
            cache.last_snapshot_update = datetime.utcnow()
            cache.update_count += 1

            log.info(
                "portfolio_tracker.snapshot_updated",
                wallet=wallet.name,
                total_value_usd=float(snapshot.total_value_usd),
                chains=len(snapshot.chains),
            )

        except Exception as e:
            cache.error_count += 1
            cache.last_error = str(e)[:200]

            log.warning(
                "portfolio_tracker.snapshot_update_failed",
                wallet=wallet.name,
                error=cache.last_error,
                error_count=cache.error_count,
            )

    async def _update_metrics(self, wallet: WalletConfig) -> None:
        """Update portfolio metrics for a wallet."""
        if not self._client:
            return

        cache = self._cache[wallet.address]

        try:
            log.debug("portfolio_tracker.updating_metrics", wallet=wallet.name)

            # Fetch metrics for multiple time ranges in parallel
            metrics_1d_task = self._client.get_full_metrics(
                address=wallet.address,
                time_range=TimeRange.ONE_DAY,
                chain_ids=wallet.chains,
            )
            metrics_1w_task = self._client.get_full_metrics(
                address=wallet.address,
                time_range=TimeRange.ONE_WEEK,
                chain_ids=wallet.chains,
            )
            metrics_1m_task = self._client.get_full_metrics(
                address=wallet.address,
                time_range=TimeRange.ONE_MONTH,
                chain_ids=wallet.chains,
            )

            metrics_1d, metrics_1w, metrics_1m = await asyncio.gather(
                metrics_1d_task,
                metrics_1w_task,
                metrics_1m_task,
            )

            cache.metrics_1d = metrics_1d
            cache.metrics_1w = metrics_1w
            cache.metrics_1m = metrics_1m
            cache.last_metrics_update = datetime.utcnow()

            log.info(
                "portfolio_tracker.metrics_updated",
                wallet=wallet.name,
                profit_1d_usd=float(metrics_1d.total_profit_usd),
                roi_1d_pct=float(metrics_1d.total_roi_percentage),
                profit_1m_usd=float(metrics_1m.total_profit_usd),
                roi_1m_pct=float(metrics_1m.total_roi_percentage),
            )

        except Exception as e:
            cache.error_count += 1
            cache.last_error = str(e)[:200]

            log.warning(
                "portfolio_tracker.metrics_update_failed",
                wallet=wallet.name,
                error=cache.last_error,
                error_count=cache.error_count,
            )

    # ========== Query Methods ==========

    def get_cached_snapshot(self, address: str) -> Optional[PortfolioSnapshot]:
        """Get cached snapshot for a wallet address.

        Args:
            address: Wallet address

        Returns:
            Cached snapshot or None if not available/stale
        """
        cache = self._cache.get(address)
        if not cache or not cache.snapshot:
            return None

        # Check if cache is stale
        if cache.last_snapshot_update:
            age = (datetime.utcnow() - cache.last_snapshot_update).total_seconds()
            if age > self.cache_ttl:
                log.debug("portfolio_tracker.snapshot_cache_stale", address=address, age=age)
                return None

        return cache.snapshot

    def get_cached_metrics(
        self,
        address: str,
        time_range: TimeRange = TimeRange.ONE_MONTH,
    ) -> Optional[PortfolioMetrics]:
        """Get cached metrics for a wallet address.

        Args:
            address: Wallet address
            time_range: Metrics time range

        Returns:
            Cached metrics or None if not available/stale
        """
        cache = self._cache.get(address)
        if not cache:
            return None

        # Check if cache is stale
        if cache.last_metrics_update:
            age = (datetime.utcnow() - cache.last_metrics_update).total_seconds()
            if age > self.cache_ttl:
                log.debug("portfolio_tracker.metrics_cache_stale", address=address, age=age)
                return None

        # Return metrics for requested time range
        if time_range == TimeRange.ONE_DAY:
            return cache.metrics_1d
        elif time_range == TimeRange.ONE_WEEK:
            return cache.metrics_1w
        elif time_range == TimeRange.ONE_MONTH:
            return cache.metrics_1m

        return None

    def get_all_snapshots(self) -> dict[str, PortfolioSnapshot]:
        """Get all cached snapshots across all wallets.

        Returns:
            Dict mapping address to snapshot
        """
        snapshots = {}
        for address, cache in self._cache.items():
            snapshot = self.get_cached_snapshot(address)
            if snapshot:
                snapshots[address] = snapshot

        return snapshots

    def get_total_portfolio_value(self) -> Decimal:
        """Get total value across all tracked wallets.

        Returns:
            Total portfolio value in USD
        """
        total = Decimal("0")
        for snapshot in self.get_all_snapshots().values():
            total += snapshot.total_value_usd

        return total

    def get_health_status(self) -> dict[str, Any]:
        """Get health status of portfolio tracker.

        Returns:
            Health metrics for monitoring
        """
        wallet_statuses = []

        for wallet in self.wallets:
            cache = self._cache.get(wallet.address, PortfolioCache())

            last_snapshot_age = None
            if cache.last_snapshot_update:
                last_snapshot_age = (
                    datetime.utcnow() - cache.last_snapshot_update
                ).total_seconds()

            last_metrics_age = None
            if cache.last_metrics_update:
                last_metrics_age = (
                    datetime.utcnow() - cache.last_metrics_update
                ).total_seconds()

            wallet_statuses.append({
                "address": wallet.address,
                "name": wallet.name,
                "enabled": wallet.enabled,
                "has_snapshot": cache.snapshot is not None,
                "has_metrics": cache.metrics_1m is not None,
                "last_snapshot_age_seconds": last_snapshot_age,
                "last_metrics_age_seconds": last_metrics_age,
                "update_count": cache.update_count,
                "error_count": cache.error_count,
                "last_error": cache.last_error,
            })

        return {
            "enabled": self.enabled,
            "wallet_count": len(self.wallets),
            "active_wallet_count": len([w for w in self.wallets if w.enabled]),
            "total_portfolio_value_usd": float(self.get_total_portfolio_value()),
            "wallets": wallet_statuses,
        }


def create_portfolio_tracker_from_env() -> Optional[PortfolioTracker]:
    """Create portfolio tracker from environment variables.

    Environment variables:
        ONEINCH_API_KEY: 1inch API key (required)
        PORTFOLIO_WALLETS: Comma-separated wallet addresses
        PORTFOLIO_WALLET_NAMES: Comma-separated wallet names (optional)
        PORTFOLIO_ENABLED: Enable/disable tracking (default: true)
        PORTFOLIO_SNAPSHOT_INTERVAL: Snapshot update interval in seconds (default: 60)
        PORTFOLIO_METRICS_INTERVAL: Metrics update interval in seconds (default: 300)

    Returns:
        Configured PortfolioTracker or None if not configured
    """
    api_key = os.getenv("ONEINCH_API_KEY") or os.getenv("ONEINCH_TOKEN")
    if not api_key:
        log.warning("portfolio_tracker.no_api_key_configured")
        return None

    wallet_addresses = os.getenv("PORTFOLIO_WALLETS", "")
    if not wallet_addresses:
        log.info("portfolio_tracker.no_wallets_configured")
        return None

    # Parse wallet addresses
    addresses = [addr.strip() for addr in wallet_addresses.split(",") if addr.strip()]

    # Parse optional wallet names
    wallet_names_str = os.getenv("PORTFOLIO_WALLET_NAMES", "")
    names = [name.strip() for name in wallet_names_str.split(",") if name.strip()]

    # Create wallet configs
    wallets = []
    for i, address in enumerate(addresses):
        name = names[i] if i < len(names) else f"wallet_{i + 1}"
        wallets.append(
            WalletConfig(
                address=address,
                name=name,
                enabled=True,
            )
        )

    # Parse configuration
    enabled = os.getenv("PORTFOLIO_ENABLED", "true").lower() in ("true", "1", "yes")
    snapshot_interval = float(os.getenv("PORTFOLIO_SNAPSHOT_INTERVAL", "60"))
    metrics_interval = float(os.getenv("PORTFOLIO_METRICS_INTERVAL", "300"))

    return PortfolioTracker(
        api_key=api_key,
        wallets=wallets,
        snapshot_interval=snapshot_interval,
        metrics_interval=metrics_interval,
        enabled=enabled,
    )
