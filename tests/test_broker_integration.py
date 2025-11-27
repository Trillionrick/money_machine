"""Recorded integration-style tests with vcrpy cassettes.

These run without live network by replaying captured HTTP interactions.
Set RUN_INTEGRATION=1 to allow re-recording with real endpoints/creds.
"""

import os

import pytest
import vcr
from pydantic import SecretStr

from src.brokers.kraken_adapter import KrakenAdapter
from src.brokers.oanda_adapter import OandaAdapter
from src.brokers.oanda_config import OandaConfig, OandaEnvironment


cassette = vcr.VCR(
    cassette_library_dir="tests/cassettes",
    record_mode="none" if os.getenv("RUN_INTEGRATION") != "1" else "once",
    filter_headers=["Authorization"],
)


@cassette.use_cassette("kraken_time.yaml")
@pytest.mark.asyncio
async def test_kraken_public_time_vcr() -> None:
    adapter = KrakenAdapter(api_key="k", api_secret="a2F5", base_url="https://api.kraken.com")
    server_time = await adapter.get_server_time()
    assert isinstance(server_time, int)
    assert server_time > 0


@cassette.use_cassette("oanda_account.yaml")
@pytest.mark.asyncio
async def test_oanda_account_vcr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OANDA_API_TOKEN", "dummy")
    monkeypatch.setenv("OANDA_ACCOUNT_ID", "001-001-1234567-001")
    monkeypatch.setenv("OANDA_ENVIRONMENT", "practice")
    config = OandaConfig(
        oanda_token=SecretStr("dummy"),
        oanda_account_id="001-001-1234567-001",
        oanda_environment=OandaEnvironment.PRACTICE,
    )
    adapter = OandaAdapter(config)
    account = await adapter.get_account()
    assert account["currency"] == "USD"
    assert account["nav"] >= 0
    await adapter.close()
