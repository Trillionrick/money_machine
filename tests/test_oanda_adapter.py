"""Tests for OandaAdapter validation helpers.

2025 best practices:
- Modern pytest-asyncio fixture patterns
- Proper Pydantic v2 field name usage (not env var names)
- Comprehensive type hints throughout
- Explicit test descriptions in docstrings
- Type-safe mock configurations
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock

import pytest  # type: ignore[import-not-found]
import pytest_asyncio  # type: ignore[import-not-found]
from pydantic import SecretStr

from src.brokers.oanda_adapter import OandaAdapter
from src.brokers.oanda_config import OandaConfig, OandaEnvironment
from src.core.execution import (
    InsufficientFundsError,
    Order,
    OrderRejectedError,
    OrderType,
    Side,
)


@pytest_asyncio.fixture
async def oanda_adapter() -> AsyncIterator[OandaAdapter]:
    """Create OandaAdapter instance for testing with mocked configuration.

    Uses Pydantic v2 field names (not environment variable names):
    - oanda_token (not OANDA_API_TOKEN)
    - oanda_account_id (not OANDA_ACCOUNT_ID)
    - oanda_environment (not OANDA_ENVIRONMENT)

    Yields:
        Configured OandaAdapter instance with EUR_USD instrument cached

    Note:
        Automatically closes adapter after test completion
    """
    config = OandaConfig(
        oanda_token=SecretStr("test_token_practice_123"),
        oanda_account_id="001-001-1234567-001",
        oanda_environment=OandaEnvironment.PRACTICE,
    )
    adapter = OandaAdapter(config)

    # Pre-populate instrument cache for EUR_USD to avoid API calls
    adapter._instrument_cache["EUR_USD"] = {
        "name": "EUR_USD",
        "tradeUnitsPrecision": 0,
        "minimumTradeSize": "1",
        "marginRate": "0.05",
    }

    yield adapter

    # Cleanup: Close adapter connections
    await adapter.close()


@pytest.mark.asyncio
async def test_prepare_units_rounds_and_validates(oanda_adapter: OandaAdapter) -> None:
    """Test that _prepare_units correctly rounds quantities and validates minimum size.

    Verifies:
    1. Quantity 1000.6 rounds to 1001 units (precision 0)
    2. Sub-minimum orders (0.2 < 1.0) raise OrderRejectedError
    """
    # Test case 1: Normal order with rounding
    order = Order(
        symbol="EUR/USD",
        side=Side.BUY,
        quantity=1000.6,
        order_type=OrderType.MARKET,
    )

    units, precision = await oanda_adapter._prepare_units(order, "EUR_USD")

    assert units == Decimal("1001"), f"Expected 1001 units, got {units}"
    assert precision == 0, f"Expected precision 0, got {precision}"

    # Test case 2: Order below minimum size should be rejected
    tiny_order = Order(
        symbol="EUR/USD",
        side=Side.BUY,
        quantity=0.2,  # Below minimumTradeSize of 1
        order_type=OrderType.MARKET,
    )

    with pytest.raises(OrderRejectedError, match="below minimum"):
        await oanda_adapter._prepare_units(tiny_order, "EUR_USD")


@pytest.mark.asyncio
async def test_margin_precheck_blocks_when_insufficient(
    oanda_adapter: OandaAdapter,
    monkeypatch: Any,
) -> None:
    """Test that _precheck_margin raises InsufficientFundsError when margin is inadequate.

    Scenario:
    - Account has $100 available margin
    - EUR_USD price is $1.50
    - Attempted position size: 4000 units
    - Required margin: 4000 * 1.50 * 0.05 = $300
    - Result: Should raise InsufficientFundsError ($300 > $100)

    Args:
        oanda_adapter: Fixture providing configured adapter
        monkeypatch: pytest monkeypatch fixture for mocking
    """
    # Mock reference price for EUR_USD
    monkeypatch.setattr(
        oanda_adapter,
        "_get_reference_price",
        AsyncMock(return_value=Decimal("1.50")),
    )

    # Mock account state with limited available margin
    mock_account_data: dict[str, Decimal | str] = {
        "margin_available": Decimal("100"),  # Only $100 available
        "currency": "USD",
        "balance": Decimal("0"),
        "unrealized_pl": Decimal("0"),
        "nav": Decimal("0"),
        "margin_used": Decimal("0"),
        "position_value": Decimal("0"),
    }

    monkeypatch.setattr(
        oanda_adapter,
        "get_account",
        AsyncMock(return_value=mock_account_data),
    )

    # Test 1: Attempt with price_hint=None (uses _get_reference_price mock)
    # Should raise InsufficientFundsError: $300 required > $100 available
    with pytest.raises(
        InsufficientFundsError,
        match="Insufficient margin",
    ):
        await oanda_adapter._precheck_margin(
            instrument="EUR_USD",
            units=Decimal("4000"),
            price_hint=None,  # Falls back to mocked _get_reference_price (1.50)
        )

    # Test 2: Attempt with explicit price_hint (same result expected)
    # Required margin: 4000 * 2.00 * 0.05 = $400 > $100 available
    with pytest.raises(
        InsufficientFundsError,
        match="Insufficient margin",
    ):
        await oanda_adapter._precheck_margin(
            instrument="EUR_USD",
            units=Decimal("4000"),
            price_hint=2.00,  # Explicit price provided (no fallback to _get_reference_price)
        )
