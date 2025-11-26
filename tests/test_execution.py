"""Tests for execution types and protocols."""

import pytest
from src.core.execution import Fill, Order, OrderType, Side


class TestOrder:
    """Tests for Order struct."""

    def test_create_limit_order(self) -> None:
        """Test creating a limit order."""
        order = Order(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100.0,
            price=150.0,
            order_type=OrderType.LIMIT,
        )

        assert order.symbol == "AAPL"
        assert order.side == Side.BUY
        assert order.quantity == 100.0
        assert order.price == 150.0
        assert order.order_type == OrderType.LIMIT

    def test_create_market_order(self) -> None:
        """Test creating a market order."""
        order = Order(
            symbol="AAPL",
            side=Side.SELL,
            quantity=50.0,
            order_type=OrderType.MARKET,
        )

        assert order.symbol == "AAPL"
        assert order.side == Side.SELL
        assert order.quantity == 50.0
        assert order.price is None
        assert order.order_type == OrderType.MARKET

    def test_order_immutable(self) -> None:
        """Test that orders are immutable."""
        order = Order(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100.0,
            order_type=OrderType.MARKET,
        )

        with pytest.raises(AttributeError):
            order.quantity = 200.0  # type: ignore[misc]


class TestFill:
    """Tests for Fill struct."""

    def test_create_fill(self) -> None:
        """Test creating a fill."""
        fill = Fill(
            order_id="order123",
            symbol="AAPL",
            side=Side.BUY,
            quantity=100.0,
            price=150.5,
            timestamp=1234567890,
            fee=1.0,
        )

        assert fill.order_id == "order123"
        assert fill.symbol == "AAPL"
        assert fill.side == Side.BUY
        assert fill.quantity == 100.0
        assert fill.price == 150.5
        assert fill.timestamp == 1234567890
        assert fill.fee == 1.0

    def test_fill_immutable(self) -> None:
        """Test that fills are immutable."""
        fill = Fill(
            order_id="order123",
            symbol="AAPL",
            side=Side.BUY,
            quantity=100.0,
            price=150.5,
            timestamp=1234567890,
        )

        with pytest.raises(AttributeError):
            fill.price = 151.0  # type: ignore[misc]

    def test_default_fee(self) -> None:
        """Test that fee defaults to 0.0."""
        fill = Fill(
            order_id="order123",
            symbol="AAPL",
            side=Side.BUY,
            quantity=100.0,
            price=150.5,
            timestamp=1234567890,
        )

        assert fill.fee == 0.0


class TestSide:
    """Tests for Side enum."""

    def test_buy_side(self) -> None:
        """Test BUY side."""
        assert Side.BUY == "buy"

    def test_sell_side(self) -> None:
        """Test SELL side."""
        assert Side.SELL == "sell"


class TestOrderType:
    """Tests for OrderType enum."""

    def test_limit_type(self) -> None:
        """Test LIMIT order type."""
        assert OrderType.LIMIT == "limit"

    def test_market_type(self) -> None:
        """Test MARKET order type."""
        assert OrderType.MARKET == "market"
