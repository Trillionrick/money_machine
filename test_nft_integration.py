"""
Test script for OpenSea NFT integration.

Run this to verify your NFT collection loads correctly.
"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from src.nft.opensea_client import OpenSeaClient, get_wallet_nfts


async def test_wallet_nfts():
    """Test fetching NFTs from your wallet."""
    print("\n" + "=" * 70)
    print("🖼️  TESTING OPENSEA NFT INTEGRATION")
    print("=" * 70)

    wallet = os.getenv("METAMASK_WALLET_ADDRESS", "0x31fcd43a349ada21f3c5df51d66f399be518a912")
    api_key = os.getenv("OPENSEA_API_KEY")

    if not api_key:
        print("\n⚠️  WARNING: OPENSEA_API_KEY not set in .env")
        print("   API calls will be rate-limited and may fail")
        print("   Add your API key to .env: OPENSEA_API_KEY=your_key_here\n")

    print(f"\nWallet: {wallet}")
    print(f"Chain: Ethereum")
    print(f"API Key: {'✓ Configured' if api_key else '✗ Not set'}")
    print("\nFetching NFTs...\n")

    try:
        nfts = await get_wallet_nfts(wallet, chain="ethereum", api_key=api_key)

        if nfts:
            print(f"✓ Found {len(nfts)} NFTs\n")
            print("Your NFT Collection:")
            print("-" * 70)

            for i, nft in enumerate(nfts[:10], 1):  # Show first 10
                print(f"\n{i}. {nft.name or f'#{nft.identifier}'}")
                print(f"   Collection: {nft.collection}")
                print(f"   Standard: {nft.token_standard.upper()}")
                print(f"   Contract: {nft.contract[:10]}...{nft.contract[-8:]}")
                if nft.opensea_url:
                    print(f"   View: {nft.opensea_url}")

            if len(nfts) > 10:
                print(f"\n... and {len(nfts) - 10} more NFTs")

        else:
            print("ℹ️  No NFTs found for this wallet on Ethereum")
            print("\nPossible reasons:")
            print("  • Wallet doesn't own any NFTs")
            print("  • NFTs are on a different chain (try polygon)")
            print("  • API key is invalid")

        print("\n" + "=" * 70)
        print("✓ Test complete!")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("  1. Check your OPENSEA_API_KEY in .env")
        print("  2. Verify wallet address is correct")
        print("  3. Ensure internet connection is working")
        print("  4. Check OpenSea API status: https://status.opensea.io/")


async def test_collection():
    """Test fetching a popular collection."""
    print("\n" + "=" * 70)
    print("🎨 TESTING COLLECTION FETCH")
    print("=" * 70)

    api_key = os.getenv("OPENSEA_API_KEY")
    client = OpenSeaClient(api_key=api_key)

    collection_slug = "boredapeyachtclub"
    print(f"\nFetching: {collection_slug}\n")

    try:
        collection = await client.get_collection(collection_slug)

        if collection:
            print("✓ Collection found!\n")
            print(f"Name: {collection.name}")
            print(f"Slug: {collection.slug}")
            if collection.floor_price_eth:
                print(f"Floor Price: {collection.floor_price_eth:.4f} ETH")
            if collection.total_supply:
                print(f"Total Supply: {collection.total_supply:,}")
            if collection.owner_count:
                print(f"Owners: {collection.owner_count:,}")
        else:
            print("⚠️  Collection not found")

    except Exception as e:
        print(f"❌ Error: {e}")

    print("\n" + "=" * 70)


async def main():
    """Run all tests."""
    await test_wallet_nfts()
    # await test_collection()  # Uncomment to test collection fetch


if __name__ == "__main__":
    asyncio.run(main())
