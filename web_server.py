"""
Web server for arbitrage scanner dashboard.

Provides a real-time web UI to monitor and control the arbitrage system.
"""

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn
from web3 import Web3

from run_live_arbitrage import ArbitrageSystem
from run_ai_integrated_arbitrage import AIIntegratedArbitrageSystem
from src.ai.decider import AICandidate, AIDecider, AIConfig
from src.live.flash_arb_runner import FlashArbitrageRunner
from src.brokers.price_fetcher import CEXPriceFetcher
from src.dex.aqua_client import AquaClient, AQUA_CONTRACT_ADDRESSES
from src.portfolio import create_portfolio_tracker_from_env, TimeRange

app = FastAPI(title="Arbitrage Scanner Dashboard")
log = structlog.get_logger()

# Import and mount AI endpoints
try:
    from src.api.ai_endpoints import router as ai_router
    app.include_router(ai_router)
    log.info("ai_endpoints.mounted")
except Exception as e:
    log.warning("ai_endpoints.mount_failed", error=str(e))

# Import and mount AI on-chain endpoints
def _noop_set_ai_runner(_: object | None = None) -> None:
    """Fallback setter if AI on-chain runner is not available."""
    return None


set_ai_runner = _noop_set_ai_runner

try:
    from src.api.ai_onchain_endpoints import router as ai_onchain_router, set_ai_runner as _set_ai_runner

    set_ai_runner = _set_ai_runner
    app.include_router(ai_onchain_router)
    log.info("ai_onchain_endpoints.mounted")
except Exception as e:
    log.warning("ai_onchain_endpoints.mount_failed", error=str(e))

# Import and mount production endpoints (circuit breakers, models, volatility)
try:
    from src.api.production_endpoints import router as production_router
    app.include_router(production_router)
    log.info("production_endpoints.mounted")
except Exception as e:
    log.warning("production_endpoints.mount_failed", error=str(e))

# Global state
scanner_task: asyncio.Task | None = None
stats_task: asyncio.Task | None = None
aqua_tasks: list[asyncio.Task] = []
scanner_system: ArbitrageSystem | None = None
runner_ref: FlashArbitrageRunner | None = None
ai_onchain_system: AIIntegratedArbitrageSystem | None = None
ai_onchain_task: asyncio.Task | None = None
scanner_running = False
scanner_started_at: datetime | None = None
opportunities: list[dict] = []
trades: list[dict] = []
aqua_events: list[dict] = []
portfolio_tracker = None
portfolio_task: asyncio.Task | None = None
system_stats = {
    "uptime_seconds": 0,
    "opportunities_found": 0,
    "trades_executed": 0,
    "total_profit_eth": 0.0,
    "wallet_balance_eth": 0.0,
    "gas_price_gwei": 0.0,
    "status": "stopped",
    "connectors": [],
    "initial_cash": float(os.getenv("INITIAL_CASH", "0") or 0),
}
runtime_environment = "live" if os.getenv("ALPACA_PAPER", "true").lower() == "false" else "sandbox"
wallets = {
    "metamask": {"address": os.getenv("METAMASK_WALLET_ADDRESS", "").strip(), "balance_eth": None},
    "rainbow": {"address": os.getenv("RAINBOW_WALLET_ADDRESS", "").strip(), "balance_eth": None},
}
rpc_url = os.getenv("ETH_RPC_URL") or os.getenv("ETHEREUM_RPC_URL") or ""
aiconfig = AIConfig(
    min_profit_eth=float(os.getenv("AI_MIN_PROFIT_ETH", os.getenv("MIN_FLASH_PROFIT_ETH", "0.05"))),
    confidence_threshold=float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.6")),
    max_gas_gwei=float(os.getenv("AI_MAX_GAS_GWEI", os.getenv("MAX_GAS_PRICE_GWEI", "120"))),
    hop_penalty_quote=float(os.getenv("AI_HOP_PENALTY_QUOTE", "5")),
)
ai_decider = AIDecider(config=aiconfig)
ai_state: dict = {"last_decision": None, "last_trace": []}
circuit_breaker_state: dict[str, object] = {}

aqua_enable = os.getenv("AQUA_ENABLE", "false").lower() == "true"
aqua_chains = [c.strip().lower() for c in os.getenv("AQUA_CHAINS", "ethereum,polygon").split(",") if c.strip()]
rpc_map = {
    "ethereum": os.getenv("ETH_RPC_URL") or os.getenv("ETHEREUM_RPC_URL") or "",
    "polygon": os.getenv("POLYGON_RPC_URL") or os.getenv("POLYGON_RPC") or "",
}

# Blockchain activity monitor state
blockchain_monitors: list[asyncio.Task] = []
blockchain_events: list[dict] = []
blockchain_monitor_enabled = os.getenv("BLOCKCHAIN_MONITOR_ENABLE", "true").lower() == "true"
_web3_client: Web3 | None = None
ENV_PATH = Path(".env")

# WebSocket connections
active_connections: list[WebSocket] = []


async def broadcast_update(data: dict):
    """Broadcast update to all connected WebSocket clients."""
    for connection in active_connections:
        try:
            await connection.send_json(data)
        except:
            pass


def get_web3() -> Web3 | None:
    """Lazy-init Web3 client using configured RPC URL."""
    global _web3_client

    if not rpc_url:
        return None

    if _web3_client is None:
        _web3_client = Web3(Web3.HTTPProvider(rpc_url))

    if not _web3_client.is_connected():
        return None

    return _web3_client


