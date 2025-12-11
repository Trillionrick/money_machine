"""Tests for paper trading execution engine."""

import asyncio

import pytest  # type: ignore[import-not-found]

from src.core.execution import Order, OrderType, Side
from src.live.paper_trading import PaperTradingEngine


@pytest.mark.asyncio
async def test_paper_trading_executes_with_price() -> None:
    engine = PaperTradingEngine(initial_cash=10_000.0, fill_delay_ms=1.0, slippage_bps=0.0)
    engine.update_prices({"AAPL": 100.0})

    order = Order(symbol="AAPL", side=Side.BUY, quantity=10, order_type=OrderType.MARKET)

    await engine.submit_orders([order])
    fill = await asyncio.wait_for(engine.fill_queue.get(), timeout=1.0)

    assert fill.symbol == "AAPL"
    assert engine.positions["AAPL"] == 10
    assert engine.cash < 10_000.0


@pytest.mark.asyncio
async def test_paper_trading_rejects_without_price() -> None:
    engine = PaperTradingEngine(initial_cash=1_000.0, fill_delay_ms=1.0, slippage_bps=0.0)

    order = Order(symbol="MSFT", side=Side.BUY, quantity=1, order_type=OrderType.MARKET)
    await engine.submit_orders([order])

    # No price -> fill_queue should stay empty after delay
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(engine.fill_queue.get(), timeout=0.1)
    assert engine.open_orders == {}


@pytest.mark.asyncio
async def test_paper_trading_sell_flow_and_cleanup() -> None:
    engine = PaperTradingEngine(initial_cash=1_000.0, fill_delay_ms=1.0, slippage_bps=0.0)
    engine.update_prices({"ETH": 200.0})

    buy = Order(symbol="ETH", side=Side.BUY, quantity=2, order_type=OrderType.MARKET)
    await engine.submit_orders([buy])
    await asyncio.wait_for(engine.fill_queue.get(), timeout=1.0)

    sell = Order(symbol="ETH", side=Side.SELL, quantity=1, order_type=OrderType.MARKET)
    await engine.submit_orders([sell])
    await asyncio.wait_for(engine.fill_queue.get(), timeout=1.0)

    assert engine.positions["ETH"] == 1

    # Sell remaining to test zero cleanup
    sell_all = Order(symbol="ETH", side=Side.SELL, quantity=2, order_type=OrderType.MARKET)
    await engine.submit_orders([sell_all])
    await asyncio.wait_for(engine.fill_queue.get(), timeout=1.0)
    assert "ETH" not in engine.positions


@pytest.mark.asyncio
async def test_paper_trading_rejects_insufficient_cash() -> None:
    engine = PaperTradingEngine(initial_cash=10.0, fill_delay_ms=1.0, slippage_bps=0.0)
    engine.update_prices({"BTC": 100.0})

    order = Order(symbol="BTC", side=Side.BUY, quantity=1, order_type=OrderType.MARKET)
    await engine.submit_orders([order])

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(engine.fill_queue.get(), timeout=0.1)
    assert engine.positions == {}


@pytest.mark.asyncio
async def test_cancel_all_orders_and_stream_fills() -> None:
    engine = PaperTradingEngine(initial_cash=1_000.0, fill_delay_ms=50.0, slippage_bps=0.0)
    engine.update_prices({"DOGE": 1.0})

    order = Order(symbol="DOGE", side=Side.BUY, quantity=10, order_type=OrderType.MARKET)
    await engine.submit_orders([order])
    await engine.cancel_all_orders()

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(engine.fill_queue.get(), timeout=0.1)

    # Submit one order and stream fills iterator
    await engine.submit_orders([order])
    fill = await asyncio.wait_for(engine.stream_fills().__anext__(), timeout=1.0)
    assert fill.symbol == "DOGE"
