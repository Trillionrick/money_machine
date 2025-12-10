"""Diagnostic script to test why the arbitrage scanner isn't finding opportunities."""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from src.brokers.price_fetcher import CEXPriceFetcher
from src.dex.uniswap_connector import UniswapConnector
from src.dex.config import UniswapConfig, Chain
from pydantic import SecretStr


async def test_cex_prices():
    """Test CEX price fetching."""
    print("=" * 70)
    print("Testing CEX Price Fetching")
    print("=" * 70)

    fetcher = CEXPriceFetcher(
        binance_enabled=True,
        alpaca_enabled=False,
        kraken_enabled=True,
    )

    test_symbols = [
        "ETH/USDC",
        "WETH/USDC",
        "BTC/USDT",
        "LINK/USDC",
    ]

    for symbol in test_symbols:
        try:
            price = await fetcher.get_price(symbol)
            print(f"✅ {symbol:12} = ${price:,.2f}")
        except Exception as e:
            print(f"❌ {symbol:12} = ERROR: {e}")

    print()


async def test_dex_quotes():
    """Test DEX quote fetching."""
    print("=" * 70)
    print("Testing DEX Quote Fetching")
    print("=" * 70)

    eth_rpc = os.getenv("ETH_RPC_URL") or os.getenv("ETHEREUM_RPC_URL")
    private_key = os.getenv("PRIVATE_KEY") or os.getenv("WALLET_PRIVATE_KEY")
    thegraph_api_key = os.getenv("THEGRAPH_API_KEY")

    if not eth_rpc:
        print("❌ No Ethereum RPC URL configured")
        return

    if not thegraph_api_key:
        print("❌ No TheGraph API Key configured")
        return

    config = UniswapConfig(
        ETHEREUM_RPC_URL=SecretStr(eth_rpc.strip()),
        WALLET_PRIVATE_KEY=SecretStr(private_key.strip()) if private_key else None,
        THEGRAPH_API_KEY=SecretStr(thegraph_api_key.strip()),
    )

    try:
        dex = UniswapConnector(config, chain=Chain.ETHEREUM)
        print(f"✅ DEX connector initialized for Ethereum")

        # Test a simple ETH/USDC quote
        token_addresses = {
            "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        }

        try:
            from decimal import Decimal
            quote = await dex.get_quote(
                token_in=token_addresses["USDC"],
                token_out=token_addresses["WETH"],
                amount_in=Decimal("1000"),  # 1000 USDC
                token_in_decimals=6,  # USDC has 6 decimals
                token_out_decimals=18,  # WETH has 18 decimals
            )
            if quote:
                expected_out = quote["expected_output"]
                print(f"✅ DEX Quote: 1000 USDC → {expected_out} WETH")
                print(f"   Price: {float(expected_out) / 1000:.6f} WETH/USDC")
            else:
                print("❌ DEX quote returned None")
        except Exception as e:
            print(f"❌ DEX quote failed: {e}")
    except Exception as e:
        print(f"❌ DEX initialization failed: {e}")

    print()


async def test_arbitrage_edge():
    """Test if we can detect an arbitrage edge."""
    print("=" * 70)
    print("Testing Arbitrage Edge Detection")
    print("=" * 70)

    # Get CEX price
    fetcher = CEXPriceFetcher(binance_enabled=True, kraken_enabled=True)

    symbol = "ETH/USDC"
    cex_price = await fetcher.get_price(symbol)

    if not cex_price:
        print(f"❌ Failed to get CEX price for {symbol}")
        return

    print(f"CEX Price: ${cex_price:,.2f}")

    # Get DEX price
    eth_rpc = os.getenv("ETH_RPC_URL") or os.getenv("ETHEREUM_RPC_URL")
    private_key = os.getenv("PRIVATE_KEY") or os.getenv("WALLET_PRIVATE_KEY")
    thegraph_api_key = os.getenv("THEGRAPH_API_KEY")

    if not eth_rpc:
        print("❌ No Ethereum RPC URL configured")
        return

    if not thegraph_api_key:
        print("❌ No TheGraph API Key configured")
        return

    config = UniswapConfig(
        ETHEREUM_RPC_URL=SecretStr(eth_rpc.strip()),
        WALLET_PRIVATE_KEY=SecretStr(private_key.strip()) if private_key else None,
        THEGRAPH_API_KEY=SecretStr(thegraph_api_key.strip()),
    )

    try:
        from decimal import Decimal
        dex = UniswapConnector(config, chain=Chain.ETHEREUM)

        token_addresses = {
            "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        }

        # Get quote for 1 WETH
        quote = await dex.get_quote(
            token_in=token_addresses["WETH"],
            token_out=token_addresses["USDC"],
            amount_in=Decimal("1"),  # 1 WETH
            token_in_decimals=18,  # WETH has 18 decimals
            token_out_decimals=6,  # USDC has 6 decimals
        )

        if quote:
            # USDC has 6 decimals - but expected_output is already in token units
            dex_price = float(quote["expected_output"])
            print(f"DEX Price: ${dex_price:,.2f}")

            # Calculate edge
            edge_bps = ((dex_price - cex_price) / cex_price) * 10000
            print(f"\nEdge: {edge_bps:.2f} bps ({edge_bps/100:.2f}%)")

            min_edge = 25.0  # bps
            if abs(edge_bps) >= min_edge:
                print(f"✅ ARBITRAGE OPPORTUNITY FOUND! (threshold: {min_edge} bps)")
            else:
                print(f"❌ No arbitrage (edge below threshold of {min_edge} bps)")
        else:
            print("❌ Failed to get DEX quote")

    except Exception as e:
        print(f"❌ Error getting DEX quote: {e}")
        import traceback
        traceback.print_exc()

    print()


async def main():
    """Run all diagnostic tests."""
    print("\n")
    print("🔍 ARBITRAGE SCANNER DIAGNOSTICS")
    print("=" * 70)
    print()

    await test_cex_prices()
    await test_dex_quotes()
    await test_arbitrage_edge()

    print("=" * 70)
    print("Diagnostics complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
