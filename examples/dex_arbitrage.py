"""Cross-venue arbitrage sketch using Binance (CEX) and Uniswap (DEX)."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import structlog

from src.brokers.connection_manager import ConnectionManager
from src.brokers.credentials import BrokerCredentials

logger = structlog.get_logger()


async def cross_venue_arbitrage() -> None:
    manager = ConnectionManager(BrokerCredentials())
    await manager.initialize()

    uniswap_eth = manager.connectors.get("uniswap_ethereum")
    binance = manager.connectors.get("binance")

    if uniswap_eth is None or binance is None:
        missing = [k for k in ("uniswap_ethereum", "binance") if k not in manager.connectors]
        msg = f"Missing connectors: {', '.join(missing)}"
        raise RuntimeError(msg)

    token_eth = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"  # WETH
    token_usdc = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

    dex_quote = await uniswap_eth.get_quote(
        token_in=token_eth,
        token_out=token_usdc,
        amount_in=Decimal("1.0"),
    )

    cex_price = Decimal(await binance.get_ticker_price("ETHUSDC"))
    dex_price = dex_quote["expected_output"]

    spread = abs(dex_price - cex_price) / cex_price

    logger.info(
        "arbitrage.scan",
        dex_price=float(dex_price),
        cex_price=float(cex_price),
        spread_pct=float(spread * 100),
    )

    if spread > Decimal("0.01"):
        if dex_price > cex_price:
            await binance.submit_orders([])  # Placeholder for CEX leg
            await uniswap_eth.execute_market_swap(
                token_in=token_eth,
                token_out=token_usdc,
                amount_in=Decimal("0.1"),
            )
        else:
            await uniswap_eth.execute_market_swap(
                token_in=token_usdc,
                token_out=token_eth,
                amount_in=Decimal("300"),
            )
            await binance.submit_orders([])  # Placeholder for CEX leg


if __name__ == "__main__":
    asyncio.run(cross_venue_arbitrage())
