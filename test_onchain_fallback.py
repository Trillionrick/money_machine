#!/usr/bin/env python3
"""Test on-chain pool discovery fallback."""

import asyncio
from decimal import Decimal
from src.dex.config import UniswapConfig, Chain
from src.dex.uniswap_connector import UniswapConnector

async def test_onchain_fallback():
    """Test that on-chain fallback works when subgraph fails."""
    config = UniswapConfig()

    # Create connector for Ethereum
    print("Creating Uniswap connector...")
    connector = UniswapConnector(config, chain=Chain.ETHEREUM)

    # Test getting a quote for WETH/USDC
    weth = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
    usdc = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

    print("\nTesting WETH/USDC quote (will use on-chain fallback if subgraph fails)...")
    try:
        quote = await connector.get_quote(
            token_in=weth,
            token_out=usdc,
            amount_in=Decimal("1.0"),  # 1 WETH
            fee_tier=500,  # 0.05% fee
        )

        print(f"\n✅ SUCCESS!")
        print(f"   Input: 1 WETH")
        print(f"   Expected output: {quote['expected_output']} USDC")
        print(f"   Price impact: {quote.get('price_impact_bps', 'N/A')} bps")
        print(f"   Pool: {quote.get('pool_address', 'N/A')}")

        return True

    except Exception as e:
        print(f"\n❌ FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_onchain_fallback())
    exit(0 if success else 1)
