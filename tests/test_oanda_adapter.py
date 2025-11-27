"""Tests for OandaAdapter validation helpers."""

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from pydantic import SecretStr

from src.brokers.oanda_adapter import OandaAdapter
from src.brokers.oanda_config import OandaConfig, OandaEnvironment
from src.core.execution import Order, OrderRejectedError, OrderType, Side
from src.core.execution import InsufficientFundsError


@pytest_asyncio.fixture
async def oanda_adapter() -> Any:
    config = OandaConfig(
        oanda_token=SecretStr("token"),
        oanda_account_id="001-001-1234567-001",
        oanda_environment=OandaEnvironment.PRACTICE,
    )
    adapter = OandaAdapter(config)
    adapter._instrument_cache["EUR_USD"] = {
        "name": "EUR_USD",
        "tradeUnitsPrecision": 0,
        "minimumTradeSize": "1",
        "marginRate": "0.05",
    }
    yield adapter
    await adapter.close()


@pytest.mark.asyncio
async def test_prepare_units_rounds_and_validates(oanda_adapter: OandaAdapter) -> None:
    order = Order(
        symbol="EUR/USD",
        side=Side.BUY,
        quantity=1000.6,
        order_type=OrderType.MARKET,
    )

    units, precision = await oanda_adapter._prepare_units(order, "EUR_USD")

    assert units == Decimal("1001")
    assert precision == 0

    tiny_order = Order(
        symbol="EUR/USD",
        side=Side.BUY,
        quantity=0.2,
        order_type=OrderType.MARKET,
    )

    with pytest.raises(OrderRejectedError):
        await oanda_adapter._prepare_units(tiny_order, "EUR_USD")


@pytest.mark.asyncio
async def test_margin_precheck_blocks_when_insufficient(oanda_adapter: OandaAdapter, monkeypatch: Any) -> None:
    monkeypatch.setattr(
        oanda_adapter,
        "_get_reference_price",
        AsyncMock(return_value=Decimal("1.50")),
    )
    monkeypatch.setattr(
        oanda_adapter,
        "get_account",
        AsyncMock(
            return_value={
                "margin_available": Decimal("100"),
                "currency": "USD",
                "balance": Decimal("0"),
                "unrealized_pl": Decimal("0"),
                "nav": Decimal("0"),
                "margin_used": Decimal("0"),
                "position_value": Decimal("0"),
            }
        ),
    )

    with pytest.raises(InsufficientFundsError):
        await oanda_adapter._precheck_margin("EUR_USD", Decimal("4000"), None)
