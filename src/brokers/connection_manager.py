"""Unified connection manager for CEX and DEX connectors."""

from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from typing import Any

import structlog
from pydantic import SecretStr, ValidationError

# from src.brokers.binance_adapter import BinanceAdapter  # Disabled: geo-blocked in US
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
        # Binance disabled: geo-blocked in US
        # if self.creds.has_binance():
        #     api_key = self.creds.binance_api_key
        #     api_secret = self.creds.binance_api_secret
        #     if api_key is None or api_secret is None:
        #         logger.warning("connector.binance_skipped", reason="missing_credentials")
        #     else:
        #         try:
        #             self.connectors["binance"] = BinanceAdapter(
        #                 api_key=api_key.get_secret_value(),
        #                 api_secret=api_secret.get_secret_value(),
        #                 testnet=self.creds.binance_testnet,
        #             )
        #             logger.info("connector.binance_initialized")
        #         except Exception as exc:
        #             logger.warning(
        #                 "connector.binance_failed",
        #                 error=str(exc),
        #                 hint="Binance may be geo-blocked in your region",
        #             )
        # else:
        #     logger.info("connector.binance_skipped", reason="missing_credentials")

        if self.creds.has_kraken():
            api_key = self.creds.kraken_api_key
            api_secret = self.creds.kraken_api_secret
            if api_key is None or api_secret is None:
                logger.warning("connector.kraken_skipped", reason="missing_credentials")
            else:
                try:
                    self.connectors["kraken"] = KrakenAdapter(
                        api_key=api_key.get_secret_value(),
                        api_secret=api_secret.get_secret_value(),
                    )
                    logger.info("connector.kraken_initialized")
                except Exception as exc:
                    logger.warning(
                        "connector.kraken_failed",
                        error=str(exc),
                    )
        else:
            logger.info("connector.kraken_skipped", reason="missing_credentials")

        try:
            oanda_config = OandaConfig.from_env()
            # Prefer calling is_configured() if it exists; otherwise fall back to checking
            # the expected credential fields (OANDA_API_TOKEN and OANDA_ACCOUNT_ID).
            method = getattr(oanda_config, "is_configured", None)
            if callable(method):
                configured = method()
            else:
                configured = bool(
                    getattr(oanda_config, "oanda_api_token", None)
                    and getattr(oanda_config, "oanda_account_id", None)
                )

            if not configured:
                logger.info(
                    "connector.oanda_skipped",
                    reason="credentials_not_set",
                    hint="Set OANDA_API_TOKEN and OANDA_ACCOUNT_ID in .env",
                )
            else:
                self.connectors["oanda"] = OandaAdapter(oanda_config)
                logger.info("connector.oanda_initialized", environment=oanda_config.oanda_environment.value)
        except ValidationError as exc:
            logger.warning(
                "connector.oanda_config_invalid",
                errors=exc.errors(),
            )
        except Exception as exc:
            logger.warning(
                "connector.oanda_failed",
                error=str(exc),
            )

    async def _init_dex(self) -> None:
        if self.dex_config is None:
            thegraph_key = os.getenv("THEGRAPH_API_KEY")
            if not thegraph_key:
                logger.info(
                    "connector.uniswap_skipped",
                    reason="missing_THEGRAPH_API_KEY",
                )
                return

            try:
                self.dex_config = UniswapConfig(THEGRAPH_API_KEY=SecretStr(thegraph_key))
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
