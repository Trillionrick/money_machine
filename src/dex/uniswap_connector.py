"""High-level Uniswap connector combining subgraph insights and on-chain execution."""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

import structlog

from src.dex.config import CHAIN_TO_SUBGRAPH_SLUG, Chain, UniswapConfig
from src.dex.subgraph_client import UniswapSubgraphClient
from src.dex.web3_connector import UniswapWeb3Connector
from src.dex.onchain_pool_discovery import OnChainPoolDiscovery

logger = structlog.get_logger()

# Native ETH address used by some protocols
NATIVE_ETH_ADDRESS = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

# WETH addresses by chain
WETH_ADDRESSES = {
    Chain.ETHEREUM: "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    Chain.POLYGON: "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
    Chain.ARBITRUM: "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
    Chain.OPTIMISM: "0x4200000000000000000000000000000000000006",
    Chain.BASE: "0x4200000000000000000000000000000000000006",
}


class UniswapConnector:
    """Unified Uniswap client for quoting and executing swaps."""

    def __init__(self, config: UniswapConfig, chain: Chain = Chain.ETHEREUM):
        self.config = config
        self.chain = chain

        chain_slug = CHAIN_TO_SUBGRAPH_SLUG.get(chain)
        if chain_slug is None:
            msg = f"Unsupported chain for Uniswap connector: {chain}"
            raise ValueError(msg)

        # Initialize subgraph client (will use on-chain fallback if API key is missing)
        api_key = config.thegraph_api_key.get_secret_value() if config.thegraph_api_key else ""
        self.subgraph = UniswapSubgraphClient(
            api_key=api_key,
            chain_slug=chain_slug,
        )

        rpc_url = config.get_rpc_url(chain)
        router_address = config.router_addresses.get(chain.value)
        if router_address is None:
            msg = f"Router address missing for chain {chain}"
            raise ValueError(msg)

        private_key = config.private_key.get_secret_value() if config.private_key else None
        relay_urls = os.getenv("PRIVATE_RELAY_URLS", "")
        private_relays = [u.strip() for u in relay_urls.split(",") if u.strip()]
        single_relay = os.getenv("PRIVATE_RELAY_URL")
        if single_relay:
            private_relays.append(single_relay.strip())
        private_relay_timeout = int(os.getenv("PRIVATE_RELAY_TIMEOUT", "20"))
        private_relay_cancel = os.getenv("PRIVATE_RELAY_CANCEL", "false").lower() == "true"
        private_relay_tip_bump_pct = float(os.getenv("PRIVATE_RELAY_TIP_BUMP_PCT", "15"))
        self.web3 = UniswapWeb3Connector(
            rpc_url=rpc_url,
            router_address=router_address,
            private_key=private_key,
            private_relays=private_relays,
            private_relay_timeout=private_relay_timeout,
            enable_private_cancel=private_relay_cancel,
            private_relay_tip_bump_pct=private_relay_tip_bump_pct,
        )

        # On-chain fallback for when subgraph is unavailable
        factory_address = config.factory_addresses.get(chain.value)
        if factory_address:
            self.onchain_discovery = OnChainPoolDiscovery(
                self.web3.w3, factory_address
            )
        else:
            self.onchain_discovery = None

    def _normalize_token_address(self, token_address: str) -> str:
        """Convert native ETH address to WETH for the current chain.

        Uniswap V3 doesn't have pools with native ETH, only WETH.
        This method ensures we always query with WETH address.

        Args:
            token_address: Token address (may be native ETH)

        Returns:
            Normalized address (WETH if input was native ETH)
        """
        if token_address.lower() == NATIVE_ETH_ADDRESS.lower():
            weth = WETH_ADDRESSES.get(self.chain)
            if weth is None:
                msg = f"WETH address not configured for chain {self.chain}"
                raise ValueError(msg)
            logger.debug(
                "uniswap_connector.normalized_eth_to_weth",
                chain=self.chain.value,
                weth_address=weth,
            )
            return weth
        return token_address

    async def get_quote(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        fee_tier: int = 3000,
        token_in_decimals: int = 18,
        token_out_decimals: int = 18,
    ) -> dict[str, Any]:
        """Get swap quote with liquidity and price impact context.

        Falls back to 1inch API if The Graph subgraph fails (e.g., payment required).
        """
        # Normalize addresses (convert native ETH to WETH)
        token_in = self._normalize_token_address(token_in)
        token_out = self._normalize_token_address(token_out)

        try:
            pool = await self._get_pool(token_in, token_out, fee_tier)
        except Exception as e:
            # Pool discovery failed - fall back to 1inch API
            error_msg = str(e)
            logger.warning(
                "uniswap_connector.pool_discovery_failed_using_1inch_fallback",
                chain=self.chain.value,
                error=error_msg[:100],
                token_in=token_in[-8:],
                token_out=token_out[-8:],
            )
            return await self._get_quote_from_1inch(
                token_in, token_out, amount_in, token_in_decimals, token_out_decimals
            )

        token_in_is_token0 = pool["token0"]["id"].lower() == token_in.lower()
        # Uniswap subgraph price definitions:
        # - token0Price = amount of token0 you get per 1 token1
        # - token1Price = amount of token1 you get per 1 token0
        # For a swap token_in → token_out:
        # - If token_in is token0, we get token1 out, so use token1Price
        # - If token_in is token1, we get token0 out, so use token0Price
        # (This is inverted from what you might expect!)
        price = Decimal(pool["token1Price"] if token_in_is_token0 else pool["token0Price"])
        expected_output = amount_in * price

        logger.debug(
            "uniswap_connector.quote_calculation",
            chain=self.chain.value,
            token_in=token_in[-6:],
            token_out=token_out[-6:],
            token0=pool["token0"]["symbol"],
            token1=pool["token1"]["symbol"],
            token0_price=str(pool["token0Price"]),
            token1_price=str(pool["token1Price"]),
            token_in_is_token0=token_in_is_token0,
            selected_price=str(price),
            amount_in=str(amount_in),
            expected_output=str(expected_output),
        )

        liquidity = Decimal(pool["liquidity"])
        pool_value_usd = Decimal(pool["totalValueLockedUSD"])
        volume_usd = Decimal(pool["volumeUSD"])
        decimals_in = int(
            pool["token0"]["decimals"] if token_in_is_token0 else pool["token1"]["decimals"]
        )
        decimals_out = int(
            pool["token1"]["decimals"] if token_in_is_token0 else pool["token0"]["decimals"]
        )

        # Get recent swap data if available (gracefully degrade if subgraph unavailable)
        try:
            recent_swaps = await self.subgraph.get_token_swaps(token_in, limit=10)
        except Exception as e:
            logger.debug(
                "uniswap_connector.swap_history_unavailable",
                error=str(e),
                token_in=token_in,
            )
            recent_swaps = []

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
        # Normalize addresses (convert native ETH to WETH)
        # Note: get_quote will also normalize, but we do it here for clarity
        token_in = self._normalize_token_address(token_in)
        token_out = self._normalize_token_address(token_out)

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

    async def _get_pool(self, token0: str, token1: str, fee: int) -> dict[str, Any]:
        """Get pool info, with on-chain fallback if subgraph fails.

        Tries multiple fee tiers (500, 3000, 10000) to find the most liquid pool.
        """
        # Try requested fee tier first via subgraph
        try:
            pool = await self.subgraph.get_pool_by_tokens(token0, token1, fee)
            if pool is not None:
                return pool
        except Exception as e:
            logger.warning(
                "uniswap_connector.subgraph_failed_trying_onchain",
                error=str(e),
                token0=token0,
                token1=token1,
                fee_tier=fee,
            )

        # Fallback to on-chain discovery - try multiple fee tiers
        if self.onchain_discovery:
            logger.info(
                "uniswap_connector.using_onchain_fallback",
                token0=token0,
                token1=token1,
                requested_fee=fee,
            )
            # Try multiple fee tiers (None = try all common tiers: 500, 3000, 10000)
            pool_address = await self.onchain_discovery.find_pool(token0, token1, fee_tier=None)
            if pool_address:
                pool_state = await self.onchain_discovery.get_pool_state(pool_address)
                logger.info(
                    "uniswap_connector.found_pool_onchain",
                    pool=pool_address,
                    actual_fee=pool_state["fee_tier"],
                    liquidity=str(pool_state["liquidity"]),
                )
                # Convert on-chain format to subgraph-like format
                return {
                    "id": pool_address,
                    "token0": {
                        "id": pool_state["token0"],
                        "symbol": pool_state["token0_symbol"],
                        "decimals": pool_state["token0_decimals"],
                    },
                    "token1": {
                        "id": pool_state["token1"],
                        "symbol": pool_state["token1_symbol"],
                        "decimals": pool_state["token1_decimals"],
                    },
                    "feeTier": pool_state["fee_tier"],
                    "liquidity": str(pool_state["liquidity"]),
                    "token0Price": str(pool_state["token0_price"]),
                    "token1Price": str(pool_state["token1_price"]),
                    "totalValueLockedUSD": "0",  # Not available on-chain
                    "volumeUSD": "0",  # Not available on-chain
                }

        msg = f"No pool found for pair ({token0}, {token1}) - tried all fee tiers"
        raise ValueError(msg)

    async def _get_quote_from_1inch(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        token_in_decimals: int,
        token_out_decimals: int,
    ) -> dict[str, Any]:
        """Get quote from 1inch API as fallback when The Graph fails."""
        from src.dex.oneinch_fallback import OneInchQuoter

        quoter = OneInchQuoter()
        result = await quoter.get_quote(
            chain_id=self.chain.value,
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            token_in_decimals=token_in_decimals,
            token_out_decimals=token_out_decimals,
        )

        if result is None:
            msg = f"1inch fallback failed for pair ({token_in}, {token_out})"
            raise ValueError(msg)

        # Add missing fields that the original quote would have
        result["pool_address"] = "1inch_aggregator"
        result["pool_liquidity_tokens"] = None
        result["pool_value_usd"] = None
        result["recent_volume_usd"] = None
        result["estimated_price_impact_pct"] = Decimal("0.5")  # Conservative estimate
        result["token_in_is_token0"] = None
        result["decimals_in"] = token_in_decimals
        result["decimals_out"] = token_out_decimals
        result["swaps_sample"] = []

        return result

    @staticmethod
    def _estimate_price_impact(amount_in: Decimal, pool_liquidity: Decimal) -> Decimal:
        if pool_liquidity == 0:
            return Decimal("100.0")

        trade_size_ratio = amount_in / pool_liquidity
        price_impact = trade_size_ratio / (Decimal("1") + trade_size_ratio)
        return price_impact * Decimal("100")
