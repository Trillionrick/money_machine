"""Sanity checks for ConnectionManager wiring."""

import pytest
from pydantic import SecretStr

from src.brokers.connection_manager import ConnectionManager
from src.brokers.credentials import BrokerCredentials


@pytest.mark.asyncio
async def test_connection_manager_initializes_router(monkeypatch: pytest.MonkeyPatch) -> None:
    creds = BrokerCredentials(
        binance_api_key=SecretStr("k"),
        binance_api_secret=SecretStr("s"),
        kraken_api_key=SecretStr("k"),
        kraken_api_secret=SecretStr("s"),
        oanda_api_key=SecretStr("tok"),  # type: ignore[arg-type]
        oanda_account_id="001-001-1234567-001",
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


@pytest.mark.asyncio
async def test_route_and_submit_requires_init() -> None:
    manager = ConnectionManager(BrokerCredentials(), dex_config=None)
    with pytest.raises(RuntimeError):
        await manager.route_and_submit([])
