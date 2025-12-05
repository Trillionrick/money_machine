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
        coingecko_enabled: bool = True,
    ):
        """Initialize price fetcher.

        Args:
            binance_enabled: Enable Binance price fetching
            alpaca_enabled: Enable Alpaca price fetching
            kraken_enabled: Enable Kraken price fetching (geo-friendly fallback)
            coingecko_enabled: Enable CoinGecko for altcoins/DeFi tokens
        """
        self.binance_enabled = binance_enabled
        self.alpaca_enabled = alpaca_enabled
        self.kraken_enabled = kraken_enabled
        self.coingecko_enabled = coingecko_enabled

        # Initialize clients
        self.binance_client: any | None = None
        self.alpaca_client: any | None = None
        self.kraken_client: httpx.AsyncClient | None = None
        self.coingecko_client: httpx.AsyncClient | None = None
        self.kraken_base_url = "https://api.kraken.com"
        self.coingecko_base_url = "https://api.coingecko.com/api/v3"

        # Price cache (symbol -> price)
        self._price_cache: dict[Symbol, Price] = {}
        self._cache_timestamp: dict[Symbol, float] = {}
        self._cache_ttl = 5.0  # Cache prices for 5 seconds

        # Rate limiting for CoinGecko (free tier: ~10-50 calls/min)
        self._coingecko_last_call = 0.0
        self._coingecko_min_interval = 1.2  # 1.2 seconds between calls

        if binance_enabled:
            self._init_binance()

        if alpaca_enabled:
            self._init_alpaca()

        if kraken_enabled:
            self._init_kraken()

        if coingecko_enabled:
            self._init_coingecko()

        log.info(
            "price_fetcher.initialized",
            binance=self.binance_enabled,
            alpaca=self.alpaca_enabled,
            kraken=self.kraken_enabled,
            coingecko=self.coingecko_enabled,
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

    def _init_coingecko(self):
        """Initialize CoinGecko HTTP client (no API key needed for free tier)."""
        try:
            self.coingecko_client = httpx.AsyncClient(timeout=10.0)
            log.info("price_fetcher.coingecko_ready")
        except Exception as e:
            log.warning(
                "price_fetcher.coingecko_unavailable",
                msg=f"CoinGecko client unavailable: {str(e)[:100]}"
            )
            self.coingecko_enabled = False

    async def get_price(self, symbol: Symbol) -> Price | None:
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

    async def _fetch_price(self, symbol: Symbol) -> Price | None:
        """Fetch price from appropriate exchange."""
        # Normalize symbol (but preserve original for special cases)
        original = symbol.replace("_", "/")
        normalized = original.upper()

        # Special handling for inverse pairs (e.g., ETH/stETH)
        # Calculate as ratio of two USD prices
        if "/" in normalized:
            base, quote = normalized.split("/", 1)

            # Check if this is an LST token paired with stablecoin
            lst_tokens = {"STETH", "RETH", "CBETH", "WSTETH"}
            stablecoins = {"USDC", "USDT", "DAI", "USDD"}

            if base in lst_tokens and quote in stablecoins:
                # Handle LST/stablecoin pairs (e.g., stETH/USDC)
                price = await self._fetch_inverse_pair_price(base, quote)
                if price is not None:
                    return price

            if self._is_inverse_pair(base, quote):
                price = await self._fetch_inverse_pair_price(base, quote)
                if price is not None:
                    return price

        # Determine which exchange to use
        if self._is_crypto_pair(normalized):
            # Try Binance first (most liquid)
            if self.binance_enabled:
                price = await self._fetch_binance_price(normalized)
                if price is not None:
                    return price

            # Try Kraken second (geo-friendly)
            if self.kraken_enabled:
                price = await self._fetch_kraken_price(normalized)
                if price is not None:
                    return price

            # Try CoinGecko last (good for altcoins/DeFi)
            if self.coingecko_enabled:
                price = await self._fetch_coingecko_price(normalized)
                if price is not None:
                    return price

        if self.alpaca_enabled:
            return await self._fetch_alpaca_price(symbol)

        log.warning("price_fetcher.no_source", symbol=symbol)
        return None

    def _is_inverse_pair(self, base: str, quote: str) -> bool:
        """Check if this is an inverse pair that needs special handling.

        Example: ETH/stETH (both are ~same value, need ratio calculation)
        """
        inverse_groups = [
            {"ETH", "WETH", "STETH", "RETH", "CBETH", "WSTETH"},  # ETH derivatives (uppercase)
            {"BTC", "WBTC"},  # BTC derivatives
        ]
        for group in inverse_groups:
            if base in group and quote in group:
                return True
        return False

    async def _fetch_inverse_pair_price(self, base: str, quote: str) -> Price | None:
        """Fetch price for inverse pairs by calculating ratio.

        Example: ETH/stETH = price(ETH in USD) / price(stETH in USD)

        For LST pairs (stETH, rETH), uses approximate peg assumption:
        - stETH ≈ ETH (typically 0.99-1.01)
        - rETH ≈ ETH * 1.05 (currently ~5% premium due to staking rewards)
        """
        try:
            # Special handling for LST pairs - use approximate pegs
            lst_pegs = {
                "STETH": 0.998,  # stETH typically trades at slight discount
                "RETH": 1.052,   # rETH includes staking rewards (~5% APR)
                "CBETH": 1.045,  # cbETH similar to rETH
                "WSTETH": 1.15,  # wstETH is wrapped stETH with accumulated rewards
            }

            log.debug(
                "price_fetcher.inverse_pair_check",
                base=base,
                quote=quote,
                quote_is_lst=quote in lst_pegs,
                base_is_lst=base in lst_pegs,
            )

            # If quote is an LST, use peg to ETH
            if quote in lst_pegs:
                eth_price = await self._fetch_price(f"{base}/USDC")
                if eth_price:
                    # stETH/USDC ≈ ETH/USDC * 0.998
                    approx_price = eth_price * lst_pegs[quote]
                    log.debug(
                        "price_fetcher.lst_peg_approximation",
                        token=quote,
                        peg=lst_pegs[quote],
                        eth_price=eth_price,
                        approx_price=approx_price,
                    )
                    return approx_price

            # If base is LST and quote is ETH, return inverse of peg
            if base in lst_pegs and quote in ["ETH", "WETH"]:
                # ETH/stETH ≈ 1 / 0.998 ≈ 1.002
                ratio = 1.0 / lst_pegs[base]
                log.debug(
                    "price_fetcher.lst_inverse_peg",
                    base=base,
                    quote=quote,
                    ratio=ratio,
                )
                return ratio

            # If base is LST and quote is USDC/USDT, use ETH as proxy
            if base in lst_pegs and quote in ["USDC", "USDT"]:
                # stETH/USDC ≈ ETH/USDC * 0.998
                eth_price = await self._fetch_price(f"ETH/{quote}")
                if eth_price:
                    approx_price = eth_price * lst_pegs[base]
                    log.debug(
                        "price_fetcher.lst_usd_peg",
                        base=base,
                        quote=quote,
                        eth_price=eth_price,
                        peg=lst_pegs[base],
                        approx_price=approx_price,
                    )
                    return approx_price

            # Fetch both prices in USD
            base_price = await self._fetch_price(f"{base}/USDC")
            quote_price = await self._fetch_price(f"{quote}/USDC")

            if base_price and quote_price and quote_price > 0:
                ratio = base_price / quote_price
                log.debug(
                    "price_fetcher.inverse_pair_calculated",
                    base=base,
                    quote=quote,
                    ratio=ratio,
                )
                return ratio
        except Exception as e:
            log.debug(
                "price_fetcher.inverse_pair_failed",
                base=base,
                quote=quote,
                error=str(e)[:50],
            )
        return None

    def _is_crypto_pair(self, symbol: str) -> bool:
        """Check if symbol is a crypto trading pair."""
        crypto_quotes = {"USDT", "USDC", "BUSD", "USD", "BTC", "ETH"}
        if "/" in symbol:
            base, quote = symbol.split("/", 1)
            return quote in crypto_quotes
        return False

    async def _fetch_binance_price(self, symbol: str) -> Price | None:
        """Fetch price from Binance.

        Args:
            symbol: Normalized symbol (e.g., "BTC/USDT")
        """
        if not self.binance_client:
            return None

        try:
            # Convert symbol format using Binance-specific mappings
            binance_symbol = self._to_binance_pair(symbol)

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

    def _to_binance_pair(self, symbol: str) -> str:
        """Convert symbol to Binance pair format."""
        base, quote = symbol.split("/")

        # Binance-specific mappings
        base_map = {
            "WETH": "ETH",
            "WBTC": "BTC",
            "stETH": "ETH",  # Binance has ETHUSDT, approximate stETH
            "rETH": "ETH",   # Approximate rETH with ETH
        }
        base = base_map.get(base, base)

        # Quote conversions
        quote_map = {
            "USDC": "USDT",  # Binance has more USDT pairs than USDC
        }
        quote = quote_map.get(quote, quote)

        # BTC/USDT -> BTCUSDT
        return f"{base}{quote}"

    async def _fetch_alpaca_price(self, symbol: str) -> Price | None:
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

    async def _fetch_kraken_price(self, symbol: str) -> Price | None:
        """Fetch price from Kraken public API with retry logic.

        Args:
            symbol: Normalized symbol (e.g., "BTC/USDT")
        """
        if not self.kraken_client:
            return None

        max_retries = 2
        retry_delay = 0.5

        for attempt in range(max_retries):
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
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (2**attempt))
                        continue
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

            except httpx.TimeoutException:
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2**attempt))
                    continue
                log.warning("price_fetcher.kraken_timeout", symbol=symbol, attempts=attempt + 1)
                return None

            except httpx.HTTPStatusError as e:
                if attempt < max_retries - 1 and e.response.status_code >= 500:
                    await asyncio.sleep(retry_delay * (2**attempt))
                    continue
                log.warning(
                    "price_fetcher.kraken_http_error",
                    symbol=symbol,
                    status=e.response.status_code,
                )
                return None

            except Exception as e:
                log.warning(
                    "price_fetcher.kraken_failed",
                    symbol=symbol,
                    error=str(e),
                    attempt=attempt + 1,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2**attempt))
                    continue
                return None

        return None

    def _to_kraken_pair(self, symbol: str) -> str:
        """Convert symbol to Kraken pair format (best-effort)."""
        overrides = {
            "GRT/ETH": "GRTXETH",
            "APE/ETH": "APEXETH",
            "LDO/ETH": "LDOXETH",
            "SHIB/ETH": "SHIBXETH",
            # Kraken lists MATIC in multiple formats
            "MATIC/USDC": "MATICUSD",
            "MATIC/USDT": "MATICUSDT",
            "MATIC/ETH": "MATICETH",
        }
        if symbol in overrides:
            return overrides[symbol]

        base, quote = symbol.split("/")

        # Kraken-specific mappings
        base = {
            "BTC": "XBT",
            "WETH": "ETH",
            "WBTC": "XBT",  # Use XBT price for WBTC
            "stETH": "ETH",  # Approximate stETH with ETH
            "rETH": "ETH",   # Approximate rETH with ETH
            "MATIC": "MATIC",  # MATIC is MATIC on Kraken
        }.get(base, base)

        quote = {
            "USDT": "USDT",
            "USDC": "USD",   # Kraken uses USD for USDC pairs
            "USD": "USD",
            "ETH": "ETH",
        }.get(quote, quote)

        return f"{base}{quote}"

    async def _fetch_coingecko_price(self, symbol: str) -> Price | None:
        """Fetch price from CoinGecko public API with retry logic.

        Args:
            symbol: Normalized symbol (e.g., "MATIC/USDC", "LDO/ETH")
        """
        if not self.coingecko_client:
            return None

        max_retries = 2
        retry_delay = 1.5

        for attempt in range(max_retries):
            try:
                # Rate limiting to avoid 429 errors (free tier limit)
                import time
                now = time.time()
                time_since_last_call = now - self._coingecko_last_call
                if time_since_last_call < self._coingecko_min_interval:
                    await asyncio.sleep(self._coingecko_min_interval - time_since_last_call)
                self._coingecko_last_call = time.time()

                base, quote = symbol.split("/")

                # Map tokens to CoinGecko IDs
                coin_id = self._to_coingecko_id(base)
                vs_currency = self._to_coingecko_currency(quote)

                if not coin_id or not vs_currency:
                    return None

                # Fetch simple price (free tier, no API key needed)
                response = await self.coingecko_client.get(
                    f"{self.coingecko_base_url}/simple/price",
                    params={
                        "ids": coin_id,
                        "vs_currencies": vs_currency,
                    },
                )
                response.raise_for_status()
                data = response.json()

                if coin_id not in data or vs_currency not in data[coin_id]:
                    return None

                price = float(data[coin_id][vs_currency])

                log.debug(
                    "price_fetcher.coingecko_price",
                    symbol=symbol,
                    price=price,
                )

                return price

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:  # Rate limit
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2**attempt) * 2  # Longer wait for rate limits
                        log.warning(
                            "price_fetcher.coingecko_rate_limited",
                            symbol=symbol,
                            wait_time=wait_time,
                        )
                        await asyncio.sleep(wait_time)
                        continue
                log.debug(
                    "price_fetcher.coingecko_http_error",
                    symbol=symbol,
                    status=e.response.status_code,
                )
                return None

            except Exception as e:
                log.debug(
                    "price_fetcher.coingecko_failed",
                    symbol=symbol,
                    error=str(e)[:100],
                    attempt=attempt + 1,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2**attempt))
                    continue
                return None

        return None

    def _to_coingecko_id(self, token: str) -> str | None:
        """Map token symbol to CoinGecko coin ID."""
        # Common token mappings to CoinGecko IDs
        mappings = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "WETH": "weth",
            "WBTC": "wrapped-bitcoin",
            "USDT": "tether",
            "USDC": "usd-coin",
            "DAI": "dai",
            "MATIC": "matic-network",
            "LINK": "chainlink",
            "UNI": "uniswap",
            "AAVE": "aave",
            "GRT": "the-graph",
            "SHIB": "shiba-inu",
            "PEPE": "pepe",
            "LDO": "lido-dao",
            "APE": "apecoin",
            "stETH": "lido-staked-ether",  # Fixed: use correct CoinGecko ID
            "rETH": "rocket-pool-eth",
        }
        return mappings.get(token)

    def _to_coingecko_currency(self, quote: str) -> str | None:
        """Map quote currency to CoinGecko vs_currency."""
        mappings = {
            "USDT": "usd",
            "USDC": "usd",
            "USD": "usd",
            "BTC": "btc",
            "ETH": "eth",
        }
        return mappings.get(quote)

    async def get_multiple_prices(
        self,
        symbols: list[Symbol]
    ) -> dict[Symbol, Price | None]:
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
async def fetch_cex_price(symbol: Symbol) -> Price | None:
    """Quick helper to fetch a single price.

    Example:
        >>> price = await fetch_cex_price("BTC/USDT")
        >>> print(f"BTC price: ${price}")
    """
    fetcher = CEXPriceFetcher()
    return await fetcher.get_price(symbol)