def refresh_circuit_breaker_state() -> dict[str, object]:
    """Fetch latest circuit breaker snapshot for dashboards."""
    global circuit_breaker_state
    try:
        from src.ai.circuit_breakers import get_circuit_breaker_manager

        manager = get_circuit_breaker_manager()
        snapshot = manager.get_status_snapshot()
        trading_allowed, blocked_reason = manager.is_trading_allowed()
        circuit_breaker_state = {
            "trading_allowed": trading_allowed,
            "blocked_reason": blocked_reason,
            "snapshot": snapshot,
        }
    except Exception as e:
        log.warning("dashboard.circuit_breaker_state_failed", error=str(e))
    return circuit_breaker_state


async def init_ai_onchain_runner() -> None:
    """Start the AI-integrated runner and register it with the API router."""
    global ai_onchain_system, ai_onchain_task

    if ai_onchain_system or ai_onchain_task:
        return

    try:
        # Run in live mode (not dry-run) for real execution stats; ensure env is production-ready.
        ai_onchain_system = AIIntegratedArbitrageSystem(dry_run=False)
        set_ai_runner(ai_onchain_system.runner)
        ai_onchain_task = asyncio.create_task(ai_onchain_system.run())
        log.info("ai_onchain.runner_started", dry_run=False)
    except Exception as e:
        log.warning("ai_onchain.runner_start_failed", error=str(e))


@app.on_event("startup")
async def _startup() -> None:
    # Start AI on-chain runner for flash loan optimization
    await init_ai_onchain_runner()

    # Auto-start Aqua watchers if enabled (independent of scanner)
    if aqua_enable:
        await start_aqua_watchers()
        log.info("aqua_watchers.auto_started", chains=aqua_chains)

    # Auto-start blockchain activity monitors
    if blockchain_monitor_enabled:
        await start_blockchain_monitors()
        log.info("blockchain_monitors.auto_started")


@app.on_event("shutdown")
async def _shutdown() -> None:
    if ai_onchain_task:
        ai_onchain_task.cancel()


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


def _record_event(collection: list[dict], item: dict, limit: int = 50) -> None:
    """Append and trim history for opportunities/trades."""
    collection.append(item)
    if len(collection) > limit:
        del collection[:-limit]


async def start_aqua_watchers() -> None:
    """Start Aqua event watchers for configured chains."""
    global aqua_tasks
    if not aqua_enable:
        return
    # stop existing
    await stop_aqua_watchers()
    tasks: list[asyncio.Task] = []
    chain_alias = {"ethereum": 1, "eth": 1, "polygon": 137, "matic": 137}
    for chain in aqua_chains:
        rpc = rpc_map.get(chain)
        if not rpc:
            continue
        chain_id = chain_alias.get(chain)
        if chain_id is None or chain_id not in AQUA_CONTRACT_ADDRESSES:
            continue
        tasks.append(asyncio.create_task(aqua_watcher(chain, chain_id, rpc)))
    aqua_tasks = tasks


async def stop_aqua_watchers() -> None:
    """Stop all Aqua watchers."""
    global aqua_tasks
    for t in aqua_tasks:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
    aqua_tasks = []


async def aqua_watcher(chain: str, chain_id: int, rpc_url: str) -> None:
    """Poll Aqua events and broadcast."""
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        return
    client = AquaClient(w3, chain_id)
    try:
        latest = w3.eth.block_number
    except Exception:
        latest = 0
    # Start from current block to avoid RPC query limits (most free RPCs restrict historical ranges)
    from_block = latest
    while True:
        try:
            to_block = w3.eth.block_number
            logs = w3.eth.get_logs(
                {
                    "fromBlock": from_block,
                    "toBlock": to_block,
                    "address": client.address,
                }
            )
            for log in logs:
                evt = client.parse_event(dict(log))
                if evt:
                    data = evt.__dict__
                    _record_event(aqua_events, data, limit=100)
                    await broadcast_update({"type": "aqua_event", "data": data})
            from_block = to_block + 1
        except Exception as e:
            structlog.get_logger().warning("aqua.watcher_error", chain=chain, error=str(e), error_type=type(e).__name__)
            await asyncio.sleep(5)
        await asyncio.sleep(5)


async def start_blockchain_monitors() -> None:
    """Start live blockchain activity monitors."""
    global blockchain_monitors
    if not blockchain_monitor_enabled:
        return

    await stop_blockchain_monitors()

    try:
        from src.nft.live_blockchain_monitor import create_monitor

        # Collect watched wallets
        watched_wallets = [
            w["address"] for w in wallets.values() if w["address"]
        ]

        async def handle_blockchain_event(event: Any) -> None:
            """Handle blockchain events and broadcast to clients."""
            event_dict = event.to_dict()
            _record_event(blockchain_events, event_dict, limit=50)
            await broadcast_update({"type": "blockchain_event", "data": event_dict})

        tasks: list[asyncio.Task] = []

        # Start Ethereum monitor
        if rpc_map.get("ethereum"):
            eth_monitor = await create_monitor(
                chain="ethereum",
                rpc_url=rpc_map["ethereum"],
                wallets=watched_wallets,
                on_event=handle_blockchain_event,
            )
            tasks.append(asyncio.create_task(eth_monitor.run()))

        # Start Polygon monitor
        if rpc_map.get("polygon"):
            poly_monitor = await create_monitor(
                chain="polygon",
                rpc_url=rpc_map["polygon"],
                wallets=watched_wallets,
                on_event=handle_blockchain_event,
            )
            tasks.append(asyncio.create_task(poly_monitor.run()))

        blockchain_monitors = tasks
        log.info("blockchain_monitors.started", count=len(tasks))

    except Exception as e:
        log.error("blockchain_monitors.start_failed", error=str(e))


async def stop_blockchain_monitors() -> None:
    """Stop all blockchain monitors."""
    global blockchain_monitors
    for task in blockchain_monitors:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    blockchain_monitors = []


