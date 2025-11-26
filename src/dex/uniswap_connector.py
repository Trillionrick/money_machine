"""High-level Uniswap connector combining subgraph insights and on-chain execution."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict

import structlog

from src.dex.config import CHAIN_TO_SUBGRAPH_SLUG, Chain, UniswapConfig
from src.dex.subgraph_client import UniswapSubgraphClient
from src.dex.web3_connector import UniswapWeb3Connector

logger = structlog.get_logger()


class UniswapConnector:
    """Unified Uniswap client for quoting and executing swaps."""

    def __init__(self, config: UniswapConfig, chain: Chain = Chain.ETHEREUM):
        self.config = config
        self.chain = chain

        chain_slug = CHAIN_TO_SUBGRAPH_SLUG.get(chain)
        if chain_slug is None:
            msg = f"Unsupported chain for Uniswap connector: {chain}"
            raise ValueError(msg)

        self.subgraph = UniswapSubgraphClient(
            api_key=config.thegraph_api_key.get_secret_value(),
            chain_slug=chain_slug,
        )

        rpc_url = config.get_rpc_url(chain)
        router_address = config.router_addresses.get(chain.value)
        if router_address is None:
            msg = f"Router address missing for chain {chain}"
            raise ValueError(msg)

        private_key = config.private_key.get_secret_value() if config.private_key else None
        self.web3 = UniswapWeb3Connector(
            rpc_url=rpc_url,
            router_address=router_address,
            private_key=private_key,
        )

    async def get_quote(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        fee_tier: int = 3000,
    ) -> Dict[str, Any]:
        """Get swap quote with liquidity and price impact context."""
        pool = await self._get_pool(token_in, token_out, fee_tier)

        token_in_is_token0 = pool["token0"]["id"].lower() == token_in.lower()
        price = Decimal(pool["token0Price"] if token_in_is_token0 else pool["token1Price"])
        expected_output = amount_in * price

        liquidity = Decimal(pool["liquidity"])
        pool_value_usd = Decimal(pool["totalValueLockedUSD"])
        volume_usd = Decimal(pool["volumeUSD"])
        decimals_in = int(
            pool["token0"]["decimals"] if token_in_is_token0 else pool["token1"]["decimals"]
        )
        decimals_out = int(
            pool["token1"]["decimals"] if token_in_is_token0 else pool["token0"]["decimals"]
        )

        recent_swaps = await self.subgraph.get_token_swaps(token_in, limit=10)

        return {
            "expected_output": expected_output,
            "pool_address": pool["id"],
            "pool_liquidity_tokens": liquidity,
            "pool_value_usd": pool_value_usd,
            "recent_volume_usd": volume_usd,
            "estimated_price_impact_pct": self._estimate_price_impact(amount_in, liquidity),
            "token_in_is_token0": token_in_is_token0,
            "decimals_in": decimals_in,
            "decimals_out": decimals_out,
            "swaps_sample": recent_swaps,
        }

    async def execute_market_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        slippage_tolerance: Decimal = Decimal("0.005"),
        fee_tier: int = 3000,
    ) -> str:
        """Execute a market swap with slippage protection."""
        quote = await self.get_quote(token_in, token_out, amount_in, fee_tier)

        amount_out_min_tokens = quote["expected_output"] * (Decimal("1") - slippage_tolerance)
        amount_in_wei = int(amount_in * Decimal(10 ** quote["decimals_in"]))
        amount_out_min = int(amount_out_min_tokens * Decimal(10 ** quote["decimals_out"]))

        await self.web3.approve_token(
            token_address=token_in,
            spender_address=str(self.web3.router_address),
            amount=amount_in_wei,
        )

        tx_hash = await self.web3.execute_swap(
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in_wei,
            amount_out_min=amount_out_min,
            fee_tier=fee_tier,
        )

        return tx_hash

    async def _get_pool(self, token0: str, token1: str, fee: int) -> Dict[str, Any]:
        pool = await self.subgraph.get_pool_by_tokens(token0, token1, fee)
        if pool is None:
            msg = f"No pool found for pair ({token0}, {token1}) at fee tier {fee}"
            raise ValueError(msg)
        return pool

    @staticmethod
    def _estimate_price_impact(amount_in: Decimal, pool_liquidity: Decimal) -> Decimal:
        if pool_liquidity == 0:
            return Decimal("100.0")

        trade_size_ratio = amount_in / pool_liquidity
        price_impact = trade_size_ratio / (Decimal("1") + trade_size_ratio)
        return price_impact * Decimal("100")
