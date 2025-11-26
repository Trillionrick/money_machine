"""Unified connection manager for CEX and DEX connectors."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import Any, Dict

import structlog
from pydantic import ValidationError

from src.brokers.binance_adapter import BinanceAdapter
from src.brokers.credentials import BrokerCredentials
from src.dex import Chain, UniswapConfig, UniswapConnector

logger = structlog.get_logger()


class ConnectionManager:
    """Manage exchange connectors across CEX and DEX venues."""

    def __init__(self, credentials: BrokerCredentials, dex_config: UniswapConfig | None = None):
        self.creds = credentials
        self.connectors: Dict[str, Any] = {}
        self.tasks: Dict[str, asyncio.Task[Any]] = {}
        self.exit_stack = AsyncExitStack()
        self.dex_config = dex_config

    async def initialize(self) -> None:
        """Initialize configured connectors."""
        await self._init_cex()
        await self._init_dex()

    async def _init_cex(self) -> None:
        if self.creds.has_binance():
            self.connectors["binance"] = BinanceAdapter(
                api_key=self.creds.binance_api_key.get_secret_value(),
                api_secret=self.creds.binance_api_secret.get_secret_value(),
                testnet=self.creds.binance_testnet,
            )
        else:
            logger.info("connector.binance_skipped", reason="missing_credentials")

    async def _init_dex(self) -> None:
        if self.dex_config is None:
            try:
                self.dex_config = UniswapConfig()
            except ValidationError as exc:
                logger.warning(
                    "connector.uniswap_config_invalid",
                    errors=exc.errors(),
                )
                return

        for chain in (Chain.ETHEREUM, Chain.ARBITRUM, Chain.BASE):
            try:
                connector = UniswapConnector(config=self.dex_config, chain=chain)
            except Exception:
                logger.exception("connector.uniswap_failed", chain=chain.name.lower())
                continue

            key = f"uniswap_{chain.name.lower()}"
            self.connectors[key] = connector

        logger.info(
            "connector.dex_initialized",
            chains=[k for k in self.connectors.keys() if k.startswith("uniswap_")],
        )
