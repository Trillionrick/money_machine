"""
Web server for arbitrage scanner dashboard.

Provides a real-time web UI to monitor and control the arbitrage system.
"""

import asyncio
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn
from web3 import Web3

from run_live_arbitrage import ArbitrageSystem
from src.live.flash_arb_runner import FlashArbitrageRunner

app = FastAPI(title="Arbitrage Scanner Dashboard")

# Global state
scanner_task: Optional[asyncio.Task] = None
stats_task: Optional[asyncio.Task] = None
scanner_system: Optional[ArbitrageSystem] = None
scanner_running = False
scanner_started_at: Optional[datetime] = None
opportunities: List[Dict] = []
trades: List[Dict] = []
system_stats = {
    "uptime_seconds": 0,
    "opportunities_found": 0,
    "trades_executed": 0,
    "total_profit_eth": 0.0,
    "wallet_balance_eth": 0.0,
    "gas_price_gwei": 0.0,
    "status": "stopped",
}
wallets = {
    "metamask": {"address": os.getenv("METAMASK_WALLET_ADDRESS", "").strip(), "balance_eth": None},
    "rainbow": {"address": os.getenv("RAINBOW_WALLET_ADDRESS", "").strip(), "balance_eth": None},
}
rpc_url = os.getenv("ETH_RPC_URL") or os.getenv("ETHEREUM_RPC_URL") or ""
_web3_client: Optional[Web3] = None

# WebSocket connections
active_connections: List[WebSocket] = []


async def broadcast_update(data: dict):
    """Broadcast update to all connected WebSocket clients."""
    for connection in active_connections:
        try:
            await connection.send_json(data)
        except:
            pass


def get_web3() -> Optional[Web3]:
    """Lazy-init Web3 client using configured RPC URL."""
    global _web3_client

    if not rpc_url:
        return None

    if _web3_client is None:
        _web3_client = Web3(Web3.HTTPProvider(rpc_url))

    if not _web3_client.is_connected():
        return None

    return _web3_client


async def refresh_wallet_balances() -> None:
    """Refresh balances for configured wallets."""
    web3 = get_web3()
    if not web3:
        return

    for key, wallet in wallets.items():
        address = wallet.get("address") or ""
        if not address:
            wallets[key]["balance_eth"] = None
            continue

        try:
            checksum = Web3.to_checksum_address(address)
            balance_wei = web3.eth.get_balance(checksum)
            wallets[key]["balance_eth"] = float(web3.from_wei(balance_wei, "ether"))
        except Exception:
            wallets[key]["balance_eth"] = None

    # Aggregate visible balance for quick display
    balances = [bal for bal in (wallets["metamask"]["balance_eth"], wallets["rainbow"]["balance_eth"]) if bal is not None]
    if balances:
        system_stats["wallet_balance_eth"] = sum(balances)


async def refresh_network_stats() -> None:
    """Refresh gas price and wallet balances."""
    web3 = get_web3()
    if web3:
        try:
            gas_price = web3.eth.gas_price
            system_stats["gas_price_gwei"] = float(web3.from_wei(gas_price, "gwei"))
        except Exception:
            pass

    await refresh_wallet_balances()


def _record_event(collection: List[Dict], item: Dict, limit: int = 50) -> None:
    """Append and trim history for opportunities/trades."""
    collection.append(item)
    if len(collection) > limit:
        del collection[:-limit]


