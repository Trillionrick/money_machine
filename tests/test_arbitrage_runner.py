"""Unit test for arbitrage runner decision logic."""

from decimal import Decimal
from typing import Awaitable

import pytest

from src.brokers.routing import OrderRouter
from src.core.execution import Order
from src.live.arbitrage_runner import ArbitrageConfig, ArbitrageRunner


class DummyDex:
    def __init__(self) -> None:
        self.swaps = []

    async def get_quote(self, token_in: str, token_out: str, amount_in: Decimal):
        return {
            "expected_output": amount_in / Decimal("1000"),  # price = 0.001 quote/base
        }

    async def execute_market_swap(self, **kwargs):
        self.swaps.append(kwargs)
        return "tx_hash"


class DummyRouter(OrderRouter):
    def __init__(self) -> None:
        self.sent = []

    async def submit_orders(self, orders):
        self.sent.extend(orders)


@pytest.mark.asyncio
async def test_arbitrage_runner_executes_when_edge_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    dex = DummyDex()
    router = DummyRouter()

    async def price_fetcher(_symbol: str) -> float | None:
        return 2.0  # CEX price >> dex price (edge positive)

    cfg = ArbitrageConfig(min_edge_bps=10, enable_execution=True, max_notional=10.0, max_position=0.02)
    runner = ArbitrageRunner(
        router=router,
        dex=dex,  # type: ignore[arg-type]
        price_fetcher=price_fetcher,  # type: ignore[arg-type]
        token_addresses={"USDC": "token_in", "ETH": "token_out"},
        config=cfg,
    )

    await runner._scan_symbol("ETH/USDC")

    assert dex.swaps, "DEX swap should be submitted"
    assert router.sent and isinstance(router.sent[0], Order)


@pytest.mark.asyncio
async def test_arbitrage_runner_skips_when_no_price() -> None:
    dex = DummyDex()
    router = DummyRouter()

    async def price_fetcher(_symbol: str) -> float | None:
        return None

    cfg = ArbitrageConfig(min_edge_bps=10, enable_execution=True)
    runner = ArbitrageRunner(
        router=router,
        dex=dex,  # type: ignore[arg-type]
        price_fetcher=price_fetcher,  # type: ignore[arg-type]
        token_addresses={"USDC": "token_in", "ETH": "token_out"},
        config=cfg,
    )

    await runner._scan_symbol("ETH/USDC")
    assert not dex.swaps
    assert not router.sent
