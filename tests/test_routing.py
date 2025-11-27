"""Tests for routing policy and router."""

import pytest

from src.brokers.routing import OrderRouter
from src.core.execution import Order, OrderType, Side


class DummyConnector:
    """Capture submitted orders for assertions."""

    def __init__(self) -> None:
        self.submitted: list[Order] = []

    async def submit_orders(self, orders: list[Order]) -> None:
        self.submitted.extend(orders)


@pytest.mark.asyncio
async def test_forex_routes_to_oanda_only() -> None:
    connectors = {
        "oanda": DummyConnector(),
        "binance": DummyConnector(),
    }
    router = OrderRouter(connectors)

    order = Order(
        symbol="EUR/USD",
        side=Side.BUY,
        quantity=10_000,
        order_type=OrderType.MARKET,
    )

    await router.submit_orders([order])

    assert len(connectors["oanda"].submitted) == 1
    assert connectors["oanda"].submitted[0].quantity == order.quantity
    assert connectors["binance"].submitted == []


@pytest.mark.asyncio
async def test_crypto_split_respects_max_share() -> None:
    connectors = {
        "kraken": DummyConnector(),
        "coinbase": DummyConnector(),
        "binance": DummyConnector(),
    }
    router = OrderRouter(connectors)

    order = Order(
        symbol="BTC/USDT",
        side=Side.BUY,
        quantity=10,
        order_type=OrderType.MARKET,
    )

    await router.submit_orders([order])

    assert [o.quantity for o in connectors["kraken"].submitted] == [4]
    assert [o.quantity for o in connectors["coinbase"].submitted] == [4]
    assert [o.quantity for o in connectors["binance"].submitted] == [2]


@pytest.mark.asyncio
async def test_crypto_overrides_when_single_venue() -> None:
    connectors = {
        "binance": DummyConnector(),
    }
    router = OrderRouter(connectors)

    order = Order(
        symbol="ETH/USDT",
        side=Side.SELL,
        quantity=5,
        order_type=OrderType.MARKET,
    )

    await router.submit_orders([order])

    assert len(connectors["binance"].submitted) == 1
    assert connectors["binance"].submitted[0].quantity == order.quantity
