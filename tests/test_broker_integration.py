"""Recorded integration-style tests with vcrpy cassettes.

These run without live network by replaying captured HTTP interactions.
Set RUN_INTEGRATION=1 to allow re-recording with real endpoints/creds.
"""
# pyright: reportMissingImports=false

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest
    import vcr  # type: ignore[import-not-found]

try:
    import pytest  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - dev dependency missing
    pytest = None  # type: ignore[assignment]

try:
    import vcr  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - dev dependency missing
    vcr = None  # type: ignore[assignment]

from pydantic import SecretStr

from src.brokers.kraken_adapter import KrakenAdapter
from src.brokers.oanda_adapter import OandaAdapter
from src.brokers.oanda_config import OandaConfig, OandaEnvironment


if vcr is None:
    pytestmark: list = []  # No pytest/vcr available; tests become no-ops
    cassette = None
else:
    pytestmark = []
    cassette = vcr.VCR(
        cassette_library_dir="tests/cassettes",
        record_mode="none" if os.getenv("RUN_INTEGRATION") != "1" else "once",
        filter_headers=["Authorization"],
    )
async_mark = (lambda fn: fn) if pytest is None else pytest.mark.asyncio


@((cassette.use_cassette("kraken_time.yaml") if cassette else (lambda fn: fn)))
@async_mark  # type: ignore[misc]
async def test_kraken_public_time_vcr() -> None:
    if pytest is None or vcr is None:
        return
    adapter = KrakenAdapter(api_key="k", api_secret="a2F5", base_url="https://api.kraken.com")
    server_time = await adapter.get_server_time()
    assert isinstance(server_time, int)
    assert server_time > 0


@((cassette.use_cassette("oanda_account.yaml") if cassette else (lambda fn: fn)))
@async_mark  # type: ignore[misc]
async def test_oanda_account_vcr(monkeypatch=None) -> None:
    if pytest is None or vcr is None:
        return
    assert monkeypatch is not None, "pytest monkeypatch fixture required"
    monkeypatch.setenv("OANDA_API_TOKEN", "dummy")
    monkeypatch.setenv("OANDA_ACCOUNT_ID", "001-001-1234567-001")
    monkeypatch.setenv("OANDA_ENVIRONMENT", "practice")
    config = OandaConfig.model_validate(
        {
            "OANDA_API_TOKEN": "dummy",
            "OANDA_ACCOUNT_ID": "001-001-1234567-001",
            "OANDA_ENVIRONMENT": OandaEnvironment.PRACTICE.value,
        }
    )
    adapter = OandaAdapter(config)
    account = await adapter.get_account()
    assert account["currency"] == "USD"
    assert account["nav"] >= 0
    await adapter.close()
