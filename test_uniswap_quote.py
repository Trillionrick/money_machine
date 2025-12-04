#!/usr/bin/env python3
"""Test Uniswap quote fetching to debug $0 issue."""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
from src.dex.uniswap_connector import UniswapConnector
from src.dex.config import UniswapConfig, Chain

load_dotenv()


async def test_quotes():
    """Test various token pair quotes."""
    config = UniswapConfig()

    # Test Ethereum WETH/USDC
    print("Testing Ethereum WETH/USDC...")
    uni_eth = UniswapConnector(config, Chain.ETHEREUM)

    weth = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
    usdc = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

    try:
        quote = await uni_eth.get_quote(weth, usdc, Decimal("1"), fee_tier=3000)
        print(f"Quote data: {quote}")
        print(f"Expected output: {quote.get('expected_output')}")
        print(f"Pool address: {quote.get('pool_address')}")
        print(f"Pool liquidity: {quote.get('pool_liquidity_tokens')}")
        print(f"Pool value USD: {quote.get('pool_value_usd')}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_quotes())
