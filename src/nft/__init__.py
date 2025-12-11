"""NFT integration module for OpenSea and other marketplaces."""

from .opensea_client import NFTMetadata, NFTCollection, OpenSeaClient, get_wallet_nfts

__all__ = [
    "NFTMetadata",
    "NFTCollection",
    "OpenSeaClient",
    "get_wallet_nfts",
]
