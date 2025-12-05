"""Dynamic gas price oracle with multiple fallback sources.

Fetches gas prices from multiple sources with automatic fallbacks:
1. Blocknative API
2. Etherscan/Polygonscan API
3. On-chain RPC
4. Hardcoded fallback (last resort)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
import time
from typing import Literal

import httpx
import structlog
from web3 import AsyncWeb3

log = structlog.get_logger()

Chain = Literal["ethereum", "polygon"]


@dataclass
class GasPrice:
    """Gas price in gwei with confidence level."""

    gwei: float
    source: str
    confidence: Literal["high", "medium", "low"]


class GasOracle:
    """Multi-source gas oracle with automatic fallbacks."""

    def __init__(
        self,
        *,
        ethereum_fallback_gwei: float = 50.0,
        polygon_fallback_gwei: float = 40.0,
        cache_ttl_seconds: float = 12.0,  # Ethereum block time
    ) -> None:
        """Initialize gas oracle.

        Args:
            ethereum_fallback_gwei: Final fallback for Ethereum
            polygon_fallback_gwei: Final fallback for Polygon
            cache_ttl_seconds: How long to cache prices
        """
        self.ethereum_fallback_gwei = ethereum_fallback_gwei
        self.polygon_fallback_gwei = polygon_fallback_gwei
        self.cache_ttl_seconds = cache_ttl_seconds

        # Cache: chain -> (price, timestamp)
        self._cache: dict[Chain, tuple[GasPrice, float]] = {}

        # API keys
        self.etherscan_api_key = os.getenv("ETHERSCAN_API_KEY")
        self.polygonscan_api_key = os.getenv("POLYGONSCAN_API_KEY")
        self.blocknative_api_key = os.getenv("BLOCKNATIVE_API_KEY")

    async def get_gas_price(
        self, chain: Chain, web3: AsyncWeb3 | None = None
    ) -> GasPrice:
        """Get current gas price for chain.

        Args:
            chain: Target chain
            web3: Optional web3 instance for RPC fallback

        Returns:
            GasPrice with source and confidence
        """
        # Check cache
        cached = self._get_cached(chain)
        if cached:
            return cached

        # Try multiple sources in order
        if chain == "ethereum":
            price = (
                await self._try_blocknative_ethereum()
                or await self._try_etherscan()
                or (await self._try_rpc(web3) if web3 else None)
                or GasPrice(
                    gwei=self.ethereum_fallback_gwei,
                    source="hardcoded_fallback",
                    confidence="low",
                )
            )
        else:  # polygon
            price = (
                await self._try_polygonscan()
                or (await self._try_rpc(web3) if web3 else None)
                or GasPrice(
                    gwei=self.polygon_fallback_gwei,
                    source="hardcoded_fallback",
                    confidence="low",
                )
            )

        # Cache result
        self._cache[chain] = (price, time.monotonic())

        if price.confidence == "low":
            log.warning(
                "gas_oracle.using_fallback",
                chain=chain,
                gwei=price.gwei,
                source=price.source,
            )
        else:
            log.debug(
                "gas_oracle.fetched",
                chain=chain,
                gwei=price.gwei,
                source=price.source,
                confidence=price.confidence,
            )

        return price

    def _get_cached(self, chain: Chain) -> GasPrice | None:
        """Get cached price if still valid."""
        if chain not in self._cache:
            return None

        price, timestamp = self._cache[chain]
        age = time.monotonic() - timestamp

        if age < self.cache_ttl_seconds:
            log.debug("gas_oracle.cache_hit", chain=chain, age_seconds=age)
            return price

        return None

    async def _try_blocknative_ethereum(self) -> GasPrice | None:
        """Try Blocknative gas estimator (Ethereum only)."""
        if not self.blocknative_api_key:
            return None

        try:
            url = "https://api.blocknative.com/gasprices/blockprices"
            headers = {"Authorization": self.blocknative_api_key}

            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

            # Get fast price (95th percentile)
            base_fee = data["blockPrices"][0]["baseFeePerGas"]
            priority_fee = data["blockPrices"][0]["estimatedPrices"][1][
                "maxPriorityFeePerGas"
            ]
            gas_price_gwei = base_fee + priority_fee

            return GasPrice(
                gwei=gas_price_gwei, source="blocknative", confidence="high"
            )

        except Exception as e:
            log.debug("gas_oracle.blocknative_failed", error=str(e))
            return None

    async def _try_etherscan(self) -> GasPrice | None:
        """Try Etherscan gas oracle (Ethereum)."""
        if not self.etherscan_api_key:
            return None

        try:
            url = "https://api.etherscan.io/api"
            params = {
                "module": "gastracker",
                "action": "gasoracle",
                "apikey": self.etherscan_api_key,
            }

            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

            if data["status"] != "1":
                return None

            # Use FastGasPrice
            gas_price_gwei = float(data["result"]["FastGasPrice"])

            return GasPrice(gwei=gas_price_gwei, source="etherscan", confidence="high")

        except Exception as e:
            log.debug("gas_oracle.etherscan_failed", error=str(e))
            return None

    async def _try_polygonscan(self) -> GasPrice | None:
        """Try Polygonscan gas oracle (Polygon)."""
        if not self.polygonscan_api_key:
            return None

        try:
            url = "https://api.polygonscan.com/api"
            params = {
                "module": "gastracker",
                "action": "gasoracle",
                "apikey": self.polygonscan_api_key,
            }

            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

            if data["status"] != "1":
                return None

            # Use FastGasPrice (or ProposeGasPrice as fallback)
            gas_price_gwei = float(
                data["result"].get("FastGasPrice")
                or data["result"].get("ProposeGasPrice")
                or "0"
            )

            if gas_price_gwei == 0:
                return None

            return GasPrice(
                gwei=gas_price_gwei, source="polygonscan", confidence="high"
            )

        except Exception as e:
            log.debug("gas_oracle.polygonscan_failed", error=str(e))
            return None

    async def _try_rpc(self, web3: AsyncWeb3) -> GasPrice | None:
        """Try on-chain RPC as fallback."""
        try:
            gas_price_wei = await web3.eth.gas_price
            gas_price_gwei = float(gas_price_wei) / 1e9

            return GasPrice(gwei=gas_price_gwei, source="rpc", confidence="medium")

        except Exception as e:
            log.debug("gas_oracle.rpc_failed", error=str(e))
            return None

    def clear_cache(self, chain: Chain | None = None) -> None:
        """Clear cache for specific chain or all chains."""
        if chain:
            self._cache.pop(chain, None)
        else:
            self._cache.clear()