async def apply_runtime_config(payload: dict) -> None:
    """Apply config overrides to the running system/runner."""
    global scanner_system, runner_ref, ai_decider
    if not scanner_system:
        return

    cfg = scanner_system.config

    # Numeric thresholds
    for key in (
        "min_edge_bps",
        "min_edge_bps_polygon",
        "min_edge_bps_cross_chain",
        "slippage_tolerance",
        "profit_floor_quote",
        "min_margin_bps",
    ):
        if key in payload and payload[key] is not None:
            try:
                setattr(cfg, key, float(payload[key]))
            except (TypeError, ValueError):
                continue

    # Gas caps
    gas_caps = {}
    for chain_key in ("eth", "polygon"):
        cap_val = payload.get(f"gas_price_cap_{chain_key}")
        if cap_val is None:
            continue
        try:
            mapped_key = "ethereum" if chain_key == "eth" else "polygon"
            gas_caps[mapped_key] = float(cap_val)
        except (TypeError, ValueError):
            pass
    if payload.get("gas_price_cap_gwei") and isinstance(payload["gas_price_cap_gwei"], dict):
        gas_caps.update(payload["gas_price_cap_gwei"])
    if gas_caps:
        cfg.gas_price_cap_gwei = gas_caps

    # Protocol filters
    if payload.get("polygon_quote_protocols"):
        cfg.polygon_quote_protocols = str(payload["polygon_quote_protocols"])

    # Execution toggles
    if "enable_execution" in payload:
        cfg.enable_execution = bool(payload["enable_execution"])
    if "enable_polygon_execution" in payload:
        cfg.enable_polygon_execution = bool(payload["enable_polygon_execution"])

    # Flash loan toggle can be updated via parent config
    if "enable_flash_loans" in payload and hasattr(cfg, "enable_flash_loans"):
        cfg.enable_flash_loans = bool(payload["enable_flash_loans"])

    # AI knobs (off-chain decider hints)
    if ai_decider:
        if payload.get("ai_min_profit_eth") is not None:
            try:
                ai_decider.config.min_profit_eth = float(payload["ai_min_profit_eth"])
            except (TypeError, ValueError):
                pass
        if payload.get("ai_confidence_threshold") is not None:
            try:
                ai_decider.config.confidence_threshold = float(payload["ai_confidence_threshold"])
            except (TypeError, ValueError):
                pass
        if payload.get("ai_max_gas_gwei") is not None:
            try:
                ai_decider.config.max_gas_gwei = float(payload["ai_max_gas_gwei"])
            except (TypeError, ValueError):
                pass
        if payload.get("ai_hop_penalty_quote") is not None:
            try:
                ai_decider.config.hop_penalty_quote = float(payload["ai_hop_penalty_quote"])
            except (TypeError, ValueError):
                pass

    # Sync AI knobs into on-chain enforcement where applicable
    if payload.get("ai_min_profit_eth") is not None and hasattr(cfg, "min_flash_profit_eth"):
        try:
            cfg.min_flash_profit_eth = float(payload["ai_min_profit_eth"])
        except (TypeError, ValueError):
            pass

    if payload.get("ai_max_gas_gwei") is not None:
        try:
            gas_val = float(payload["ai_max_gas_gwei"])
            # ensure we have a dict for per-chain caps
            if not isinstance(cfg.gas_price_cap_gwei, dict):
                cfg.gas_price_cap_gwei = {}
            cfg.gas_price_cap_gwei["ethereum"] = gas_val
        except (TypeError, ValueError):
            pass

    # Propagate to live runner if present
    if runner_ref:
        runner_ref.config = cfg


def _persist_env_value(key: str, value: str) -> None:
    """Persist a single env key to the .env file (best-effort)."""
    try:
        ENV_PATH.touch(exist_ok=True)
        lines = ENV_PATH.read_text().splitlines()
        updated = False
        for idx, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[idx] = f"{key}={value}"
                updated = True
                break
        if not updated:
            lines.append(f"{key}={value}")
        ENV_PATH.write_text("\n".join(lines) + "\n")
    except Exception:
        log.warning("env.persist_failed", key=key)


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
    """Serve the production dashboard HTML."""
    with open("production_dashboard.html", "r") as f:
        return f.read()


@app.get("/classic", response_class=HTMLResponse)
async def get_classic_dashboard():
    """Serve the classic dashboard HTML."""
    with open("web_dashboard.html", "r") as f:
        return f.read()


@app.get("/api/status")
async def get_status():
    """Get current system status."""
    return {
        "running": scanner_running,
        "stats": system_stats,
        "wallets": wallets,
        "environment": runtime_environment,
        "opportunities": opportunities[-10:],  # Last 10
        "trades": trades[-10:],  # Last 10
        "connectors": getattr(scanner_system, "active_connectors", []),
        "ai_state": ai_state,
        "route_health": {
            "failures": getattr(runner_ref, "route_failures", {}),
            "blacklisted_routes": list(getattr(runner_ref, "blacklisted_routes", [])),
            "pair_results": getattr(runner_ref, "pair_results", {}),
        },
    }


@app.get("/api/wallets")
async def get_wallets():
    """Return configured wallet metadata and balances."""
    await refresh_wallet_balances()
    return {"wallets": wallets, "rpc_url": rpc_url}


@app.get("/api/aqua/events")
async def get_aqua_events():
    """Return recent Aqua events."""
    return {"events": aqua_events[-50:]}


@app.get("/api/blockchain/events")
async def get_blockchain_events():
    """Return recent blockchain activity events."""
    return {
        "events": blockchain_events[-30:],
        "enabled": blockchain_monitor_enabled,
        "count": len(blockchain_events),
    }


