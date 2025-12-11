"""
OpenSea API v2 client for fetching NFT collection data.

Uses 2025 OpenSea REST API standards with proper type hints.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import structlog
from httpx import AsyncClient, HTTPStatusError

log = structlog.get_logger()


@dataclass
class NFTMetadata:
    """Represents a single NFT."""

    identifier: str
    collection: str
    contract: str
    token_standard: str
    name: str | None
    description: str | None
    image_url: str | None
    opensea_url: str | None
    traits: list[dict[str, Any]]
    floor_price_eth: float | None = None
    last_sale_price_eth: float | None = None


@dataclass
class NFTCollection:
    """Represents an NFT collection summary."""

    name: str
    slug: str
    image_url: str | None
    floor_price_eth: float | None
    total_supply: int | None
    owner_count: int | None


class OpenSeaClient:
    """
    Client for OpenSea API v2.

    Supports fetching NFTs by wallet address across multiple chains.
    """

    BASE_URL = "https://api.opensea.io/api/v2"
    TESTNET_BASE_URL = "https://testnets-api.opensea.io/api/v2"

    def __init__(self, api_key: str | None = None, use_testnet: bool = False):
        """
        Initialize OpenSea client.

        Args:
            api_key: OpenSea API key (optional for low rate limits)
            use_testnet: Use testnet API endpoint
        """
        self.api_key = api_key or os.getenv("OPENSEA_API_KEY", "")
        self.base_url = self.TESTNET_BASE_URL if use_testnet else self.BASE_URL

        self.headers = {
            "Accept": "application/json",
        }

        if self.api_key:
            self.headers["x-api-key"] = self.api_key

    async def get_nfts_by_account(
        self,
        wallet_address: str,
        chain: str = "ethereum",
        limit: int = 50,
    ) -> list[NFTMetadata]:
        """
        Fetch all NFTs owned by a wallet address.

        Args:
            wallet_address: Ethereum wallet address
            chain: Blockchain name (ethereum, polygon, arbitrum, base, etc.)
            limit: Max NFTs to return (default 50)

        Returns:
            List of NFT metadata objects
        """
        endpoint = f"{self.base_url}/chain/{chain}/account/{wallet_address}/nfts"

        params = {
            "limit": str(limit),
        }

        try:
            async with AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    endpoint,
                    headers=self.headers,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

                nfts = []
                for nft_data in data.get("nfts", []):
                    nfts.append(self._parse_nft(nft_data))

                log.info(
                    "opensea.nfts_fetched",
                    wallet=wallet_address[:10] + "...",
                    chain=chain,
                    count=len(nfts),
                )

                return nfts

        except HTTPStatusError as e:
            log.error(
                "opensea.api_error",
                status=e.response.status_code,
                error=str(e),
            )
            return []
        except Exception as e:
            log.exception("opensea.fetch_failed", error=str(e))
            return []

    async def get_collection(self, collection_slug: str) -> NFTCollection | None:
        """
        Fetch collection details by slug.

        Args:
            collection_slug: OpenSea collection slug (e.g., 'boredapeyachtclub')

        Returns:
            Collection metadata or None if not found
        """
        endpoint = f"{self.base_url}/collections/{collection_slug}"

        try:
            async with AsyncClient(timeout=30.0) as client:
                response = await client.get(endpoint, headers=self.headers)
                response.raise_for_status()
                data = response.json()

                return self._parse_collection(data)

        except HTTPStatusError as e:
            log.error(
                "opensea.collection_error",
                status=e.response.status_code,
                slug=collection_slug,
            )
            return None
        except Exception as e:
            log.exception("opensea.collection_fetch_failed", error=str(e))
            return None

    def _parse_nft(self, nft_data: dict[str, Any]) -> NFTMetadata:
        """Parse NFT data from API response."""
        identifier = nft_data.get("identifier", "")
        collection_slug = nft_data.get("collection", "")
        contract = nft_data.get("contract", "")

        # OpenSea URL format: https://opensea.io/assets/{chain}/{contract}/{identifier}
        opensea_url = f"https://opensea.io/assets/ethereum/{contract}/{identifier}"

        return NFTMetadata(
            identifier=identifier,
            collection=collection_slug,
            contract=contract,
            token_standard=nft_data.get("token_standard", "erc721"),
            name=nft_data.get("name"),
            description=nft_data.get("description"),
            image_url=nft_data.get("image_url"),
            opensea_url=opensea_url,
            traits=nft_data.get("traits", []),
        )

    def _parse_collection(self, collection_data: dict[str, Any]) -> NFTCollection:
        """Parse collection data from API response."""
        stats = collection_data.get("stats", {})

        # Floor price is in ETH
        floor_price = stats.get("floor_price")

        return NFTCollection(
            name=collection_data.get("name", ""),
            slug=collection_data.get("collection", ""),
            image_url=collection_data.get("image_url"),
            floor_price_eth=float(floor_price) if floor_price else None,
            total_supply=stats.get("total_supply"),
            owner_count=stats.get("num_owners"),
        )


async def get_wallet_nfts(
    wallet_address: str,
    chain: str = "ethereum",
    api_key: str | None = None,
) -> list[NFTMetadata]:
    """
    Convenience function to fetch NFTs for a wallet.

    Args:
        wallet_address: Ethereum wallet address
        chain: Blockchain name
        api_key: Optional OpenSea API key

    Returns:
        List of NFTs owned by the wallet
    """
    client = OpenSeaClient(api_key=api_key)
    return await client.get_nfts_by_account(wallet_address, chain)
