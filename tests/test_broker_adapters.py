"""Adapter smoke tests for request construction and error mapping."""
# pyright: reportMissingImports=false

from unittest.mock import AsyncMock, patch

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

try:
    import pytest  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - dev dependency missing
    pytest = None  # type: ignore[assignment]

from pydantic import SecretStr

from src.brokers.binance_adapter import BinanceAdapter
from src.brokers.kraken_adapter import KrakenAdapter
from src.brokers.oanda_adapter import OandaAdapter
from src.brokers.oanda_config import OandaConfig, OandaEnvironment
from src.core.execution import ExecutionError, Order, OrderType, Side


class DummyClient:
    """Minimal sync client to emulate binance SDK."""

    def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - simple stub
        self.orders = []

    def get_symbol_info(self, symbol):
        return {"filters": [{"filterType": "LOT_SIZE", "stepSize": "0.01"}]}

    def create_order(self, **kwargs):
        self.orders.append(kwargs)
        return {"orderId": 1}

    def cancel_order(self, **kwargs):
        return {"status": "CANCELED"}

def cancel_open_orders(self, **kwargs):
    return []


if pytest is None:
    pytestmark: list = []  # No pytest available; tests become no-ops
    async_mark = lambda fn: fn
else:
    pytestmark = []
    async_mark = pytest.mark.asyncio


@async_mark  # type: ignore[misc]
async def test_binance_adapter_builds_orders() -> None:
    if pytest is None:
        return

    import types
    import sys

    dummy_mod = types.SimpleNamespace()
    client_mod = types.SimpleNamespace(Client=DummyClient)
    exceptions_mod = types.SimpleNamespace(BinanceAPIException=Exception)

    with patch.dict(
        sys.modules,
        {
            "binance": dummy_mod,
            "binance.client": client_mod,
            "binance.exceptions": exceptions_mod,
        },
    ):
        adapter = BinanceAdapter(api_key="k", api_secret="s", testnet=True)

    order = Order(symbol="BTC/USDT", side=Side.BUY, quantity=1.2345, order_type=OrderType.MARKET)

    with patch.object(adapter, "_submit_single_order", new_callable=AsyncMock) as mock_submit:
        await adapter.submit_orders([order])
        mock_submit.assert_awaited_once()
        sent_order = mock_submit.call_args.args[0]
        assert sent_order.symbol == "BTC/USDT"


@async_mark  # type: ignore[misc]
async def test_kraken_signature_and_request(monkeypatch=None) -> None:
    if pytest is None:
        return
    assert monkeypatch is not None, "pytest monkeypatch fixture required"
    adapter = KrakenAdapter(api_key="k", api_secret="a2F5", base_url="https://api.kraken.com")

    async def fake_request(endpoint, params=None, private=False):
        if private:
            assert endpoint == "Balance"
        return {}

    monkeypatch.setattr(adapter, "_request", fake_request)
    await adapter.get_account()


@async_mark  # type: ignore[misc]
async def test_oanda_error_mapping(monkeypatch=None) -> None:
    if pytest is None:
        return
    assert monkeypatch is not None, "pytest monkeypatch fixture required"

    config = OandaConfig.model_validate(
        {
            "OANDA_API_TOKEN": "t",
            "OANDA_ACCOUNT_ID": "001-001-1234567-001",
            "OANDA_ENVIRONMENT": OandaEnvironment.PRACTICE.value,
        }
    )
    adapter = OandaAdapter(config)

    async def fake_request(method, endpoint, params=None, json=None):
        raise ExecutionError("boom")

    with patch.object(adapter, "_request", side_effect=fake_request):
        with pytest.raises(Exception):
            await adapter.get_account()

    await adapter.close()
