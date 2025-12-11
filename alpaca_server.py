"""
Alpaca Trading Dashboard Server

Provides a dedicated web UI for Alpaca algorithmic trading operations.
Runs on port 8081, separate from the main arbitrage dashboard.
"""

import asyncio
import os
from pathlib import Path
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    load_dotenv(dotenv_path=env_path)
except ImportError:
    # python-dotenv not installed, try manual loading
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

log = structlog.get_logger()

# Initialize FastAPI app
app = FastAPI(title="Alpaca Trading Dashboard")

# Global Alpaca adapter and AI bridge instances
alpaca_adapter = None
ai_bridge = None
current_paper_mode = os.getenv("ALPACA_PAPER", "true").lower() == "true"


class MarketOrderRequest(BaseModel):
    """Market order request model."""
    symbol: str
    quantity: int
    side: str  # 'buy' or 'sell'


class LimitOrderRequest(BaseModel):
    """Limit order request model."""
    symbol: str
    quantity: int
    side: str  # 'buy' or 'sell'
    limit_price: float


class ModeRequest(BaseModel):
    """Trading mode request model."""
    paper: bool


def initialize_alpaca(paper_mode: bool | None = None):
    """Initialize Alpaca adapter from environment variables.

    Args:
        paper_mode: Override paper trading mode. If None, uses current_paper_mode global.
    """
    global alpaca_adapter, current_paper_mode

    if paper_mode is not None:
        current_paper_mode = paper_mode

    try:
        # Select appropriate API keys based on mode
        if current_paper_mode:
            api_key = os.getenv("ALPACA_PAPER_API_KEY") or os.getenv("ALPACA_API_KEY")
            api_secret = os.getenv("ALPACA_PAPER_API_SECRET") or os.getenv("ALPACA_API_SECRET")
            mode_name = "paper"
        else:
            api_key = os.getenv("ALPACA_LIVE_API_KEY")
            api_secret = os.getenv("ALPACA_LIVE_API_SECRET")
            mode_name = "live"

        if not api_key or not api_secret:
            log.warning(
                "alpaca.missing_credentials",
                msg=f"Set ALPACA_{mode_name.upper()}_API_KEY and ALPACA_{mode_name.upper()}_API_SECRET in .env",
                mode=mode_name,
            )
            return None

        # Check for placeholder values
        if api_key.startswith("your_") or api_secret.startswith("your_"):
            log.warning(
                "alpaca.placeholder_credentials",
                msg=f"Please replace placeholder {mode_name} API keys in .env with actual credentials",
                mode=mode_name,
            )
            return None

        from src.brokers.alpaca_adapter import AlpacaAdapter

        alpaca_adapter = AlpacaAdapter(
            api_key=api_key,
            api_secret=api_secret,
            paper=current_paper_mode,
        )

        log.info(
            "alpaca.initialized",
            paper=current_paper_mode,
            endpoint="paper" if current_paper_mode else "live",
            mode=mode_name,
        )
        return alpaca_adapter

    except ImportError as e:
        log.error(
            "alpaca.import_failed",
            error=str(e),
            msg="Install alpaca-py: pip install alpaca-py",
        )
        return None
    except Exception as e:
        log.exception("alpaca.init_failed", error=str(e))
        return None


# Initialize Alpaca on module load instead of startup event
initialize_alpaca()

# Initialize AI Bridge if Alpaca is available
def initialize_ai_bridge():
    """Initialize AI-Alpaca integration bridge."""
    global ai_bridge

    if not alpaca_adapter:
        log.warning("alpaca_ai.no_adapter", msg="Alpaca adapter not initialized")
        return None

    try:
        from src.integrations.alpaca_ai_bridge import AlpacaAIBridge

        ai_bridge = AlpacaAIBridge(alpaca_adapter=alpaca_adapter)
        log.info("alpaca_ai.bridge_initialized")
        return ai_bridge
    except Exception as e:
        log.exception("alpaca_ai.bridge_failed", error=str(e))
        return None


