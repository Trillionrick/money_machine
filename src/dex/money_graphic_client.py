"""Async client for the project-owned `money_graphic` subgraph."""

from __future__ import annotations

from typing import Any

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class MoneyGraphicSettings(BaseSettings):
    """Settings for the money_graphic subgraph endpoint."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    subgraph_url: str | None = Field(
        default=None,
        alias="MONEY_GRAPHIC_SUBGRAPH_URL"
    )


class MoneyGraphicClient:
    """Lightweight async GraphQL client to consume the money_graphic subgraph."""

    def __init__(
        self,
        endpoint: str | None = None,
        settings: MoneyGraphicSettings | None = None,
    ):
        try:
            resolved_settings = settings or MoneyGraphicSettings()
        except ValidationError as e:
            raise ValueError(
                "Failed to load MoneyGraphicSettings. Ensure MONEY_GRAPHIC_SUBGRAPH_URL "
                "is set in your .env file or pass an endpoint directly."
            ) from e

        self.endpoint = endpoint or resolved_settings.subgraph_url

        if not self.endpoint:
            raise ValueError(
                "No subgraph endpoint provided. Either set MONEY_GRAPHIC_SUBGRAPH_URL "
                "in your .env file or pass endpoint parameter to MoneyGraphicClient."
            )

        transport = AIOHTTPTransport(url=self.endpoint)
        self.client = Client(transport=transport, fetch_schema_from_transport=False)

    async def get_token_meta(self, token_address: str) -> dict[str, Any]:
        """Fetch token-level metadata and supply/holder counts."""
        query = gql(
            """
            query TokenMeta($id: Bytes!) {
              token(id: $id) {
                id
                name
                symbol
                decimals
                totalSupply
                holderCount
                lastUpdatedBlock
                lastUpdatedTimestamp
              }
            }
            """
        )
        result = await self.client.execute_async(
            query, variable_values={"id": token_address.lower()}
        )
        return result["token"]

    async def get_daily_snapshots(
        self, token_address: str, limit: int = 30
    ) -> list[dict[str, Any]]:
        """Return recent daily snapshots for a token, newest first."""
        query = gql(
            """
            query Daily($token: Bytes!, $limit: Int!) {
              dailySnapshots(
                where: { token: $token }
                first: $limit
                orderBy: date
                orderDirection: desc
              ) {
                id
                date
                transferCount
                volume
                holderCount
                totalSupply
                blockNumber
                blockTimestamp
              }
            }
            """
        )
        result = await self.client.execute_async(
            query,
            variable_values={"token": token_address.lower(), "limit": limit},
        )
        return result["dailySnapshots"]

    async def get_top_holders(
        self,
        token_address: str,
        limit: int = 20,
        min_balance: int = 0,
    ) -> list[dict[str, Any]]:
        """Return top holders by balance for a token."""
        query = gql(
            """
            query TopHolders($token: Bytes!, $limit: Int!, $minBalance: BigInt!) {
              holderBalances(
                where: { token: $token, balance_gt: $minBalance }
                first: $limit
                orderBy: balance
                orderDirection: desc
              ) {
                id
                holder
                balance
                lastUpdatedBlock
                lastUpdatedTimestamp
              }
            }
            """
        )

        result = await self.client.execute_async(
            query,
            variable_values={
                "token": token_address.lower(),
                "limit": limit,
                "minBalance": str(min_balance),
            },
        )
        return result["holderBalances"]

    async def get_vault(self, vault_address: str) -> dict[str, Any]:
        """Fetch staking vault metadata and totals."""
        query = gql(
            """
            query Vault($id: Bytes!) {
              vault(id: $id) {
                id
                stakeToken
                rewardToken
                owner
                totalStaked
                rewardRate
                periodFinish
                lastUpdate
                lastUpdatedBlock
                lastUpdatedTimestamp
              }
            }
            """
        )
        result = await self.client.execute_async(
            query, variable_values={"id": vault_address.lower()}
        )
        return result["vault"]

    async def get_recent_stakes(
        self, vault_address: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Return recent stake actions for a vault."""
        query = gql(
            """
            query Stakes($id: Bytes!, $limit: Int!) {
              stakeActions(
                where: { vault: $id }
                first: $limit
                orderBy: blockTimestamp
                orderDirection: desc
              ) {
                id
                user
                amount
                blockNumber
                blockTimestamp
                transactionHash
              }
            }
            """
        )
        result = await self.client.execute_async(
            query, variable_values={"id": vault_address.lower(), "limit": limit}
        )
        return result["stakeActions"]

    async def get_recent_rewards(
        self, vault_address: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Return recent reward payouts for a vault."""
        query = gql(
            """
            query Rewards($id: Bytes!, $limit: Int!) {
              rewardPaidActions(
                where: { vault: $id }
                first: $limit
                orderBy: blockTimestamp
                orderDirection: desc
              ) {
                id
                user
                reward
                blockNumber
                blockTimestamp
                transactionHash
              }
            }
            """
        )
        result = await self.client.execute_async(
            query, variable_values={"id": vault_address.lower(), "limit": limit}
        )
        return result["rewardPaidActions"]
