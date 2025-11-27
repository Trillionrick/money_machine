"""Tests for live engine wiring and loops."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.core.execution import Fill, Order, OrderType, Side
from src.core.policy import MarketSnapshot, Policy, PortfolioState
from src.live.engine import LiveEngine


class DummyExecEngine:
    def __init__(self, *, positions: dict[str, float]) -> None:
        self.positions = positions
        self.submitted: list[list[Order]] = []
        self.fills: list[Fill] = []

    async def submit_orders(self, orders: list[Order]) -> None:
        self.submitted.append(orders)

    async def cancel_order(self, order_id: str) -> None:  # pragma: no cover - not used
        raise NotImplementedError

    async def cancel_all_orders(self, symbol: str | None = None) -> None:  # pragma: no cover
        raise NotImplementedError

    async def get_open_orders(self, symbol: str | None = None):  # pragma: no cover
        raise NotImplementedError

    async def get_positions(self) -> dict[str, float]:
        return self.positions

    async def stream_fills(self) -> AsyncIterator[Fill]:
        for fill in self.fills:
            yield fill


@dataclass
class DummyPolicy(Policy):
    orders_to_submit: list[Order]
    fills_seen: list[Fill]

    def decide(
        self,
        portfolio: PortfolioState,
        snapshot: MarketSnapshot,
        context: dict[str, Any] | None = None,
    ):
        return self.orders_to_submit

    def on_fill(self, fill: Fill) -> None:
        self.fills_seen.append(fill)


async def _snapshot_feed(snapshots: list[MarketSnapshot]) -> AsyncIterator[MarketSnapshot]:
    for snap in snapshots:
        yield snap
    await asyncio.sleep(0)  # allow cancellation paths


@pytest.mark.asyncio
async def test_market_data_loop_submits_orders_and_updates_portfolio() -> None:
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


@pytest.mark.asyncio
async def test_fill_handler_invokes_policy_on_fill() -> None:
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


@pytest.mark.asyncio
async def test_health_monitor_respects_stop_signal() -> None:
    exec_engine = DummyExecEngine(positions={})
    policy = DummyPolicy(orders_to_submit=[], fills_seen=[])
    engine = LiveEngine(exec_engine, _snapshot_feed([]), policy, tick_rate_hz=1_000.0)

    with patch("src.live.engine.asyncio.sleep", new=AsyncMock(return_value=None)):
        task = asyncio.create_task(engine._health_monitor())
        await engine.stop()
        await asyncio.wait_for(task, timeout=1.0)
        assert engine._shutdown.is_set()


@pytest.mark.asyncio
async def test_lifecycle_context_triggers_shutdown() -> None:
    exec_engine = DummyExecEngine(positions={})
    policy = DummyPolicy(orders_to_submit=[], fills_seen=[])
    engine = LiveEngine(exec_engine, _snapshot_feed([]), policy, tick_rate_hz=1_000.0)

    async with engine.lifecycle():
        await engine.stop()
    assert engine._shutdown.is_set()
