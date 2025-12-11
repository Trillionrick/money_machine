"""On-chain Uniswap V3 pool discovery without subgraph dependency."""

from __future__ import annotations

from typing import Any
import structlog
from web3 import AsyncWeb3
from web3.contract.async_contract import AsyncContract

logger = structlog.get_logger()

# Uniswap V3 Factory ABI (minimal - just getPool function)
FACTORY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]

# ERC20 ABI (minimal - for decimals)
ERC20_ABI = [
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "symbol",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# Uniswap V3 Pool ABI (minimal - for reading pool state)
POOL_ABI = [
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "fee",
        "outputs": [{"internalType": "uint24", "name": "", "type": "uint24"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

# Common fee tiers (basis points)
FEE_TIERS = [100, 500, 3000, 10000]  # 0.01%, 0.05%, 0.3%, 1%


class OnChainPoolDiscovery:
    """Discover and query Uniswap V3 pools directly on-chain without subgraph."""

    def __init__(self, w3: AsyncWeb3, factory_address: str):
        self.w3 = w3
        self.factory_address = w3.to_checksum_address(factory_address)
        self.factory: AsyncContract = w3.eth.contract(
            address=self.factory_address, abi=FACTORY_ABI
        )

    async def find_pool(
        self, token_a: str, token_b: str, fee_tier: int | None = None
    ) -> str | None:
        """Find pool address for token pair, trying common fee tiers if not specified."""
        token_a = self.w3.to_checksum_address(token_a)
        token_b = self.w3.to_checksum_address(token_b)

        tiers_to_try = [fee_tier] if fee_tier else FEE_TIERS

        for tier in tiers_to_try:
            try:
                pool_address = await self.factory.functions.getPool(
                    token_a, token_b, tier
                ).call()

                # Zero address means pool doesn't exist
                if pool_address != "0x0000000000000000000000000000000000000000":
                    logger.debug(
                        "onchain_pool_discovery.found_pool",
                        token_a=token_a,
                        token_b=token_b,
                        fee_tier=tier,
                        pool=pool_address,
                    )
                    return pool_address

            except Exception as e:
                logger.warning(
                    "onchain_pool_discovery.query_failed",
                    token_a=token_a,
                    token_b=token_b,
                    fee_tier=tier,
                    error=str(e),
                )
                continue

        logger.info(
            "onchain_pool_discovery.no_pool_found",
            token_a=token_a,
            token_b=token_b,
            tiers_tried=tiers_to_try,
        )
        return None

    async def get_pool_state(self, pool_address: str) -> dict[str, Any]:
        """Get current pool state (price, liquidity, decimals, etc.)."""
        pool_address = self.w3.to_checksum_address(pool_address)
        pool: AsyncContract = self.w3.eth.contract(address=pool_address, abi=POOL_ABI)

        # Fetch all pool data in parallel
        token0_addr, token1_addr, fee, liquidity, slot0 = await asyncio.gather(
            pool.functions.token0().call(),
            pool.functions.token1().call(),
            pool.functions.fee().call(),
            pool.functions.liquidity().call(),
            pool.functions.slot0().call(),
        )

        # Get token metadata (decimals and symbols)
        token0_contract: AsyncContract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(token0_addr), abi=ERC20_ABI
        )
        token1_contract: AsyncContract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(token1_addr), abi=ERC20_ABI
        )

        (token0_decimals, token0_symbol, token1_decimals, token1_symbol) = await asyncio.gather(
            token0_contract.functions.decimals().call(),
            token0_contract.functions.symbol().call(),
            token1_contract.functions.decimals().call(),
            token1_contract.functions.symbol().call(),
        )

        sqrt_price_x96 = slot0[0]
        tick = slot0[1]

        # Calculate human-readable price from sqrtPriceX96
        # price = (sqrtPriceX96 / 2^96) ^ 2
        price = (sqrt_price_x96 / (2**96)) ** 2

        return {
            "pool_address": pool_address,
            "token0": token0_addr,
            "token1": token1_addr,
            "token0_decimals": token0_decimals,
            "token1_decimals": token1_decimals,
            "token0_symbol": token0_symbol,
            "token1_symbol": token1_symbol,
            "fee_tier": fee,
            "liquidity": liquidity,
            "sqrt_price_x96": sqrt_price_x96,
            "tick": tick,
            "token0_price": price,  # token1 per token0
            "token1_price": 1 / price if price > 0 else 0,  # token0 per token1
        }

    async def get_quote_price(
        self, token_in: str, token_out: str, fee_tier: int | None = None
    ) -> float | None:
        """Get current market price for token pair."""
        pool_address = await self.find_pool(token_in, token_out, fee_tier)

        if not pool_address:
            return None

        pool_state = await self.get_pool_state(pool_address)

        # Determine which direction the quote is
        token_in = self.w3.to_checksum_address(token_in)
        token_out = self.w3.to_checksum_address(token_out)

        if token_in.lower() == pool_state["token0"].lower():
            # Buying token1 with token0
            return pool_state["token0_price"]
        else:
            # Buying token0 with token1
            return pool_state["token1_price"]


# Need to import asyncio at the top
import asyncio