async def _initialize_and_start_scanner(config: dict, dry_run: bool, enable_flash: bool, auto_execute: bool):
    """Background task to initialize and start the scanner."""
    global scanner_task, stats_task, scanner_system, scanner_running, scanner_started_at, runner_ref

    try:
        # Create system with configuration (this can take several seconds)
        log.info("scanner.initializing", dry_run=dry_run, enable_flash=enable_flash)
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

        system_ref = scanner_system

        async def price_fetcher(symbol: str):
            return await system_ref.price_fetcher.get_price(symbol)

        runner = FlashArbitrageRunner(
            router=scanner_system.router,
            dex=scanner_system.dex,
            price_fetcher=price_fetcher,
            token_addresses=scanner_system.token_addresses,
            polygon_token_addresses=getattr(scanner_system, "polygon_token_addresses", None),
            config=scanner_system.config,
            token_decimals=getattr(scanner_system, "token_decimals", {}),
            polygon_dex=getattr(scanner_system, "polygon_dex", None),
            on_opportunity=handle_opportunity,
            on_trade=handle_trade,
        )
        runner_ref = runner

        # Apply overrides from UI
        await apply_runtime_config(config or {})
        await start_aqua_watchers()

        # Mark as started
        scanner_running = True
        scanner_started_at = datetime.now(timezone.utc)
        system_stats["status"] = "running"
        system_stats["start_time"] = scanner_started_at.isoformat()

        # Start scanner and stats loops
        scanner_task = asyncio.create_task(runner.run(scanner_system.symbols))
        stats_task = asyncio.create_task(stats_loop())

        log.info("scanner.started", dry_run=dry_run, enable_flash=enable_flash,
                 connectors=getattr(scanner_system, "active_connectors", []))

        # Broadcast success via WebSocket
        await broadcast_update({
            "type": "status",
            "running": True,
            "message": "Scanner started successfully",
            "wallets": wallets,
            "connectors": getattr(scanner_system, "active_connectors", []),
            "environment": runtime_environment,
        })

    except Exception as e:
        log.error("scanner.init_failed", error=str(e))
        scanner_running = False
        system_stats["status"] = "error"
        await broadcast_update({
            "type": "status",
            "running": False,
            "message": f"Failed to start: {str(e)}",
            "environment": runtime_environment,
        })


@app.post("/api/start")
async def start_scanner(config: dict[str, Any] | None = None):
    """Start the arbitrage scanner."""
    global scanner_running, runtime_environment

    if scanner_running:
        return {"error": "Scanner already running"}

    try:
        environment = (config or {}).get("environment", runtime_environment)
        if environment not in ("sandbox", "live"):
            environment = "sandbox"

        # Flip sandbox/live env vars so connectors hit the right endpoints
        if environment == "live":
            os.environ["ALPACA_PAPER"] = "false"
            os.environ["BYBIT_TESTNET"] = "false"
            os.environ["TRADING_MODE"] = "live"
            os.environ["DRY_RUN"] = "false"
        else:
            os.environ["ALPACA_PAPER"] = "true"
            os.environ["BYBIT_TESTNET"] = "true"
            os.environ["TRADING_MODE"] = "paper"
            os.environ["DRY_RUN"] = "true"
        runtime_environment = environment
        system_stats["environment"] = runtime_environment

        # Extract config
        dry_run = config.get("dry_run", True) if config else True
        enable_flash = config.get("enable_flash", True) if config else True
        auto_execute = config.get("auto_execute", False) if config else False

        # Start initialization in background to avoid blocking the HTTP response
        asyncio.create_task(
            _initialize_and_start_scanner(config or {}, dry_run, enable_flash, auto_execute)
        )

        # Return immediately while initialization happens in background
        return {
            "success": True,
            "message": "Scanner is starting...",
            "dry_run": dry_run,
            "enable_flash": enable_flash,
            "auto_execute": auto_execute,
            "environment": runtime_environment,
        }

    except Exception as e:
        log.exception("scanner.start_failed")
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
    await stop_aqua_watchers()

    scanner_running = False
    system_stats["status"] = "stopped"
    system_stats["uptime_seconds"] = 0
    system_stats["gas_price_gwei"] = 0.0
    system_stats["wallet_balance_eth"] = 0.0

    await broadcast_update({
        "type": "status",
        "running": False,
        "message": "Scanner stopped",
        "environment": runtime_environment,
    })

    return {"success": True, "message": "Scanner stopped"}


@app.get("/api/config")
async def get_config():
    """Return current runtime config."""
    # DRY_RUN is critical safety config - always expose it
    dry_run = os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")

    if not scanner_system:
        return {
            "config": {
                "initial_cash": float(os.getenv("INITIAL_CASH", "0") or 0),
                "dry_run": dry_run,
                "trading_mode": os.getenv("TRADING_MODE", "paper"),
            }
        }

    cfg = scanner_system.config
    return {
        "config": {
            "min_edge_bps": cfg.min_edge_bps,
            "min_edge_bps_polygon": cfg.min_edge_bps_polygon,
            "min_edge_bps_cross_chain": cfg.min_edge_bps_cross_chain,
            "slippage_tolerance": cfg.slippage_tolerance,
            "profit_floor_quote": cfg.profit_floor_quote,
            "gas_price_cap_gwei": cfg.gas_price_cap_gwei,
            "min_margin_bps": getattr(cfg, "min_margin_bps", 0.0),
            "enable_execution": cfg.enable_execution,
            "enable_polygon_execution": cfg.enable_polygon_execution,
            "polygon_quote_protocols": cfg.polygon_quote_protocols,
            "initial_cash": float(os.getenv("INITIAL_CASH", "0") or 0),
            "dry_run": dry_run,
            "trading_mode": os.getenv("TRADING_MODE", "paper"),
        }
    }


