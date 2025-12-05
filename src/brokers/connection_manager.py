"""Unified connection manager for CEX and DEX connectors."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import Any

import structlog
from pydantic import ValidationError

from src.brokers.binance_adapter import BinanceAdapter
from src.brokers.credentials import BrokerCredentials
from src.brokers.kraken_adapter import KrakenAdapter
from src.brokers.oanda_adapter import OandaAdapter
from src.brokers.oanda_config import OandaConfig
from src.brokers.routing import DefaultRoutingPolicy, OrderRouter
from src.core.execution import OrderSeq
from src.dex import Chain, UniswapConfig, UniswapConnector

logger = structlog.get_logger()


class ConnectionManager:
    """Manage exchange connectors across CEX and DEX venues."""

    def __init__(self, credentials: BrokerCredentials, dex_config: UniswapConfig | None = None):
        self.creds = credentials
        self.connectors: dict[str, Any] = {}
        self.tasks: dict[str, asyncio.Task[Any]] = {}
        self.exit_stack = AsyncExitStack()
        self.dex_config = dex_config
        self.router: OrderRouter | None = None

    async def initialize(self) -> None:
        """Initialize configured connectors."""
        await self._init_cex()
        await self._init_dex()
        self._init_router()

    async def _init_cex(self) -> None:
        if self.creds.has_binance():
            self.connectors["binance"] = BinanceAdapter(
                api_key=self.creds.binance_api_key.get_secret_value(),
                api_secret=self.creds.binance_api_secret.get_secret_value(),
                testnet=self.creds.binance_testnet,
            )
        else:
            logger.info("connector.binance_skipped", reason="missing_credentials")

        if self.creds.has_kraken():
            self.connectors["kraken"] = KrakenAdapter(
                api_key=self.creds.kraken_api_key.get_secret_value(),  # type: ignore[union-attr]
                api_secret=self.creds.kraken_api_secret.get_secret_value(),  # type: ignore[union-attr]
            )
        else:
            logger.info("connector.kraken_skipped", reason="missing_credentials")

        try:
            oanda_config = OandaConfig.from_env()
            self.connectors["oanda"] = OandaAdapter(oanda_config)
        except Exception:
            logger.info("connector.oanda_skipped", reason="missing_or_invalid_config")

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

    def _init_router(self) -> None:
        """Initialize the routing engine using available connectors."""
        if not self.connectors:
            logger.warning("router.skipped", reason="no_connectors")
            return

        self.router = OrderRouter(
            connectors=self.connectors,
            policy=DefaultRoutingPolicy(max_venue_share=0.40),
        )
        logger.info(
            "router.initialized",
            connectors=list(self.connectors.keys()),
            policy="default_forex_oanda_crypto_priority",
        )

    async def route_and_submit(self, orders: OrderSeq) -> None:
        """Route orders through the router if configured."""
        if self.router is None:
            msg = "Router not initialized; call initialize() first"
            raise RuntimeError(msg)
        await self.router.submit_orders(orders)
