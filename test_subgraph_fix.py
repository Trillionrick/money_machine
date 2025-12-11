#!/usr/bin/env python3
"""Quick test to verify subgraph connectivity after switching to decentralized endpoints."""

import asyncio
from src.dex.config import UniswapConfig, Chain
from src.dex.subgraph_client import UniswapSubgraphClient

async def test_subgraph():
    """Test querying the free decentralized subgraph."""
    config = UniswapConfig()

    # Test Ethereum mainnet
    print("Testing Ethereum mainnet subgraph...")
    api_key = config.thegraph_api_key.get_secret_value() if config.thegraph_api_key else ""
    client = UniswapSubgraphClient(
        api_key=api_key,
        chain_slug="mainnet",
    )

    try:
        # Query for WETH/USDC pool (0.05% fee tier)
        weth = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
        usdc = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
        fee_tier = 500  # 0.05%

        pool = await client.get_pool_by_tokens(weth, usdc, fee_tier)

        if pool:
            print(f"✅ SUCCESS: Found pool {pool['id']}")
            print(f"   TVL: ${float(pool['totalValueLockedUSD']):,.2f}")
            print(f"   {pool['token0']['symbol']}/{pool['token1']['symbol']}")
            print(f"   Price: {pool['token0Price']}")
        else:
            print("⚠️  No pool found (unexpected)")

    except Exception as e:
        print(f"❌ FAILED: {type(e).__name__}: {e}")
        return False

    print("\n✅ Subgraph connectivity restored!")
    return True

if __name__ == "__main__":
    asyncio.run(test_subgraph())