@app.post("/api/config/update")
async def update_config(payload: dict):
    """Update live config values while running."""
    initial_cash_val = payload.get("initial_cash")
    if initial_cash_val is not None:
        try:
            val = float(initial_cash_val)
            os.environ["INITIAL_CASH"] = str(val)
            system_stats["initial_cash"] = val
            _persist_env_value("INITIAL_CASH", str(val))
        except (TypeError, ValueError):
            pass

    await apply_runtime_config(payload or {})
    return {"success": True, "config": payload}


def _parse_ai_candidates(payload: dict) -> list[AICandidate]:
    """Convert incoming JSON into AICandidate objects."""
    candidates: list[AICandidate] = []
    for raw in payload.get("candidates", []):
        try:
            candidates.append(
                AICandidate(
                    symbol=raw["symbol"],
                    edge_bps=float(raw.get("edge_bps", 0)),
                    notional_quote=float(raw.get("notional_quote", 0)),
                    gas_cost_quote=float(raw.get("gas_cost_quote", 0)),
                    flash_fee_quote=float(raw.get("flash_fee_quote", 0)),
                    slippage_quote=float(raw.get("slippage_quote", 0)),
                    hop_count=int(raw.get("hop_count", 1)),
                    cex_price=float(raw.get("cex_price")) if raw.get("cex_price") is not None else None,
                    dex_price=float(raw.get("dex_price")) if raw.get("dex_price") is not None else None,
                    chain=raw.get("chain", "ethereum"),
                    confidence=float(raw.get("confidence", 0.5)),
                )
            )
        except Exception:
            continue
    return candidates


@app.post("/api/ai/score")
async def ai_score(payload: dict):
    """Score a batch of AI candidates and optionally execute the best one."""
    if not payload or "candidates" not in payload:
        return {"error": "candidates required"}

    candidates = _parse_ai_candidates(payload)
    decision = ai_decider.pick_best(candidates)
    decision_payload = decision.as_dict() if decision else None
    if decision_payload is not None:
        decision_payload["timestamp"] = datetime.now(timezone.utc).isoformat()

    ai_state["last_decision"] = decision_payload
    ai_state["last_trace"] = ai_decider.last_trace

    log.info("ai_decision.batch_scored", decision=decision_payload, trace=ai_decider.last_trace)
    await broadcast_update(
        {"type": "ai_decision", "data": decision_payload, "trace": ai_decider.last_trace}
    )

    response = {"decision": decision_payload, "trace": ai_decider.last_trace}

    # Optional execution hook (only if scanner is live + execution enabled)
    if payload.get("execute") and decision:
        if not scanner_running or not runner_ref:
            response.update({"executed": False, "reason": "scanner_not_running"})
            return response

        if not scanner_system or not scanner_system.config.enable_execution:
            response.update({"executed": False, "reason": "execution_disabled"})
            return response

        if not scanner_system.config.enable_flash_loans:
            response.update({"executed": False, "reason": "flash_loans_disabled"})
            return response

        exec_result = await runner_ref.execute_ai_flash_decision(decision)
        response["executed"] = exec_result.get("accepted", False)
        response["execution_result"] = exec_result

    return response


@app.get("/api/prices/{symbol}")
async def get_price(symbol: str):
    """Get current price for a symbol."""
    try:
        fetcher = CEXPriceFetcher(binance_enabled=False, kraken_enabled=True)
        price = await fetcher.get_price(symbol)
        return {"symbol": symbol, "price": price}
    except Exception as e:
        return {"error": str(e)}


# ========== AI/ML Visualization Endpoints ==========

@app.get("/api/ai/decisions/recent")
async def get_recent_ai_decisions(limit: int = 20):
    """Get recent AI decisions with full trace data.

    Args:
        limit: Maximum number of decisions to return (1-100)

    Returns:
        Recent AI decisions with scores and reasoning
    """
    if limit < 1 or limit > 100:
        return {"error": "Limit must be 1-100"}

    # Return recent AI decisions from state
    decisions = []
    if ai_state.get("last_decision"):
        decisions.append({
            "timestamp": ai_state["last_decision"].get("timestamp"),
            "decision": ai_state["last_decision"],
            "trace": ai_state.get("last_trace", []),
        })

    return {
        "decisions": decisions[-limit:],
        "count": len(decisions),
    }


