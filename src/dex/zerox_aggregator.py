"""0x API integration for DEX quote aggregation.

Provides fallback when 1inch is unavailable and better pricing discovery
by comparing multiple aggregators.

0x API v2 (2025) - Production-ready implementation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
import structlog
from web3 import Web3

log = structlog.get_logger()


@dataclass
class ZeroXQuote:
    """Quote response from 0x API."""

    chain_id: int
    buy_token: str
    sell_token: str
    buy_amount: Decimal
    sell_amount: Decimal
    price: Decimal
    guaranteed_price: Decimal  # Price after slippage
    estimated_gas: int
    gas_price_wei: int
    protocol_fee_wei: int
    sources: list[dict[str, Any]]  # DEX sources used
    allow_ance_target: str  # Contract to approve
    to_address: str  # Contract to call for swap
    data: str  # Call data
    value_wei: int  # ETH value to send

    @property
    def effective_price(self) -> Decimal:
        """Get effective price including all fees."""
        return self.guaranteed_price

    @property
    def total_cost_eth(self) -> Decimal:
        """Total cost in ETH including gas and protocol fees."""
        total_wei = self.estimated_gas * self.gas_price_wei + self.protocol_fee_wei
        return Decimal(total_wei) / Decimal(10**18)


@dataclass
class ZeroXConfig:
    """Configuration for 0x API client."""

    # API endpoints by chain
    api_urls: dict[int, str] = None

    # API key (optional but recommended for higher rate limits)
    api_key: str | None = None

    # Slippage tolerance
    slippage_bps: float = 50  # 0.5%

    # Enable affiliate fees
    enable_affiliate_fee: bool = False
    affiliate_fee_bps: float = 0  # Fee to charge on top

    # Request settings
    timeout_seconds: float = 3.0
    max_retries: int = 2

    def __post_init__(self):
        """Set default API URLs if not provided."""
        if self.api_urls is None:
            self.api_urls = {
                1: "https://api.0x.org",  # Ethereum mainnet
                137: "https://polygon.api.0x.org",  # Polygon
                42161: "https://arbitrum.api.0x.org",  # Arbitrum
                10: "https://optimism.api.0x.org",  # Optimism
                8453: "https://base.api.0x.org",  # Base
            }


class ZeroXAggregator:
    """0x API client for DEX quote aggregation.

    Provides:
    - Price quotes across multiple DEXes
    - Swap execution calldata
    - Gas estimates
    - Source liquidity breakdown
    """

    def __init__(self, config: ZeroXConfig | None = None):
        """Initialize 0x aggregator.

        Args:
            config: Configuration (uses defaults if None)
        """
        self.config = config or ZeroXConfig()
        self.log = structlog.get_logger()

        # HTTP client with retry logic
        self.client = httpx.AsyncClient(
            timeout=self.config.timeout_seconds,
            follow_redirects=True,
        )

        # Statistics
        self.stats = {
            "quotes_requested": 0,
            "quotes_success": 0,
            "quotes_failed": 0,
            "total_gas_estimated": 0,
        }

    async def get_quote(
        self,
        chain_id: int,
        sell_token: str,
        buy_token: str,
        sell_amount: Decimal | None = None,
        buy_amount: Decimal | None = None,
        taker_address: str | None = None,
        slippage_bps: float | None = None,
        exclude_sources: list[str] | None = None,
    ) -> ZeroXQuote | None:
        """Get a quote for a token swap.

        Args:
            chain_id: Blockchain ID (1=Ethereum, 137=Polygon, etc.)
            sell_token: Token to sell (address or symbol)
            buy_token: Token to buy (address or symbol)
            sell_amount: Amount to sell (specify this OR buy_amount, not both)
            buy_amount: Amount to buy (specify this OR sell_amount, not both)
            taker_address: Address that will execute the trade (optional)
            slippage_bps: Slippage tolerance in bps (uses config default if None)
            exclude_sources: DEX sources to exclude (e.g., ["Uniswap_V2"])

        Returns:
            ZeroXQuote if successful, None if failed
        """
        self.stats["quotes_requested"] += 1

        if chain_id not in self.config.api_urls:
            self.log.warning("zerox.unsupported_chain", chain_id=chain_id)
            return None

        if (sell_amount is None) == (buy_amount is None):
            raise ValueError("Must specify exactly one of sell_amount or buy_amount")

        try:
            # Build query parameters
            params: dict[str, Any] = {
                "sellToken": sell_token,
                "buyToken": buy_token,
                "slippagePercentage": (slippage_bps or self.config.slippage_bps) / 10000,
            }

            if sell_amount is not None:
                params["sellAmount"] = str(int(sell_amount))
            else:
                params["buyAmount"] = str(int(buy_amount))

            if taker_address:
                params["takerAddress"] = taker_address

            if exclude_sources:
                params["excludedSources"] = ",".join(exclude_sources)

            if self.config.enable_affiliate_fee and self.config.affiliate_fee_bps > 0:
                params["feeRecipient"] = taker_address  # Send fees to taker
                params["buyTokenPercentageFee"] = self.config.affiliate_fee_bps / 10000

            # Get API URL
            base_url = self.config.api_urls[chain_id]

            # Build headers
            headers = {"Content-Type": "application/json"}
            if self.config.api_key:
                headers["0x-api-key"] = self.config.api_key

            # Make request (use /swap/v1/quote for executable quotes)
            url = f"{base_url}/swap/v1/quote"

            self.log.debug(
                "zerox.requesting_quote",
                chain_id=chain_id,
                sell_token=sell_token,
                buy_token=buy_token,
                sell_amount=sell_amount,
                buy_amount=buy_amount,
            )

            response = await self._request_with_retry(url, params, headers)

            if response.status_code != 200:
                self.log.warning(
                    "zerox.quote_failed",
                    status=response.status_code,
                    response=response.text,
                )
                self.stats["quotes_failed"] += 1
                return None

            data = response.json()

            # Parse response into ZeroXQuote
            quote = self._parse_quote(chain_id, data)

            self.stats["quotes_success"] += 1
            self.stats["total_gas_estimated"] += quote.estimated_gas

            self.log.info(
                "zerox.quote_received",
                chain_id=chain_id,
                sell_token=sell_token,
                buy_token=buy_token,
                price=float(quote.price),
                guaranteed_price=float(quote.guaranteed_price),
                gas=quote.estimated_gas,
                sources=len(quote.sources),
            )

            return quote

        except Exception as e:
            self.log.exception("zerox.quote_error", error=str(e))
            self.stats["quotes_failed"] += 1
            return None

    async def get_price_only(
        self,
        chain_id: int,
        sell_token: str,
        buy_token: str,
        sell_amount: Decimal,
    ) -> Decimal | None:
        """Get just the price without execution calldata (faster, no gas needed).

        Args:
            chain_id: Blockchain ID
            sell_token: Token to sell
            buy_token: Token to buy
            sell_amount: Amount to sell

        Returns:
            Price as Decimal, or None if failed
        """
        if chain_id not in self.config.api_urls:
            return None

        try:
            params = {
                "sellToken": sell_token,
                "buyToken": buy_token,
                "sellAmount": str(int(sell_amount)),
            }

            base_url = self.config.api_urls[chain_id]
            url = f"{base_url}/swap/v1/price"

            headers = {"Content-Type": "application/json"}
            if self.config.api_key:
                headers["0x-api-key"] = self.config.api_key

            response = await self._request_with_retry(url, params, headers)

            if response.status_code != 200:
                return None

            data = response.json()
            return Decimal(data["price"])

        except Exception as e:
            self.log.warning("zerox.price_error", error=str(e))
            return None

    async def _request_with_retry(
        self,
        url: str,
        params: dict,
        headers: dict,
    ) -> httpx.Response:
        """Make HTTP request with retry logic.

        Args:
            url: API endpoint
            params: Query parameters
            headers: HTTP headers

        Returns:
            Response object

        Raises:
            Exception: If all retries fail
        """
        last_error = None

        for attempt in range(self.config.max_retries + 1):
            try:
                response = await self.client.get(url, params=params, headers=headers)
                return response

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                if attempt < self.config.max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                    continue

        raise last_error or Exception("Request failed")

    def _parse_quote(self, chain_id: int, data: dict) -> ZeroXQuote:
        """Parse API response into ZeroXQuote.

        Args:
            chain_id: Blockchain ID
            data: JSON response data

        Returns:
            Parsed quote
        """
        return ZeroXQuote(
            chain_id=chain_id,
            buy_token=data["buyTokenAddress"],
            sell_token=data["sellTokenAddress"],
            buy_amount=Decimal(data["buyAmount"]),
            sell_amount=Decimal(data["sellAmount"]),
            price=Decimal(data["price"]),
            guaranteed_price=Decimal(data.get("guaranteedPrice", data["price"])),
            estimated_gas=int(data["gas"]),
            gas_price_wei=int(data["gasPrice"]),
            protocol_fee_wei=int(data.get("protocolFee", "0")),
            sources=data.get("sources", []),
            allowance_target=data["allowanceTarget"],
            to_address=data["to"],
            data=data["data"],
            value_wei=int(data.get("value", "0")),
        )

    def get_stats(self) -> dict[str, Any]:
        """Get aggregator usage statistics.

        Returns:
            Stats dict
        """
        success_rate = (
            self.stats["quotes_success"] / self.stats["quotes_requested"]
            if self.stats["quotes_requested"] > 0
            else 0.0
        )

        avg_gas = (
            self.stats["total_gas_estimated"] / self.stats["quotes_success"]
            if self.stats["quotes_success"] > 0
            else 0
        )

        return {
            **self.stats,
            "success_rate": success_rate,
            "avg_gas": avg_gas,
        }

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()


async def compare_aggregators(
    chain_id: int,
    sell_token: str,
    buy_token: str,
    sell_amount: Decimal,
    oneinch_price: Decimal | None = None,
) -> dict[str, Any]:
    """Compare quotes from 0x and 1inch to find best price.

    Args:
        chain_id: Blockchain ID
        sell_token: Token to sell
        buy_token: Token to buy
        sell_amount: Amount to sell
        oneinch_price: Optional 1inch price for comparison

    Returns:
        Comparison dict with best aggregator and prices
    """
    zerox = ZeroXAggregator()

    try:
        # Get 0x quote
        zerox_quote = await zerox.get_quote(
            chain_id=chain_id,
            sell_token=sell_token,
            buy_token=buy_token,
            sell_amount=sell_amount,
        )

        result = {
            "chain_id": chain_id,
            "sell_token": sell_token,
            "buy_token": buy_token,
            "sell_amount": sell_amount,
            "zerox_available": zerox_quote is not None,
            "oneinch_available": oneinch_price is not None,
        }

        if zerox_quote:
            result["zerox_price"] = float(zerox_quote.effective_price)
            result["zerox_gas"] = zerox_quote.estimated_gas
            result["zerox_sources"] = [s.get("name") for s in zerox_quote.sources]

        if oneinch_price:
            result["oneinch_price"] = float(oneinch_price)

        # Determine best option
        if zerox_quote and oneinch_price:
            if zerox_quote.effective_price > oneinch_price:
                result["best_aggregator"] = "0x"
                result["price_difference_bps"] = float(
                    (zerox_quote.effective_price - oneinch_price) / oneinch_price * 10000
                )
            else:
                result["best_aggregator"] = "1inch"
                result["price_difference_bps"] = float(
                    (oneinch_price - zerox_quote.effective_price)
                    / zerox_quote.effective_price
                    * 10000
                )
        elif zerox_quote:
            result["best_aggregator"] = "0x"
        elif oneinch_price:
            result["best_aggregator"] = "1inch"
        else:
            result["best_aggregator"] = None

        return result

    finally:
        await zerox.close()
