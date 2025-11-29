"""Centralized price fetching from multiple CEX (Centralized Exchanges).

Fetches real-time prices from:
- Binance (crypto)
- Alpaca (US stocks)
- Other exchanges as needed

This provides the CEX side of the arbitrage equation.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Dict, Optional

import httpx
import structlog

from src.core.types import Price, Symbol

log = structlog.get_logger()


class CEXPriceFetcher:
    """Fetch real-time prices from centralized exchanges."""

    def __init__(
        self,
        binance_enabled: bool = True,
        alpaca_enabled: bool = False,
        kraken_enabled: bool = True,
    ):
        """Initialize price fetcher.

        Args:
            binance_enabled: Enable Binance price fetching
            alpaca_enabled: Enable Alpaca price fetching
            kraken_enabled: Enable Kraken price fetching (geo-friendly fallback)
        """
        self.binance_enabled = binance_enabled
        self.alpaca_enabled = alpaca_enabled
        self.kraken_enabled = kraken_enabled

        # Initialize clients
        self.binance_client: Optional[any] = None
        self.alpaca_client: Optional[any] = None
        self.kraken_client: Optional[httpx.AsyncClient] = None
        self.kraken_base_url = "https://api.kraken.com"

        # Price cache (symbol -> price)
        self._price_cache: Dict[Symbol, Price] = {}
        self._cache_timestamp: Dict[Symbol, float] = {}
        self._cache_ttl = 5.0  # Cache prices for 5 seconds

        if binance_enabled:
            self._init_binance()

        if alpaca_enabled:
            self._init_alpaca()

        if kraken_enabled:
            self._init_kraken()

        log.info(
            "price_fetcher.initialized",
            binance=binance_enabled,
            alpaca=alpaca_enabled,
            kraken=kraken_enabled,
        )

    def _init_binance(self):
        """Initialize Binance client (spot market)."""
        try:
            from binance.client import Client
            # Public client - no API keys needed for price data
            self.binance_client = Client()
            log.info("price_fetcher.binance_ready")
        except ImportError:
            log.warning(
                "price_fetcher.binance_unavailable",
                msg="Install with: pip install python-binance"
            )
            self.binance_enabled = False
        except Exception as e:
            log.warning(
                "price_fetcher.binance_blocked",
                msg=f"Binance unavailable: {str(e)[:100]}"
            )
            self.binance_enabled = False
            self.binance_client = None

    def _init_alpaca(self):
        """Initialize Alpaca client."""
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            # Public client for market data
            self.alpaca_client = StockHistoricalDataClient(api_key=None, secret_key=None)
            log.info("price_fetcher.alpaca_ready")
        except ImportError:
            log.warning(
                "price_fetcher.alpaca_unavailable",
                msg="Install with: pip install alpaca-py"
            )
            self.alpaca_enabled = False

    def _init_kraken(self):
        """Initialize Kraken HTTP client."""
        try:
            self.kraken_client = httpx.AsyncClient(timeout=10.0)
            log.info("price_fetcher.kraken_ready")
        except Exception as e:
            log.warning(
                "price_fetcher.kraken_unavailable",
                msg=f"Kraken client unavailable: {str(e)[:100]}"
            )
            self.kraken_enabled = False

    async def get_price(self, symbol: Symbol) -> Optional[Price]:
        """Get current price for a symbol from appropriate exchange.

        Args:
            symbol: Trading symbol (e.g., "BTC/USDT", "ETH/USDC", "AAPL")

        Returns:
            Current price or None if unavailable
        """
        # Check cache first
        import time
        now = time.time()
        if symbol in self._price_cache:
            cached_time = self._cache_timestamp.get(symbol, 0)
            if now - cached_time < self._cache_ttl:
                return self._price_cache[symbol]

        # Fetch fresh price
        price = await self._fetch_price(symbol)

        if price:
            self._price_cache[symbol] = price
            self._cache_timestamp[symbol] = now

        return price

    async def _fetch_price(self, symbol: Symbol) -> Optional[Price]:
        """Fetch price from appropriate exchange."""
        # Normalize symbol
        normalized = symbol.replace("_", "/").upper()

        # Determine which exchange to use
        if self._is_crypto_pair(normalized):
            if self.binance_enabled:
                price = await self._fetch_binance_price(normalized)
                if price is not None:
                    return price

            if self.kraken_enabled:
                price = await self._fetch_kraken_price(normalized)
                if price is not None:
                    return price

        if self.alpaca_enabled:
            return await self._fetch_alpaca_price(symbol)

        log.warning("price_fetcher.no_source", symbol=symbol)
        return None

    def _is_crypto_pair(self, symbol: str) -> bool:
        """Check if symbol is a crypto trading pair."""
        crypto_quotes = {"USDT", "USDC", "BUSD", "USD", "BTC", "ETH"}
        if "/" in symbol:
            base, quote = symbol.split("/", 1)
            return quote in crypto_quotes
        return False

    async def _fetch_binance_price(self, symbol: str) -> Optional[Price]:
        """Fetch price from Binance.

        Args:
            symbol: Normalized symbol (e.g., "BTC/USDT")
        """
        if not self.binance_client:
            return None

        try:
            # Convert symbol format (BTC/USDT -> BTCUSDT)
            binance_symbol = symbol.replace("/", "")

            # Get ticker price
            ticker = await asyncio.to_thread(
                self.binance_client.get_symbol_ticker,
                symbol=binance_symbol
            )

            price = float(ticker["price"])

            log.debug(
                "price_fetcher.binance_price",
                symbol=symbol,
                price=price,
            )

            return price

        except Exception as e:
            log.warning(
                "price_fetcher.binance_failed",
                symbol=symbol,
                error=str(e),
            )
            return None

    async def _fetch_alpaca_price(self, symbol: str) -> Optional[Price]:
        """Fetch price from Alpaca.

        Args:
            symbol: Stock symbol (e.g., "AAPL")
        """
        if not self.alpaca_client:
            return None

        try:
            # Get latest trade
            from alpaca.data.requests import StockLatestTradeRequest

            request = StockLatestTradeRequest(symbol_or_symbols=symbol)
            trade = await asyncio.to_thread(
                self.alpaca_client.get_stock_latest_trade,
                request
            )

            if symbol in trade:
                price = float(trade[symbol].price)

                log.debug(
                    "price_fetcher.alpaca_price",
                    symbol=symbol,
                    price=price,
                )

                return price

        except Exception as e:
            log.warning(
                "price_fetcher.alpaca_failed",
                symbol=symbol,
                error=str(e),
            )

        return None

    async def _fetch_kraken_price(self, symbol: str) -> Optional[Price]:
        """Fetch price from Kraken public API.

        Args:
            symbol: Normalized symbol (e.g., "BTC/USDT")
        """
        if not self.kraken_client:
            return None

        try:
            kraken_pair = self._to_kraken_pair(symbol)

            response = await self.kraken_client.get(
                f"{self.kraken_base_url}/0/public/Ticker",
                params={"pair": kraken_pair},
            )
            response.raise_for_status()
            data = response.json()

            if data.get("error"):
                log.warning(
                    "price_fetcher.kraken_failed",
                    symbol=symbol,
                    error="; ".join(data["error"]),
                )
                return None

            result = data.get("result") or {}
            if not result:
                log.warning("price_fetcher.kraken_failed", symbol=symbol, error="empty_result")
                return None

            ticker = next(iter(result.values()))
            price = float(ticker["c"][0])  # Last trade close price

            log.debug(
                "price_fetcher.kraken_price",
                symbol=symbol,
                price=price,
            )

            return price

        except Exception as e:
            log.warning(
                "price_fetcher.kraken_failed",
                symbol=symbol,
                error=str(e),
            )
            return None

    def _to_kraken_pair(self, symbol: str) -> str:
        """Convert symbol to Kraken pair format (best-effort)."""
        base, quote = symbol.split("/")

        # Kraken uses XBT instead of BTC, and ETH for WETH
        base = {
            "BTC": "XBT",
            "WETH": "ETH",
        }.get(base, base)

        # Keep stablecoin naming but normalize USD-like quotes
        quote = {
            "USDT": "USDT",
            "USDC": "USDC",
            "USD": "USD",
        }.get(quote, quote)

        return f"{base}{quote}"

    async def get_multiple_prices(
        self,
        symbols: list[Symbol]
    ) -> Dict[Symbol, Optional[Price]]:
        """Fetch prices for multiple symbols concurrently.

        Args:
            symbols: List of symbols to fetch

        Returns:
            Dictionary mapping symbols to prices
        """
        tasks = [self.get_price(symbol) for symbol in symbols]
        prices = await asyncio.gather(*tasks, return_exceptions=True)

        result = {}
        for symbol, price in zip(symbols, prices):
            if isinstance(price, Exception):
                log.error(
                    "price_fetcher.bulk_fetch_error",
                    symbol=symbol,
                    error=str(price),
                )
                result[symbol] = None
            else:
                result[symbol] = price

        return result


# Convenience function for simple usage
async def fetch_cex_price(symbol: Symbol) -> Optional[Price]:
    """Quick helper to fetch a single price.

    Example:
        >>> price = await fetch_cex_price("BTC/USDT")
        >>> print(f"BTC price: ${price}")
    """
    fetcher = CEXPriceFetcher()
    return await fetcher.get_price(symbol)