async def stats_loop():
    """Continuously update uptime and network stats."""
    while scanner_running:
        if scanner_started_at:
            delta = datetime.now(timezone.utc) - scanner_started_at
            system_stats["uptime_seconds"] = int(delta.total_seconds())

        await refresh_network_stats()

        await broadcast_update({
            "type": "stats_update",
            "data": system_stats,
            "wallets": wallets,
        })

        await asyncio.sleep(5)


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Serve the main dashboard HTML."""
    with open("web_dashboard.html", "r") as f:
        return f.read()


@app.get("/api/status")
async def get_status():
    """Get current system status."""
    return {
        "running": scanner_running,
        "stats": system_stats,
        "wallets": wallets,
        "opportunities": opportunities[-10:],  # Last 10
        "trades": trades[-10:],  # Last 10
    }


@app.get("/api/wallets")
async def get_wallets():
    """Return configured wallet metadata and balances."""
    await refresh_wallet_balances()
    return {"wallets": wallets, "rpc_url": rpc_url}


@app.post("/api/start")
async def start_scanner(config: dict = None):
    """Start the arbitrage scanner."""
    global scanner_task, stats_task, scanner_system, scanner_running, scanner_started_at

    if scanner_running:
        return {"error": "Scanner already running"}

    try:
        # Create system with configuration
        dry_run = config.get("dry_run", True) if config else True
        enable_flash = config.get("enable_flash", True) if config else True
        auto_execute = config.get("auto_execute", False) if config else False

        scanner_system = ArbitrageSystem(
            dry_run=dry_run,
            enable_flash_loans=enable_flash,
        )

        # Toggle execution based on UI controls
        scanner_system.config.enable_execution = auto_execute and not dry_run

        async def handle_opportunity(event: dict) -> None:
            system_stats["opportunities_found"] += 1
            system_stats["last_opportunity_at"] = datetime.now(timezone.utc).isoformat()
            _record_event(opportunities, event)
            await broadcast_update({"type": "opportunity", "data": event})

        async def handle_trade(event: dict) -> None:
            system_stats["trades_executed"] += 1
            system_stats["last_trade_at"] = datetime.now(timezone.utc).isoformat()
            _record_event(trades, event)
            await broadcast_update({"type": "trade", "data": event})

        async def price_fetcher(symbol: str):
            return await scanner_system.price_fetcher.get_price(symbol)

        runner = FlashArbitrageRunner(
            router=scanner_system.router,
            dex=scanner_system.dex,
            price_fetcher=price_fetcher,
            token_addresses=scanner_system.token_addresses,
            config=scanner_system.config,
            on_opportunity=handle_opportunity,
            on_trade=handle_trade,
        )

        # Start scanner in background
        scanner_running = True
        scanner_started_at = datetime.now(timezone.utc)
        system_stats["status"] = "running"
        system_stats["start_time"] = scanner_started_at.isoformat()

        scanner_task = asyncio.create_task(runner.run(scanner_system.symbols))
        stats_task = asyncio.create_task(stats_loop())

        await broadcast_update({
            "type": "status",
            "running": True,
            "message": "Scanner started",
            "wallets": wallets,
        })

        return {
            "success": True,
            "message": "Scanner started",
            "dry_run": dry_run,
            "enable_flash": enable_flash,
            "auto_execute": auto_execute,
        }

    except Exception as e:
        return {"error": str(e)}


@app.post("/api/stop")
async def stop_scanner():
    """Stop the arbitrage scanner."""
    global scanner_task, stats_task, scanner_running

    if not scanner_running:
        return {"error": "Scanner not running"}

    if scanner_task:
        scanner_task.cancel()
        try:
            await scanner_task
        except asyncio.CancelledError:
            pass

    if stats_task:
        stats_task.cancel()
        try:
            await stats_task
        except asyncio.CancelledError:
            pass

    scanner_running = False
    system_stats["status"] = "stopped"
    system_stats["uptime_seconds"] = 0
    system_stats["gas_price_gwei"] = 0.0
    system_stats["wallet_balance_eth"] = 0.0

    await broadcast_update({
        "type": "status",
        "running": False,
        "message": "Scanner stopped"
    })

    return {"success": True, "message": "Scanner stopped"}


@app.get("/api/prices/{symbol}")
async def get_price(symbol: str):
    """Get current price for a symbol."""
    try:
        fetcher = CEXPriceFetcher()
        price = await fetcher.get_price(symbol)
        return {"symbol": symbol, "price": price}
    except Exception as e:
        return {"error": str(e)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await websocket.accept()
    active_connections.append(websocket)

    try:
        # Send initial state
        await websocket.send_json({
            "type": "init",
            "data": {
                "running": scanner_running,
                "stats": system_stats,
                "wallets": wallets,
            }
        })

        # Keep connection alive
        while True:
            try:
                data = await websocket.receive_text()
                # Handle incoming messages if needed
            except WebSocketDisconnect:
                break

    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        active_connections.remove(websocket)


def start_web_server(host="0.0.0.0", port=8080):
    """Start the web server."""
    print("=" * 70)
    print("🌐 ARBITRAGE DASHBOARD STARTING")
    print("=" * 70)
    print(f"")
    print(f"📊 Dashboard URL: http://localhost:{port}")
    print(f"")
    print(f"Features:")
    print(f"  • Real-time opportunity scanning")
    print(f"  • Live trade execution monitoring")
    print(f"  • Profit tracking")
    print(f"  • System controls (start/stop)")
    print(f"")
    print("=" * 70)
    print()

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_web_server()