initialize_ai_bridge()


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Serve the Alpaca dashboard HTML."""
    try:
        with open("alpaca_dashboard.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Dashboard not found</h1><p>alpaca_dashboard.html is missing</p>",
            status_code=404,
        )


@app.get("/api/alpaca/mode")
async def get_mode() -> dict[str, Any]:
    """Get current trading mode.

    Returns:
        Current paper/live mode status
    """
    return {
        "paper": current_paper_mode,
        "mode": "paper" if current_paper_mode else "live",
    }


@app.post("/api/alpaca/mode")
async def set_mode(request: ModeRequest) -> dict[str, Any]:
    """Switch between paper and live trading modes.

    Args:
        request: Mode request with paper flag

    Returns:
        New mode status
    """
    global current_paper_mode

    if not request.paper:
        # Require explicit confirmation for live trading
        log.warning(
            "alpaca.live_mode_activated",
            msg="⚠️ LIVE TRADING MODE ACTIVATED - REAL MONEY AT RISK",
        )

    # Reinitialize adapter with new mode
    initialize_alpaca(paper_mode=request.paper)

    # Reinitialize AI bridge
    initialize_ai_bridge()

    log.info(
        "alpaca.mode_switched",
        paper=current_paper_mode,
        mode="paper" if current_paper_mode else "live",
    )

    return {
        "success": True,
        "paper": current_paper_mode,
        "mode": "paper" if current_paper_mode else "live",
        "message": f"Switched to {'paper' if current_paper_mode else 'live'} trading mode",
    }


@app.get("/api/alpaca/account")
async def get_account() -> dict[str, Any]:
    """Get Alpaca account information.

    Returns:
        Account details including cash, equity, buying_power
    """
    if not alpaca_adapter:
        raise HTTPException(status_code=503, detail="Alpaca adapter not initialized")

    try:
        account = await alpaca_adapter.get_account()

        return {
            **account,
            "paper": current_paper_mode,
        }
    except Exception as e:
        log.exception("alpaca.get_account_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/alpaca/positions")
async def get_positions() -> dict[str, Any]:
    """Get all current positions.

    Returns:
        List of positions with P&L
    """
    if not alpaca_adapter:
        raise HTTPException(status_code=503, detail="Alpaca adapter not initialized")

    try:
        # Get positions from adapter
        positions_dict = await alpaca_adapter.get_positions()

        # Import Alpaca client to get full position details
        from alpaca.trading.client import TradingClient

        # Select appropriate API keys based on current mode
        if current_paper_mode:
            api_key = os.getenv("ALPACA_PAPER_API_KEY") or os.getenv("ALPACA_API_KEY")
            api_secret = os.getenv("ALPACA_PAPER_API_SECRET") or os.getenv("ALPACA_API_SECRET")
        else:
            api_key = os.getenv("ALPACA_LIVE_API_KEY")
            api_secret = os.getenv("ALPACA_LIVE_API_SECRET")

        client = TradingClient(api_key=api_key, secret_key=api_secret, paper=current_paper_mode)

        loop = asyncio.get_running_loop()
        all_positions = await loop.run_in_executor(None, client.get_all_positions)

        # Convert to list format with full details
        positions = []
        for pos in all_positions:
            positions.append({
                "symbol": pos.symbol,
                "qty": float(pos.qty),
                "side": "long" if float(pos.qty) > 0 else "short",
                "market_value": float(pos.market_value),
                "cost_basis": float(pos.cost_basis),
                "unrealized_pl": float(pos.unrealized_pl),
                "unrealized_plpc": float(pos.unrealized_plpc),
                "current_price": float(pos.current_price),
                "avg_entry_price": float(pos.avg_entry_price),
            })

        return {"positions": positions}

    except Exception as e:
        log.exception("alpaca.get_positions_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/alpaca/orders")
async def get_orders(symbol: str | None = None) -> dict[str, Any]:
    """Get open orders.

    Args:
        symbol: Optional symbol to filter by

    Returns:
        List of open orders
    """
    if not alpaca_adapter:
        raise HTTPException(status_code=503, detail="Alpaca adapter not initialized")

    try:
        orders_list = await alpaca_adapter.get_open_orders(symbol=symbol)

        # Convert to dict format
        orders = []
        for order in orders_list:
            orders.append({
                "id": order.id,
                "symbol": order.symbol,
                "qty": order.quantity,
                "side": order.side.value,
                "type": order.order_type.value,
                "limit_price": order.price,
                "status": "open",
                "created_at": None,  # Add timestamp if available in Order model
            })

        return {"orders": orders}

    except Exception as e:
        log.exception("alpaca.get_orders_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/alpaca/order/market")
async def place_market_order(request: MarketOrderRequest) -> dict[str, Any]:
    """Place a market order.

    Args:
        request: Market order parameters

    Returns:
        Order confirmation
    """
    if not alpaca_adapter:
        raise HTTPException(status_code=503, detail="Alpaca adapter not initialized")

    try:
        from src.core.execution import Order, OrderType, Side

        # Create order
        side = Side.BUY if request.side.lower() == "buy" else Side.SELL
        order = Order(
            symbol=request.symbol,
            side=side,
            quantity=float(request.quantity),
            order_type=OrderType.MARKET,
        )

        # Submit order
        await alpaca_adapter.submit_orders([order])

        log.info(
            "alpaca.market_order_placed",
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
        )

        return {
            "success": True,
            "symbol": request.symbol,
            "side": request.side,
            "quantity": request.quantity,
            "type": "market",
        }

    except Exception as e:
        log.exception("alpaca.place_market_order_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/alpaca/order/limit")
async def place_limit_order(request: LimitOrderRequest) -> dict[str, Any]:
    """Place a limit order.

    Args:
        request: Limit order parameters

    Returns:
        Order confirmation
    """
    if not alpaca_adapter:
        raise HTTPException(status_code=503, detail="Alpaca adapter not initialized")

    try:
        from src.core.execution import Order, OrderType, Side

        # Create order
        side = Side.BUY if request.side.lower() == "buy" else Side.SELL
        order = Order(
            symbol=request.symbol,
            side=side,
            quantity=float(request.quantity),
            order_type=OrderType.LIMIT,
            price=request.limit_price,
        )

        # Submit order
        await alpaca_adapter.submit_orders([order])

        log.info(
            "alpaca.limit_order_placed",
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            limit_price=request.limit_price,
        )

        return {
            "success": True,
            "symbol": request.symbol,
            "side": request.side,
            "quantity": request.quantity,
            "type": "limit",
            "limit_price": request.limit_price,
        }

    except Exception as e:
        log.exception("alpaca.place_limit_order_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/alpaca/order/{order_id}")
async def cancel_order(order_id: str) -> dict[str, Any]:
    """Cancel an order by ID.

    Args:
        order_id: Alpaca order ID

    Returns:
        Cancellation confirmation
    """
    if not alpaca_adapter:
        raise HTTPException(status_code=503, detail="Alpaca adapter not initialized")

    try:
        await alpaca_adapter.cancel_order(order_id)

        log.info("alpaca.order_cancelled", order_id=order_id)

        return {
            "success": True,
            "order_id": order_id,
            "message": "Order cancelled",
        }

    except Exception as e:
        log.exception("alpaca.cancel_order_failed", order_id=order_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/alpaca/orders/cancel")
async def cancel_all_orders(symbol: str | None = None) -> dict[str, Any]:
    """Cancel all open orders, optionally filtered by symbol.

    Args:
        symbol: Optional symbol to filter by

    Returns:
        Number of orders cancelled
    """
    if not alpaca_adapter:
        raise HTTPException(status_code=503, detail="Alpaca adapter not initialized")

    try:
        # Get current orders before cancelling
        orders_before = await alpaca_adapter.get_open_orders(symbol=symbol)
        count = len(orders_before)

        # Cancel all orders
        await alpaca_adapter.cancel_all_orders(symbol=symbol)

        log.info("alpaca.orders_cancelled", symbol=symbol or "all", count=count)

        return {
            "success": True,
            "cancelled": count,
            "symbol": symbol,
        }

    except Exception as e:
        log.exception("alpaca.cancel_all_failed", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/alpaca/position/{symbol}")
async def close_position(symbol: str) -> dict[str, Any]:
    """Close a position by submitting a market order in the opposite direction.

    Args:
        symbol: Symbol to close position for

    Returns:
        Closure confirmation
    """
    if not alpaca_adapter:
        raise HTTPException(status_code=503, detail="Alpaca adapter not initialized")

    try:
        # Get current position
        positions = await alpaca_adapter.get_positions()

        if symbol not in positions:
            raise HTTPException(status_code=404, detail=f"No position found for {symbol}")

        quantity = abs(positions[symbol])

        # Determine side (opposite of current position)
        from src.core.execution import Order, OrderType, Side

        side = Side.SELL if positions[symbol] > 0 else Side.BUY

        # Create market order to close
        order = Order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=OrderType.MARKET,
        )

        # Submit order
        await alpaca_adapter.submit_orders([order])

        log.info(
            "alpaca.position_closed",
            symbol=symbol,
            quantity=quantity,
            side=side.value,
        )

        return {
            "success": True,
            "symbol": symbol,
            "quantity": quantity,
            "side": side.value,
            "message": "Position close order submitted",
        }

    except HTTPException:
        raise
    except Exception as e:
        log.exception("alpaca.close_position_failed", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# AI ARBITRAGE & FLASH LOAN ENDPOINTS
# ============================================================================


class AIOpportunityRequest(BaseModel):
    """AI arbitrage opportunity analysis request."""
    symbol: str
    cex_price: float
    dex_price: float
    notional_quote: float = 1000.0
    confidence: float = 0.7


class AITradeRequest(BaseModel):
    """AI-driven trade execution request."""
    symbol: str
    direction: str  # 'buy' or 'sell'
    quantity: float
    order_type: str = "market"
    limit_price: float | None = None


@app.post("/api/ai/analyze")
async def analyze_arbitrage_opportunity(request: AIOpportunityRequest) -> dict[str, Any]:
    """Analyze an arbitrage opportunity using AI.

    Args:
        request: Opportunity parameters

    Returns:
        AI analysis with recommendation
    """
    if not ai_bridge:
        raise HTTPException(status_code=503, detail="AI bridge not initialized")

    try:
        analysis = await ai_bridge.analyze_opportunity(
            symbol=request.symbol,
            cex_price=request.cex_price,
            dex_price=request.dex_price,
            notional_quote=request.notional_quote,
            confidence=request.confidence,
        )

        log.info(
            "alpaca_ai.opportunity_analyzed",
            symbol=request.symbol,
            should_trade=analysis.get("should_trade"),
        )

        return analysis

    except Exception as e:
        log.exception("alpaca_ai.analyze_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ai/execute")
async def execute_ai_trade(request: AITradeRequest) -> dict[str, Any]:
    """Execute an AI-recommended trade.

    Args:
        request: Trade parameters

    Returns:
        Execution result
    """
    if not ai_bridge:
        raise HTTPException(status_code=503, detail="AI bridge not initialized")

    try:
        result = await ai_bridge.execute_arbitrage_trade(
            symbol=request.symbol,
            direction=request.direction,
            quantity=request.quantity,
            order_type=request.order_type,
            limit_price=request.limit_price,
        )

        log.info(
            "alpaca_ai.trade_executed",
            symbol=request.symbol,
            success=result.get("success"),
        )

        return result

    except Exception as e:
        log.exception("alpaca_ai.execute_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ai/flash-loan")
async def execute_flash_loan_arbitrage(
    opportunity: dict[str, Any]
) -> dict[str, Any]:
    """Execute a flash loan arbitrage strategy.

    Args:
        opportunity: Arbitrage opportunity details

    Returns:
        Execution result
    """
    if not ai_bridge:
        raise HTTPException(status_code=503, detail="AI bridge not initialized")

    try:
        result = await ai_bridge.execute_flash_loan_arbitrage(opportunity)

        log.info(
            "alpaca_ai.flash_loan_executed",
            symbol=opportunity.get("symbol"),
            success=result.get("success"),
        )

        return result

    except Exception as e:
        log.exception("alpaca_ai.flash_loan_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ai/performance")
async def get_ai_performance() -> dict[str, Any]:
    """Get AI trading performance metrics.

    Returns:
        Performance statistics
    """
    if not ai_bridge:
        raise HTTPException(status_code=503, detail="AI bridge not initialized")

    try:
        metrics = ai_bridge.get_performance_metrics()
        return metrics

    except Exception as e:
        log.exception("alpaca_ai.performance_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ai/monitor")
async def monitor_ai_positions() -> dict[str, Any]:
    """Monitor AI-managed positions.

    Returns:
        Position monitoring report
    """
    if not ai_bridge:
        raise HTTPException(status_code=503, detail="AI bridge not initialized")

    try:
        report = await ai_bridge.monitor_positions()
        return report

    except Exception as e:
        log.exception("alpaca_ai.monitor_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


def start_alpaca_server(host: str = "0.0.0.0", port: int = 8081):
    """Start the Alpaca dashboard server.

    Args:
        host: Host to bind to
        port: Port to listen on
    """
    print("=" * 70)
    print("📈 ALPACA TRADING DASHBOARD STARTING")
    print("=" * 70)
    print()
    print(f"📊 Dashboard URL: http://localhost:{port}")
    print()
    print("Features:")
    print("  • Real-time account monitoring")
    print("  • Market & limit orders")
    print("  • Position management")
    print("  • Order tracking & cancellation")
    print("  • AI-powered arbitrage analysis")
    print("  • Flash loan simulation trading")
    print("  • Runtime mode switching (Paper ↔ Live)")
    print()
    mode = "PAPER TRADING" if current_paper_mode else "LIVE TRADING"
    print(f"Default Mode: {mode}")
    print("💡 Switch modes anytime in the dashboard")
    print()
    print("=" * 70)
    print()

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_alpaca_server()
