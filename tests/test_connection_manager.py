"""Sanity checks for ConnectionManager wiring."""
# pyright: reportMissingImports=false

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

try:
    import pytest  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - dev dependency missing
    pytest = None  # type: ignore[assignment]

from pydantic import SecretStr

from src.brokers.connection_manager import ConnectionManager
from src.brokers.credentials import BrokerCredentials


if pytest is None:
    pytestmark: list = []  # No pytest available; tests become no-ops
    async_mark = lambda fn: fn
else:
    pytestmark = []
    async_mark = pytest.mark.asyncio


@async_mark  # type: ignore[misc]
async def test_connection_manager_initializes_router(monkeypatch=None) -> None:
    if pytest is None:
        return
    assert monkeypatch is not None, "pytest monkeypatch fixture required"

    creds = BrokerCredentials.model_validate(
        {
            "BINANCE_API_KEY": "k",
            "BINANCE_API_SECRET": "s",
            "KRAKEN_API_KEY": "k",
            "KRAKEN_API_SECRET": "s",
            "OANDA_API_KEY": "tok",
            "OANDA_ACCOUNT_ID": "001-001-1234567-001",
        }
    )

    # Stub adapters to avoid network
    from src.brokers import connection_manager as cm
    monkeypatch.setattr(cm, "BinanceAdapter", lambda *a, **k: object())
    monkeypatch.setattr(cm, "KrakenAdapter", lambda *a, **k: object())

    class DummyOanda:
        async def submit_orders(self, orders):  # pragma: no cover - simple stub
            return

    monkeypatch.setattr(cm, "OandaAdapter", lambda *a, **k: DummyOanda())
    monkeypatch.setattr(cm, "OandaConfig", lambda: None)

    manager = ConnectionManager(creds, dex_config=None)
    await manager.initialize()
    assert manager.router is not None
    assert "binance" in manager.connectors or "kraken" in manager.connectors


@async_mark  # type: ignore[misc]
async def test_route_and_submit_requires_init() -> None:
    if pytest is None:
        return

    manager = ConnectionManager(BrokerCredentials(), dex_config=None)
    with pytest.raises(RuntimeError):
        await manager.route_and_submit([])
