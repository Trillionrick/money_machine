"""Async GraphQL client for querying Uniswap V3 subgraphs."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

from src.dex.config import SUBGRAPH_ENDPOINTS

logger = structlog.get_logger()


class UniswapSubgraphClient:
    """Async GraphQL client for Uniswap subgraph queries.

    This client uses a lock to ensure thread-safe concurrent access to the
    shared GraphQL client, preventing TransportAlreadyConnected errors.
    """

    def __init__(self, api_key: str, chain_slug: str = "mainnet", version: str = "v3"):
        endpoint_key = f"{version}_{chain_slug}"
        try:
            endpoint_url = SUBGRAPH_ENDPOINTS[endpoint_key].format(api_key=api_key)
        except KeyError as exc:
            msg = f"Unsupported subgraph target: {endpoint_key}"
            raise ValueError(msg) from exc

        transport = AIOHTTPTransport(url=endpoint_url)
        self.client = Client(transport=transport, fetch_schema_from_transport=False)
        self._lock = asyncio.Lock()

    async def get_pool_data(self, pool_address: str) -> dict[str, Any]:
        """Return pool-level stats including liquidity and prices."""
        query = gql(
            """
            query GetPool($poolAddress: ID!) {
                pool(id: $poolAddress) {
                    id
                    token0 { id symbol decimals }
                    token1 { id symbol decimals }
                    feeTier
                    liquidity
                    sqrtPrice
                    token0Price
                    token1Price
                    volumeUSD
                    txCount
                    totalValueLockedToken0
                    totalValueLockedToken1
                    totalValueLockedUSD
                }
            }
        """
        )

        async with self._lock:
            result = await self.client.execute_async(
                query, variable_values={"poolAddress": pool_address.lower()}
            )
        return result["pool"]

    async def get_pool_by_tokens(
        self, token_a: str, token_b: str, fee_tier: int
    ) -> dict[str, Any] | None:
        """Find a pool for a token pair and fee tier."""
        query = gql(
            """
            query GetPoolByTokens($tokens: [String!]!, $feeTier: Int!) {
                pools(
                    first: 1,
                    orderBy: totalValueLockedUSD,
                    orderDirection: desc,
                    where: {
                        token0_in: $tokens,
                        token1_in: $tokens,
                        feeTier: $feeTier
                    }
                ) {
                    id
                    token0 { id symbol decimals }
                    token1 { id symbol decimals }
                    feeTier
                    liquidity
                    token0Price
                    token1Price
                    totalValueLockedUSD
                    volumeUSD
                }
            }
        """
        )

        tokens = [token_a.lower(), token_b.lower()]
        async with self._lock:
            result = await self.client.execute_async(
                query,
                variable_values={"tokens": tokens, "feeTier": fee_tier},
            )
        pools = result.get("pools") or []
        return pools[0] if pools else None

    async def get_token_price_usd(self, token_address: str) -> float:
        """Get token price in USD using derived ETH price."""
        query = gql(
            """
            query GetTokenPrice($tokenAddress: ID!) {
                token(id: $tokenAddress) {
                    id
                    symbol
                    derivedETH
                }
                bundle(id: "1") {
                    ethPriceUSD
                }
            }
        """
        )

        async with self._lock:
            result = await self.client.execute_async(
                query, variable_values={"tokenAddress": token_address.lower()}
            )

        token = result["token"]
        eth_price_usd = float(result["bundle"]["ethPriceUSD"])
        derived_eth = float(token["derivedETH"])

        return derived_eth * eth_price_usd

    async def get_top_pools(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return top pools by TVL."""
        query = gql(
            """
            query GetTopPools($limit: Int!) {
                pools(
                    first: $limit,
                    orderBy: totalValueLockedUSD,
                    orderDirection: desc
                ) {
                    id
                    token0 { symbol }
                    token1 { symbol }
                    feeTier
                    totalValueLockedUSD
                    volumeUSD
                    token0Price
                    token1Price
                }
            }
        """
        )

        async with self._lock:
            result = await self.client.execute_async(
                query, variable_values={"limit": limit}
            )
        return result["pools"]

    async def get_token_swaps(
        self, token_address: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Return recent swaps for a token (order flow proxy)."""
        query = gql(
            """
            query GetSwaps($token: String!, $limit: Int!) {
                swaps(
                    first: $limit,
                    orderBy: timestamp,
                    orderDirection: desc,
                    where: {
                        or: [
                            {token0: $token},
                            {token1: $token}
                        ]
                    }
                ) {
                    id
                    timestamp
                    amount0
                    amount1
                    amountUSD
                    sqrtPriceX96
                    tick
                    sender
                    recipient
                }
            }
        """
        )

        async with self._lock:
            result = await self.client.execute_async(
                query, variable_values={"token": token_address.lower(), "limit": limit}
            )
        return result["swaps"]
