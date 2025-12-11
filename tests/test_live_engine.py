"""Tests for live engine wiring and loops."""
# pyright: reportMissingImports=false

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import msgspec

if TYPE_CHECKING:
    import pytest

try:
    import pytest  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - dev dependency missing
    pytest = None  # type: ignore[assignment]

from src.core.execution import Fill, Order, OrderSeq, OrderType, Side
from src.core.policy import MarketSnapshot, Policy, PortfolioState
from src.core.types import ContextMap
from src.live.engine import LiveEngine


class DummyExecEngine:
    def __init__(self, *, positions: dict[str, float]) -> None:
        self.positions = positions
        self.submitted: list[list[Order]] = []
        self.fills: list[Fill] = []

    async def submit_orders(self, orders: OrderSeq) -> None:
        self.submitted.append(list(orders))

    async def cancel_order(self, order_id: str) -> None:  # pragma: no cover - not used
        raise NotImplementedError

    async def cancel_all_orders(self, symbol: str | None = None) -> None:  # pragma: no cover
        raise NotImplementedError

    async def get_open_orders(self, symbol: str | None = None):  # pragma: no cover
        raise NotImplementedError

    async def get_positions(self) -> dict[str, float]:
        return self.positions

    async def stream_fills(self) -> AsyncIterator[Fill]:
        async def _gen() -> AsyncIterator[Fill]:
            for fill in self.fills:
                yield fill
        return _gen()

    async def get_account(self) -> dict[str, float]:
        return {"cash": 0.0, "equity": 0.0, "buying_power": 0.0}


@dataclass
class DummyPolicy(Policy):
    orders_to_submit: list[Order]
    fills_seen: list[Fill]

    def decide(
        self,
        portfolio: PortfolioState,
        snapshot: MarketSnapshot,
        context: ContextMap | None = None,
    ) -> OrderSeq:
        return self.orders_to_submit

    def on_fill(self, fill: msgspec.Struct) -> None:
        self.fills_seen.append(fill)  # type: ignore[arg-type]


async def _snapshot_feed(snapshots: list[MarketSnapshot]) -> AsyncIterator[MarketSnapshot]:
    for snap in snapshots:
        yield snap
    await asyncio.sleep(0)  # allow cancellation paths


async_mark = (lambda fn: fn) if pytest is None else pytest.mark.asyncio


@async_mark  # type: ignore[misc]
async def test_market_data_loop_submits_orders_and_updates_portfolio() -> None:
    if pytest is None:
        return
    exec_engine = DummyExecEngine(positions={"BTC/USD": 1.0})
    policy = DummyPolicy(orders_to_submit=[
        Order(symbol="ETH/USD", side=Side.BUY, quantity=2, order_type=OrderType.MARKET)
    ], fills_seen=[])

    snapshots = [
        MarketSnapshot(timestamp=1, prices={"ETH/USD": 2000}, volumes={}, features=None),
    ]
    engine = LiveEngine(exec_engine, _snapshot_feed(snapshots), policy, tick_rate_hz=1_000.0)

    await asyncio.wait_for(engine._market_data_loop(), timeout=1.0)

    assert exec_engine.submitted and exec_engine.submitted[0][0].symbol == "ETH/USD"
    assert engine._last_portfolio is not None
    assert engine._last_portfolio.positions["BTC/USD"] == 1.0


@async_mark  # type: ignore[misc]
async def test_fill_handler_invokes_policy_on_fill() -> None:
    if pytest is None:
        return
    exec_engine = DummyExecEngine(positions={})
    fill = Fill(
        order_id="1",
        symbol="BTC/USD",
        side=Side.BUY,
        quantity=0.5,
        price=30000.0,
        timestamp=123,
        fee=0.0,
    )
    exec_engine.fills = [fill]
    policy = DummyPolicy(orders_to_submit=[], fills_seen=[])
    engine = LiveEngine(exec_engine, _snapshot_feed([]), policy, tick_rate_hz=1_000.0)

    await asyncio.wait_for(engine._fill_handler_loop(), timeout=1.0)

    assert policy.fills_seen == [fill]


@async_mark  # type: ignore[misc]
async def test_health_monitor_respects_stop_signal() -> None:
    if pytest is None:
        return
    exec_engine = DummyExecEngine(positions={})
    policy = DummyPolicy(orders_to_submit=[], fills_seen=[])
    engine = LiveEngine(exec_engine, _snapshot_feed([]), policy, tick_rate_hz=1_000.0)

    with patch("src.live.engine.asyncio.sleep", new=AsyncMock(return_value=None)):
        task = asyncio.create_task(engine._health_monitor())
        await engine.stop()
        await asyncio.wait_for(task, timeout=1.0)
        assert engine._shutdown.is_set()


@async_mark  # type: ignore[misc]
async def test_lifecycle_context_triggers_shutdown() -> None:
    if pytest is None:
        return
    exec_engine = DummyExecEngine(positions={})
    policy = DummyPolicy(orders_to_submit=[], fills_seen=[])
    engine = LiveEngine(exec_engine, _snapshot_feed([]), policy, tick_rate_hz=1_000.0)

    async with engine.lifecycle():
        await engine.stop()
    assert engine._shutdown.is_set()
