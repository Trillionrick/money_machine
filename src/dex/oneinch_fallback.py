"""1inch API fallback for DEX quotes when The Graph is unavailable.

This module provides a direct 1inch API integration that bypasses The Graph dependency.
Use this when The Graph API key has hit rate limits or requires payment.
"""

import os
from decimal import Decimal
from typing import Any

import httpx
import structlog

log = structlog.get_logger()


class OneInchQuoter:
    """Direct 1inch API integration for DEX quotes."""

    def __init__(self, api_key: str | None = None, timeout: float = 3.0):
        """Initialize 1inch quoter.

        Args:
            api_key: 1inch API key (optional, but recommended for higher rate limits)
            timeout: HTTP timeout in seconds
        """
        self.api_key = api_key or os.getenv("ONEINCH_API_KEY") or os.getenv("ONEINCH_TOKEN")
        self.timeout = timeout

    async def get_quote(
        self,
        chain_id: int,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        token_in_decimals: int = 18,
        token_out_decimals: int = 18,
    ) -> dict[str, Any] | None:
        """Get swap quote from 1inch.

        Args:
            chain_id: Chain ID (1 for Ethereum, 137 for Polygon)
            token_in: Input token address
            token_out: Output token address
            amount_in: Amount to swap (in token units, not wei)
            token_in_decimals: Decimals for input token
            token_out_decimals: Decimals for output token

        Returns:
            Quote dict with 'expected_output' and 'price', or None if failed
        """
        # Convert amount to wei
        amount_in_wei = int(amount_in * Decimal(10**token_in_decimals))

        # Build request
        url = f"https://api.1inch.dev/swap/v6.0/{chain_id}/quote"
        params = {
            "src": token_in,
            "dst": token_out,
            "amount": str(amount_in_wei),
        }

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()

            # Parse response
            dst_amount_raw = data.get("dstAmount") or data.get("toAmount")
            if not dst_amount_raw:
                log.debug("oneinch.quote_missing_dst_amount", data=data)
                return None

            # Convert from wei to token units
            expected_output = Decimal(dst_amount_raw) / Decimal(10**token_out_decimals)
            price = float(expected_output / amount_in) if amount_in > 0 else 0.0

            log.debug(
                "oneinch.quote_success",
                chain_id=chain_id,
                token_in=token_in[-6:],
                token_out=token_out[-6:],
                amount_in=str(amount_in),
                expected_output=str(expected_output),
                price=price,
            )

            return {
                "expected_output": expected_output,
                "price": price,
                "liquidity": None,  # 1inch doesn't provide liquidity directly
                "pool": "1inch_aggregator",
                "token0": {"decimals": token_in_decimals},
                "token1": {"decimals": token_out_decimals},
                "recent_swaps": [],
                "metadata": {
                    "source": "1inch",
                    "estimated_gas": data.get("gas") or data.get("estimatedGas"),
                    "protocols": data.get("protocols"),
                },
            }

        except httpx.HTTPStatusError as e:
            log.debug(
                "oneinch.quote_http_error",
                status=e.response.status_code,
                detail=e.response.text[:200],
            )
            return None
        except httpx.TimeoutException:
            log.debug("oneinch.quote_timeout")
            return None
        except Exception as e:
            log.debug("oneinch.quote_failed", error=str(e))
            return None
