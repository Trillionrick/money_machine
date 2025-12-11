"""Configuration and chain metadata for Uniswap connectivity."""

from __future__ import annotations

from enum import IntEnum

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Chain(IntEnum):
    """Supported EVM chains for Uniswap V3."""

    ETHEREUM = 1
    POLYGON = 137
    ARBITRUM = 42161
    OPTIMISM = 10
    BASE = 8453
    BSC = 56
    AVALANCHE = 43114


CHAIN_TO_SUBGRAPH_SLUG: dict[Chain, str] = {
    Chain.ETHEREUM: "mainnet",
    Chain.POLYGON: "polygon",
    Chain.ARBITRUM: "arbitrum",
    Chain.OPTIMISM: "optimism",
    Chain.BASE: "base",
}

DEFAULT_FACTORY_ADDRESSES: dict[int, str] = {
    1: "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    137: "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    42161: "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    10: "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    8453: "0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
}

DEFAULT_ROUTER_ADDRESSES: dict[int, str] = {
    1: "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
    137: "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
    42161: "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
    10: "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
    8453: "0x2626664c2603336E57B271c5C0b26F421741e481",
}

# Human-readable router map keyed by chain name for scripts/CLI tools.
ROUTER_ADDRESSES: dict[str, dict[str, str]] = {
    "ethereum": {"uniswap_v3": DEFAULT_ROUTER_ADDRESSES[1]},
    "polygon": {"uniswap_v3": DEFAULT_ROUTER_ADDRESSES[137]},
    "arbitrum": {"uniswap_v3": DEFAULT_ROUTER_ADDRESSES[42161]},
    "optimism": {"uniswap_v3": DEFAULT_ROUTER_ADDRESSES[10]},
    "base": {"uniswap_v3": DEFAULT_ROUTER_ADDRESSES[8453]},
}

# Minimal token map for scripts; extend as needed per chain.
TOKEN_ADDRESSES: dict[str, dict[str, str]] = {
    "ethereum": {
        "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    },
    "polygon": {
        "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
        "USDC": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
    },
    "arbitrum": {
        "WETH": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        "USDC": "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8",
    },
    "optimism": {
        "WETH": "0x4200000000000000000000000000000000000006",
        "USDC": "0x7F5c764cBc14f9669B88837ca1490cCa17c31607",
    },
    "base": {
        "WETH": "0x4200000000000000000000000000000000000006",
        "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54b2C6d5E6",
    },
}

SUBGRAPH_ENDPOINTS: dict[str, str] = {
    # TheGraph decentralized network - 100k free queries/month per API key
    # Get free key at: https://thegraph.com/studio/
    "v3_mainnet": (
        "https://gateway-arbitrum.network.thegraph.com/api/{api_key}/subgraphs/id/"
        "5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV"
    ),
    "v3_polygon": (
        "https://gateway-arbitrum.network.thegraph.com/api/{api_key}/subgraphs/id/"
        "3hCPRGf4z88VC5rsBKU5AA9FBBq5nF3jbKJG7VZCbhjm"
    ),
    "v3_arbitrum": (
        "https://gateway-arbitrum.network.thegraph.com/api/{api_key}/subgraphs/id/"
        "FbCGRftH4a3yZugY7TnbYgPJVEv2LvMT6oF1fxPe9aJM"
    ),
    "v3_optimism": (
        "https://gateway-arbitrum.network.thegraph.com/api/{api_key}/subgraphs/id/"
        "Cghf4LfVqPiFw6fp6Y5X5Ubc8UpmUhSfJL82zwiBFLaj"
    ),
    "v3_base": (
        "https://gateway-arbitrum.network.thegraph.com/api/{api_key}/subgraphs/id/"
        "43Hwfi3dJSoN8Qhp5SLeKYEZbkKp2EmizGso61TvG7sK"
    ),
}


class UniswapConfig(BaseSettings):
    """Typed configuration for Uniswap connectivity."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,  # Allow using both field names and aliases in constructor
    )

    ethereum_rpc: SecretStr | None = Field(default=None, alias="ETHEREUM_RPC_URL")
    polygon_rpc: SecretStr | None = Field(default=None, alias="POLYGON_RPC_URL")
    arbitrum_rpc: SecretStr | None = Field(default=None, alias="ARBITRUM_RPC_URL")
    optimism_rpc: SecretStr | None = Field(default=None, alias="OPTIMISM_RPC_URL")
    base_rpc: SecretStr | None = Field(default=None, alias="BASE_RPC_URL")

    thegraph_api_key: SecretStr | None = Field(default=None, alias="THEGRAPH_API_KEY")
    private_key: SecretStr | None = Field(default=None, alias="WALLET_PRIVATE_KEY")

    factory_addresses: dict[int, str] = Field(
        default_factory=lambda: DEFAULT_FACTORY_ADDRESSES.copy()
    )
    router_addresses: dict[int, str] = Field(
        default_factory=lambda: DEFAULT_ROUTER_ADDRESSES.copy()
    )

    def get_rpc_url(self, chain: Chain) -> str:
        """Return RPC URL for the requested chain."""
        attr = f"{chain.name.lower()}_rpc"
        rpc = getattr(self, attr, None)
        if rpc is None:
            msg = f"RPC URL missing for chain {chain.name} ({chain.value})"
            raise ValueError(msg)
        return rpc.get_secret_value()
