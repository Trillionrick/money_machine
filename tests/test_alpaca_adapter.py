"""Sanity tests for Alpaca adapter request building."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.brokers.alpaca_adapter import AlpacaAdapter
from src.core.execution import Order, OrderType, Side


class DummyOrder:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.id = "1"


class DummyClient:
    def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - simple stub
        self.submitted = []

    def submit_order(self, request):
        self.submitted.append(request)
        return DummyOrder(request.symbol)

    def cancel_order_by_id(self, order_id):
        return {"id": order_id}


@pytest.mark.asyncio
async def test_alpaca_market_order_submission() -> None:
    import types
    import sys

    dummy_mod = types.SimpleNamespace()
    enums_mod = types.SimpleNamespace(OrderSide=types.SimpleNamespace(BUY="buy", SELL="sell"), TimeInForce=types.SimpleNamespace(DAY="day"))
    requests_mod = types.SimpleNamespace(
        MarketOrderRequest=lambda **kwargs: types.SimpleNamespace(**kwargs),
        LimitOrderRequest=lambda **kwargs: types.SimpleNamespace(**kwargs),
    )
    client_mod = types.SimpleNamespace(TradingClient=DummyClient)

    with patch.dict(
        sys.modules,
        {
            "alpaca": dummy_mod,
            "alpaca.trading": dummy_mod,
            "alpaca.trading.client": client_mod,
            "alpaca.trading.requests": requests_mod,
            "alpaca.trading.enums": enums_mod,
        },
    ):
        adapter = AlpacaAdapter(api_key="k", api_secret="s", paper=True)

    order = Order(symbol="AAPL", side=Side.BUY, quantity=2, order_type=OrderType.MARKET)

    with patch.object(adapter, "client", DummyClient()):
        with patch.object(asyncio, "get_event_loop", return_value=asyncio.new_event_loop()):
            await adapter.submit_orders([order])