@app.get("/api/ml/performance")
async def get_ml_performance():
    """Get ML model performance metrics.

    Returns:
        Performance stats for all ML models
    """
    try:
        from pathlib import Path

        models_dir = Path("models")

        # Check which models exist
        models_status = {
            "predictive_transformer": {
                "exists": (models_dir / "predictive_transformer.pt").exists(),
                "path": str(models_dir / "predictive_transformer.pt"),
            },
            "slippage_xgb": {
                "exists": (models_dir / "slippage_xgb.json").exists(),
                "path": str(models_dir / "slippage_xgb.json"),
            },
            "route_success": {
                "exists": (models_dir / "route_success_model.pkl").exists(),
                "path": str(models_dir / "route_success_model.pkl"),
            },
        }

        # Check RL agents
        rl_dir = models_dir / "multi_agent_rl"
        if rl_dir.exists():
            rl_agents = list(rl_dir.glob("agent_*.zip"))
            models_status["rl_agents"] = {
                "exists": len(rl_agents) > 0,
                "count": len(rl_agents),
                "agents": [a.stem for a in rl_agents],
            }

        return {
            "models": models_status,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        log.exception("ml_performance.failed", error=str(e))
        return {"error": str(e)}


@app.get("/api/execution/matrix")
async def get_execution_matrix():
    """Get execution path performance matrix.

    Returns:
        Success rates and P&L by execution path
    """
    try:
        # Aggregate stats by execution path
        paths = {
            "flash_loan": {
                "attempts": flash_executions if 'flash_executions' in globals() else 0,
                "failures": flash_failures if 'flash_failures' in globals() else 0,
                "success_rate": 0.0,
                "total_profit_eth": 0.0,
            },
            "cex_arbitrage": {
                "attempts": system_stats.get("trades_executed", 0),
                "success_rate": 0.0,
                "total_profit_eth": system_stats.get("total_profit_eth", 0.0),
            },
            "cross_chain": {
                "attempts": 0,
                "success_rate": 0.0,
                "total_profit_eth": 0.0,
            },
        }

        # Calculate success rates
        for path, stats in paths.items():
            if stats["attempts"] > 0:
                successes = stats["attempts"] - stats.get("failures", 0)
                stats["success_rate"] = successes / stats["attempts"]

        return {
            "paths": paths,
            "total_attempts": sum(p["attempts"] for p in paths.values()),
            "total_profit_eth": sum(p.get("total_profit_eth", 0) for p in paths.values()),
        }

    except Exception as e:
        log.exception("execution_matrix.failed", error=str(e))
        return {"error": str(e)}


@app.get("/api/ml/predictions/recent")
async def get_recent_predictions(limit: int = 10):
    """Get recent ML model predictions.

    Args:
        limit: Maximum number of predictions to return

    Returns:
        Recent predictions from all ML models
    """
    # This would query the prediction log database
    # For now, return empty
    return {
        "predictions": [],
        "count": 0,
        "message": "Prediction logging not yet implemented",
    }


@app.get("/api/rl/agents/status")
async def get_rl_agents_status():
    """Get multi-agent RL system status.

    Returns:
        Status of all RL agents
    """
    try:
        from pathlib import Path

        models_dir = Path("models/multi_agent_rl")

        if not models_dir.exists():
            return {
                "enabled": False,
                "message": "Multi-agent RL not yet trained",
            }

        agents = list(models_dir.glob("agent_*.zip"))

        agent_stats = []
        for agent_path in agents:
            agent_name = agent_path.stem.replace("agent_", "")
            agent_stats.append({
                "name": agent_name,
                "model_path": str(agent_path),
                "size_mb": agent_path.stat().st_size / 1024 / 1024,
                "active": False,  # Would be determined by runtime state
            })

        return {
            "enabled": len(agents) > 0,
            "agent_count": len(agents),
            "agents": agent_stats,
        }

    except Exception as e:
        log.exception("rl_agents_status.failed", error=str(e))
        return {"error": str(e)}


@app.post("/api/ml/train")
async def trigger_ml_training(model_type: str = "all"):
    """Trigger ML model training.

    Args:
        model_type: Type of model to train (all, predictive, slippage, rl)

    Returns:
        Training task status
    """
    try:
        import subprocess

        # Launch training script in background
        cmd = ["python", "scripts/train_ml_models.py"]

        if model_type != "all":
            cmd.append(f"--{model_type}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=Path(__file__).parent,
        )

        return {
            "status": "training_started",
            "model_type": model_type,
            "pid": process.pid,
            "message": "Training running in background. Check logs for progress.",
        }

    except Exception as e:
        log.exception("ml_training.failed", error=str(e))
        return {"error": str(e)}


# ========== NFT API Endpoints (OpenSea v2) ==========

@app.get("/api/nft/wallet/{wallet_address}")
async def get_wallet_nfts(wallet_address: str, chain: str = "ethereum"):
    """
    Get all NFTs owned by a wallet address.

    Args:
        wallet_address: Ethereum wallet address
        chain: Blockchain (ethereum, polygon, base, arbitrum, etc.)
    """
    try:
        from src.nft.opensea_client import get_wallet_nfts

        api_key = os.getenv("OPENSEA_API_KEY")
        nfts = await get_wallet_nfts(wallet_address, chain, api_key)

        return {
            "success": True,
            "wallet": wallet_address,
            "chain": chain,
            "count": len(nfts),
            "nfts": [
                {
                    "identifier": nft.identifier,
                    "collection": nft.collection,
                    "name": nft.name,
                    "image_url": nft.image_url,
                    "opensea_url": nft.opensea_url,
                    "contract": nft.contract,
                    "token_standard": nft.token_standard,
                }
                for nft in nfts
            ],
        }
    except Exception as e:
        log.exception("nft.wallet_fetch_failed", wallet=wallet_address, error=str(e))
        return {"success": False, "error": str(e)}


@app.get("/api/nft/collection/{collection_slug}")
async def get_collection_info(collection_slug: str):
    """
    Get collection details by OpenSea slug.

    Args:
        collection_slug: OpenSea collection identifier (e.g., 'boredapeyachtclub')
    """
    try:
        from src.nft.opensea_client import OpenSeaClient

        api_key = os.getenv("OPENSEA_API_KEY")
        client = OpenSeaClient(api_key=api_key)
        collection = await client.get_collection(collection_slug)

        if not collection:
            return {"success": False, "error": "Collection not found"}

        return {
            "success": True,
            "collection": {
                "name": collection.name,
                "slug": collection.slug,
                "image_url": collection.image_url,
                "floor_price_eth": collection.floor_price_eth,
                "total_supply": collection.total_supply,
                "owner_count": collection.owner_count,
            },
        }
    except Exception as e:
        log.exception("nft.collection_fetch_failed", slug=collection_slug, error=str(e))
        return {"success": False, "error": str(e)}


# ========== Portfolio API Endpoints (1inch v5.0) ==========

@app.get("/api/portfolio/status")
async def portfolio_status():
    """Get portfolio tracker status and health."""
    global portfolio_tracker

    if not portfolio_tracker:
        return {
            "enabled": False,
            "error": "Portfolio tracker not configured. Set ONEINCH_API_KEY and PORTFOLIO_WALLETS in .env"
        }

    try:
        status = portfolio_tracker.get_health_status()
        return status
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/portfolio/snapshots")
async def portfolio_snapshots():
    """Get current portfolio snapshots for all wallets."""
    global portfolio_tracker

    if not portfolio_tracker:
        return {"error": "Portfolio tracker not configured"}

    try:
        snapshots = portfolio_tracker.get_all_snapshots()

        # Convert to JSON-serializable format
        result = {}
        for address, snapshot in snapshots.items():
            chains_data = {}
            for chain_id, chain_snapshot in snapshot.chains.items():
                chains_data[chain_id] = {
                    "chain_id": chain_snapshot.chain_id,
                    "total_value_usd": float(chain_snapshot.total_value_usd),
                    "token_count": len(chain_snapshot.tokens),
                    "protocol_count": len(chain_snapshot.protocols),
                    "tokens": chain_snapshot.tokens[:10],  # Limit to top 10
                    "protocols": chain_snapshot.protocols[:10],  # Limit to top 10
                }

            result[address] = {
                "address": snapshot.address,
                "total_value_usd": float(snapshot.total_value_usd),
                "timestamp": snapshot.timestamp.isoformat(),
                "chains": chains_data,
            }

        return result
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/portfolio/metrics")
async def portfolio_metrics(
    address: str | None = None,
    time_range: str = "1month",
):
    """Get portfolio metrics (PnL, ROI) for specified wallet and time range."""
    global portfolio_tracker

    if not portfolio_tracker:
        return {"error": "Portfolio tracker not configured"}

    try:
        # Parse time range
        time_range_map = {
            "1day": TimeRange.ONE_DAY,
            "1week": TimeRange.ONE_WEEK,
            "1month": TimeRange.ONE_MONTH,
            "3months": TimeRange.THREE_MONTHS,
            "1year": TimeRange.ONE_YEAR,
        }
        tr = time_range_map.get(time_range, TimeRange.ONE_MONTH)

        # If address specified, get metrics for that wallet
        if address:
            metrics = portfolio_tracker.get_cached_metrics(address, tr)
            if not metrics:
                return {"error": f"No metrics available for {address}"}

            return {
                "address": metrics.address,
                "time_range": metrics.time_range.value,
                "total_profit_usd": float(metrics.total_profit_usd),
                "total_roi_percentage": float(metrics.total_roi_percentage),
                "timestamp": metrics.timestamp.isoformat(),
                "protocol_count": len(metrics.protocols),
                "token_count": len(metrics.tokens),
                "top_protocols": [
                    {
                        "name": p.protocol_name,
                        "chain_id": p.chain_id,
                        "profit_usd": float(p.absolute_profit_usd),
                        "roi_percentage": float(p.roi_percentage),
                        "apr_percentage": float(p.apr_percentage) if p.apr_percentage else None,
                    }
                    for p in sorted(metrics.protocols, key=lambda x: x.absolute_profit_usd, reverse=True)[:5]
                ],
                "top_tokens": [
                    {
                        "symbol": t.symbol,
                        "chain_id": t.chain_id,
                        "profit_usd": float(t.absolute_profit_usd),
                        "roi_percentage": float(t.roi_percentage),
                        "value_usd": float(t.current_value_usd),
                    }
                    for t in sorted(metrics.tokens, key=lambda x: x.absolute_profit_usd, reverse=True)[:10]
                ],
            }

        # Otherwise get aggregated metrics across all wallets
        all_metrics = []
        for wallet_config in portfolio_tracker.wallets:
            metrics = portfolio_tracker.get_cached_metrics(wallet_config.address, tr)
            if metrics:
                all_metrics.append({
                    "address": metrics.address,
                    "total_profit_usd": float(metrics.total_profit_usd),
                    "total_roi_percentage": float(metrics.total_roi_percentage),
                })

        total_profit = sum(m["total_profit_usd"] for m in all_metrics)

        return {
            "time_range": tr.value,
            "wallet_count": len(all_metrics),
            "total_profit_usd": total_profit,
            "wallets": all_metrics,
        }

    except Exception as e:
        return {"error": str(e)}


@app.get("/api/portfolio/total-value")
async def portfolio_total_value():
    """Get total portfolio value across all tracked wallets."""
    global portfolio_tracker

    if not portfolio_tracker:
        return {"error": "Portfolio tracker not configured"}

    try:
        total_value = portfolio_tracker.get_total_portfolio_value()
        return {
            "total_value_usd": float(total_value),
            "wallet_count": len(portfolio_tracker.wallets),
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/portfolio/start")
async def start_portfolio_tracker():
    """Start portfolio tracking."""
    global portfolio_tracker, portfolio_task

    try:
        # Initialize tracker if not already created
        if not portfolio_tracker:
            portfolio_tracker = create_portfolio_tracker_from_env()

        if not portfolio_tracker:
            return {"error": "Portfolio tracker not configured. Check ONEINCH_API_KEY and PORTFOLIO_WALLETS"}

        # Start tracker if not already running
        if portfolio_task is None or portfolio_task.done():
            portfolio_task = asyncio.create_task(portfolio_tracker.start())
            log.info("portfolio_tracker.started_from_api")
            return {"status": "started", "wallets": len(portfolio_tracker.wallets)}

        return {"status": "already_running"}

    except Exception as e:
        log.exception("portfolio_tracker.start_failed")
        return {"error": str(e)}


@app.post("/api/portfolio/stop")
async def stop_portfolio_tracker():
    """Stop portfolio tracking."""
    global portfolio_tracker, portfolio_task

    if not portfolio_tracker:
        return {"error": "Portfolio tracker not running"}

    try:
        await portfolio_tracker.stop()
        if portfolio_task:
            portfolio_task.cancel()
            try:
                await portfolio_task
            except asyncio.CancelledError:
                pass
            portfolio_task = None

        log.info("portfolio_tracker.stopped_from_api")
        return {"status": "stopped"}

    except Exception as e:
        log.exception("portfolio_tracker.stop_failed")
        return {"error": str(e)}


# ============================================================================
# PRODUCTION SAFETY INTEGRATION ENDPOINTS
# ============================================================================


@app.get("/api/production/overview")
async def get_production_overview() -> dict[str, Any]:
    """Get comprehensive production safety overview.

    Returns:
        Combined status from safety guard, circuit breakers, and recent trades
    """
    try:
        from src.ai.production_safety import get_production_safety_guard
        from src.ai.circuit_breakers import get_circuit_breaker_manager
        from src.ai.transaction_logger import get_transaction_logger

        safety = get_production_safety_guard()
        breakers = get_circuit_breaker_manager()
        tx_logger = get_transaction_logger()

        safety_status = safety.get_status()
        breaker_status = breakers.get_status()
        trade_stats = tx_logger.get_session_stats()

        # Determine overall system health
        is_healthy = (
            not safety_status["emergency_shutdown"]
            and breaker_status["trading_allowed"]
            and safety_status["limits"]["hourly_loss"]["remaining_eth"] > 0
        )

        return {
            "healthy": is_healthy,
            "safety": {
                "emergency_shutdown": safety_status["emergency_shutdown"],
                "trades_today": safety_status["usage"]["trades_today"],
                "hourly_loss_eth": safety_status["limits"]["hourly_loss"]["used_eth"],
                "daily_loss_eth": safety_status["limits"]["daily_loss"]["used_eth"],
            },
            "circuit_breakers": {
                "trading_allowed": breaker_status["trading_allowed"],
                "any_tripped": breaker_status["any_tripped"],
                "tripped_breakers": [
                    name
                    for name, breaker in breaker_status["breakers"].items()
                    if breaker["state"] != "closed"
                ],
            },
            "trades": {
                "total": trade_stats.get("total_trades", 0),
                "approved": trade_stats.get("approved_trades", 0),
                "executed": trade_stats.get("executed_trades", 0),
                "win_rate": trade_stats.get("win_rate", 0.0),
            },
        }
    except Exception as e:
        log.warning("production.overview_failed", error=str(e))
        return {"error": str(e), "healthy": False}


@app.get("/api/production/safety/quick-status")
async def get_safety_quick_status() -> dict[str, Any]:
    """Get quick production safety status for dashboard widgets.

    Returns:
        Simplified safety status with key metrics
    """
    try:
        from src.ai.production_safety import get_production_safety_guard

        safety = get_production_safety_guard()
        status = safety.get_status()

        return {
            "emergency_shutdown": status["emergency_shutdown"],
            "trades_today": status["usage"]["trades_today"],
            "max_trades_today": status["limits"]["daily_trades"]["limit"],
            "daily_loss_eth": status["limits"]["daily_loss"]["used_eth"],
            "max_daily_loss_eth": status["limits"]["daily_loss"]["limit_eth"],
            "total_drawdown_eth": status["limits"]["total_drawdown"]["used_eth"],
            "max_drawdown_eth": status["limits"]["total_drawdown"]["limit_eth"],
        }
    except Exception as e:
        log.warning("production.safety_quick_status_failed", error=str(e))
        return {"error": str(e)}


@app.get("/api/production/circuit-breakers/status")
async def get_circuit_breakers_quick_status() -> dict[str, Any]:
    """Get quick circuit breaker status.

    Returns:
        Simplified circuit breaker status
    """
    try:
        from src.ai.circuit_breakers import get_circuit_breaker_manager

        breakers = get_circuit_breaker_manager()
        status = breakers.get_status()

        return {
            "trading_allowed": status["trading_allowed"],
            "any_tripped": status["any_tripped"],
            "breakers": {
                name: {
                    "state": breaker["state"],
                    "current_value": breaker.get("current_value"),
                    "threshold": breaker.get("threshold"),
                }
                for name, breaker in status["breakers"].items()
            },
        }
    except Exception as e:
        log.warning("production.circuit_breakers_status_failed", error=str(e))
        return {"error": str(e)}


@app.get("/api/production/trades/recent")
async def get_recent_trades(limit: int = 10) -> dict[str, Any]:
    """Get recent trade executions.

    Args:
        limit: Maximum number of trades to return (1-100)

    Returns:
        Recent trades with execution results
    """
    if limit < 1 or limit > 100:
        return {"error": "Limit must be 1-100"}

    try:
        from src.ai.transaction_logger import get_transaction_logger

        tx_logger = get_transaction_logger()
        stats = tx_logger.get_session_stats()

        # Get recent trades from history
        recent = stats.get("recent_trades", [])[-limit:]

        return {
            "trades": recent,
            "count": len(recent),
        }
    except Exception as e:
        log.warning("production.recent_trades_failed", error=str(e))
        return {"error": str(e)}


@app.get("/api/production/stats")
async def get_production_stats() -> dict[str, Any]:
    """Get comprehensive production statistics.

    Returns:
        Win rate, P&L, execution metrics, safety metrics
    """
    try:
        from src.ai.production_safety import get_production_safety_guard
        from src.ai.transaction_logger import get_transaction_logger

        safety = get_production_safety_guard()
        tx_logger = get_transaction_logger()

        safety_stats = safety.get_status()
        trade_stats = tx_logger.get_session_stats()

        return {
            "safety": safety_stats,
            "trades": trade_stats,
        }
    except Exception as e:
        log.warning("production.stats_failed", error=str(e))
        return {"error": str(e)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await websocket.accept()
    active_connections.append(websocket)

    try:
        # Refresh circuit breaker state for initial payload
        refresh_circuit_breaker_state()

        # Send initial state
        await websocket.send_json({
            "type": "init",
            "data": {
                "running": scanner_running,
                "stats": system_stats,
                "wallets": wallets,
                "environment": runtime_environment,
                "ai_state": ai_state,
                "circuit_breakers": circuit_breaker_state,
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
