"""Production System API Endpoints for Dashboard Integration.

Provides REST API endpoints for:
- Circuit breaker status and controls
- Model versioning and performance
- Market volatility metrics
- TimescaleDB data queries
- System health monitoring
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

log = structlog.get_logger()

# Create router
router = APIRouter(prefix="/api/production", tags=["Production System"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================


class CircuitBreakerControl(BaseModel):
    """Request model for circuit breaker control."""

    action: str = Field(..., description="Action: 'reset_all' or 'attempt_recovery'")
    breaker_type: str | None = Field(None, description="Specific breaker type for recovery")


class ModelVersionQuery(BaseModel):
    """Query parameters for model versions."""

    model_name: str = Field(..., description="Model name")
    limit: int = Field(10, ge=1, le=50, description="Max versions to return")


# ============================================================================
# CIRCUIT BREAKERS
# ============================================================================


@router.get("/circuit-breakers/status")
async def get_circuit_breaker_status() -> dict[str, Any]:
    """Get status of all circuit breakers.

    Returns:
        Status of all circuit breakers with trigger info
    """
    try:
        from src.ai.circuit_breakers import get_circuit_breaker_manager

        manager = get_circuit_breaker_manager()
        status = manager.get_status()

        # Add trading allowed check
        trading_allowed, reason = manager.is_trading_allowed()

        return {
            "trading_allowed": trading_allowed,
            "blocked_reason": reason,
            "breakers": status,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        log.exception("circuit_breakers.status_failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/circuit-breakers/snapshot")
async def get_circuit_breaker_snapshot() -> dict[str, Any]:
    """Get detailed circuit breaker snapshot for monitoring dashboards."""
    try:
        from src.ai.circuit_breakers import get_circuit_breaker_manager

        manager = get_circuit_breaker_manager()
        snapshot = manager.get_status_snapshot()
        trading_allowed, reason = manager.is_trading_allowed()

        return {
            "trading_allowed": trading_allowed,
            "blocked_reason": reason,
            "snapshot": snapshot,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        log.exception("circuit_breakers.snapshot_failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/circuit-breakers/control")
async def control_circuit_breakers(control: CircuitBreakerControl) -> dict[str, Any]:
    """Control circuit breakers (reset or attempt recovery).

    Args:
        control: Circuit breaker control action

    Returns:
        Result of the control action
    """
    try:
        from src.ai.circuit_breakers import (
            CircuitBreakerType,
            get_circuit_breaker_manager,
        )

        manager = get_circuit_breaker_manager()

        if control.action == "reset_all":
            manager.reset_all()
            return {
                "success": True,
                "action": "reset_all",
                "message": "All circuit breakers reset",
            }

        elif control.action == "attempt_recovery":
            if not control.breaker_type:
                raise HTTPException(
                    status_code=400, detail="breaker_type required for recovery"
                )

            try:
                breaker_type = CircuitBreakerType(control.breaker_type)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"Invalid breaker type: {control.breaker_type}"
                )

            success = manager.attempt_recovery(breaker_type)

            return {
                "success": success,
                "action": "attempt_recovery",
                "breaker_type": control.breaker_type,
                "message": (
                    "Recovery initiated" if success else "Recovery not allowed yet"
                ),
            }

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {control.action}")

    except HTTPException:
        raise
    except Exception as e:
        log.exception("circuit_breakers.control_failed")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MODEL VERSIONING
# ============================================================================


@router.get("/models/versions")
async def get_model_versions(
    model_name: str = Query(..., description="Model name"),
    limit: int = Query(10, ge=1, le=50, description="Max versions to return"),
) -> dict[str, Any]:
    """Get version history for a model.

    Args:
        model_name: Name of the model
        limit: Maximum number of versions to return

    Returns:
        List of model versions with metadata
    """
    try:
        from src.ai.model_versioning import get_model_version_manager

        manager = get_model_version_manager()
        versions = manager.list_versions(model_name, source="local")[:limit]

        return {
            "model_name": model_name,
            "versions": versions,
            "count": len(versions),
        }
    except Exception as e:
        log.exception("models.versions_failed", model=model_name)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/current")
async def get_current_models() -> dict[str, Any]:
    """Get information about currently loaded models.

    Returns:
        Status of all ML models
    """
    try:
        from src.ai.model_versioning import get_model_version_manager

        manager = get_model_version_manager()

        models = {}
        for model_name in ["route_success_model", "profit_maximizer", "slippage_xgb"]:
            try:
                _, metadata = manager.load_model(model_name)
                models[model_name] = {
                    "version": metadata.version,
                    "trained_at": metadata.trained_at.isoformat(),
                    "training_samples": metadata.training_samples,
                    "metrics": metadata.metrics,
                    "model_type": metadata.model_type,
                }
            except FileNotFoundError:
                models[model_name] = {"status": "not_found"}
            except Exception as e:
                models[model_name] = {"status": "error", "error": str(e)}

        return {
            "models": models,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        log.exception("models.current_failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/compare")
async def compare_model_versions(
    model_name: str = Query(..., description="Model name"),
    version1: str = Query(..., description="First version"),
    version2: str = Query(..., description="Second version"),
) -> dict[str, Any]:
    """Compare two model versions.

    Args:
        model_name: Name of the model
        version1: First version to compare
        version2: Second version to compare

    Returns:
        Comparison of metrics between versions
    """
    try:
        from src.ai.model_versioning import get_model_version_manager

        manager = get_model_version_manager()
        comparison = manager.compare_versions(model_name, version1, version2)

        return comparison
    except Exception as e:
        log.exception("models.compare_failed", model=model_name)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MARKET VOLATILITY
# ============================================================================


@router.get("/volatility/current")
async def get_current_volatility(
    symbols: str = Query("ETH/USDC,WETH/USDC", description="Comma-separated symbols"),
    chain: str = Query("ethereum", description="Blockchain"),
) -> dict[str, Any]:
    """Get current volatility metrics for symbols.

    Args:
        symbols: Comma-separated list of trading symbols
        chain: Blockchain (ethereum, polygon)

    Returns:
        Current volatility metrics for each symbol
    """
    try:
        from src.ai.market_data import get_market_data_collector

        collector = get_market_data_collector()
        symbol_list = [s.strip() for s in symbols.split(",")]

        volatility_data = {}
        for symbol in symbol_list:
            metrics = await collector.get_latest_volatility(symbol, chain)
            if metrics:
                volatility_data[symbol] = {
                    "price": metrics.price,
                    "volatility_1h": metrics.volatility_1h,
                    "volatility_24h": metrics.volatility_24h,
                    "volatility_7d": metrics.volatility_7d,
                    "returns_1h": metrics.returns_1h,
                    "volume_24h": metrics.volume_24h,
                    "bid_ask_spread_bps": metrics.bid_ask_spread_bps,
                    "timestamp": metrics.timestamp.isoformat(),
                }
            else:
                volatility_data[symbol] = {"status": "no_data"}

        return {
            "chain": chain,
            "volatility": volatility_data,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        log.exception("volatility.current_failed")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DATABASE QUERIES
# ============================================================================


@router.get("/opportunities/recent")
async def get_recent_opportunities(
    hours: int = Query(1, ge=1, le=168, description="Hours to look back"),
    limit: int = Query(50, ge=1, le=500, description="Max results"),
) -> dict[str, Any]:
    """Get recent arbitrage opportunities from database.

    Args:
        hours: Hours to look back
        limit: Maximum number of opportunities

    Returns:
        List of recent opportunities
    """
    try:
        from src.ai.opportunity_logger import get_opportunity_logger

        logger = get_opportunity_logger()
        await logger.connect()

        if not logger.pool:
            raise HTTPException(status_code=503, detail="Database not available")

        rows = await logger.pool.fetch(
            """
            SELECT
                timestamp, symbol, chain, edge_bps, cex_price, dex_price,
                executed, profitable, profit_quote, gas_cost_eth,
                pool_liquidity_quote, gas_price_gwei
            FROM arbitrage_opportunities
            WHERE timestamp > NOW() - $1::INTERVAL
            ORDER BY timestamp DESC
            LIMIT $2
            """,
            f"{hours} hours",
            limit,
        )

        opportunities = [dict(row) for row in rows]

        # Convert timestamps to ISO format
        for opp in opportunities:
            if "timestamp" in opp and opp["timestamp"]:
                opp["timestamp"] = opp["timestamp"].isoformat()

        return {
            "opportunities": opportunities,
            "count": len(opportunities),
            "hours": hours,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("opportunities.query_failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/opportunities/stats")
async def get_opportunity_stats(
    hours: int = Query(24, ge=1, le=168, description="Hours to look back"),
) -> dict[str, Any]:
    """Get aggregate statistics on opportunities.

    Args:
        hours: Hours to look back

    Returns:
        Aggregate statistics
    """
    try:
        from src.ai.opportunity_logger import get_opportunity_logger

        logger = get_opportunity_logger()
        await logger.connect()

        if not logger.pool:
            raise HTTPException(status_code=503, detail="Database not available")

        row = await logger.pool.fetchrow(
            """
            SELECT
                COUNT(*) as total_opportunities,
                COUNT(*) FILTER (WHERE executed = TRUE) as executed,
                COUNT(*) FILTER (WHERE profitable = TRUE) as profitable,
                CAST(COUNT(*) FILTER (WHERE profitable = TRUE) AS FLOAT) /
                    NULLIF(COUNT(*) FILTER (WHERE executed = TRUE), 0) as win_rate,
                AVG(edge_bps) as avg_edge_bps,
                AVG(profit_quote) FILTER (WHERE executed = TRUE AND profitable = TRUE) as avg_profit,
                SUM(profit_quote) FILTER (WHERE executed = TRUE AND profitable = TRUE) as total_profit,
                AVG(gas_cost_eth * 3000) FILTER (WHERE executed = TRUE) as avg_gas_cost_usd
            FROM arbitrage_opportunities
            WHERE timestamp > NOW() - $1::INTERVAL
            """,
            f"{hours} hours",
        )

        return {
            "stats": dict(row) if row else {},
            "hours": hours,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("opportunities.stats_failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/hourly")
async def get_hourly_performance(
    hours: int = Query(24, ge=1, le=168, description="Hours to look back"),
) -> dict[str, Any]:
    """Get hourly performance metrics.

    Args:
        hours: Hours to look back

    Returns:
        Hourly performance breakdown
    """
    try:
        from src.ai.opportunity_logger import get_opportunity_logger

        logger = get_opportunity_logger()
        await logger.connect()

        if not logger.pool:
            raise HTTPException(status_code=503, detail="Database not available")

        rows = await logger.pool.fetch(
            """
            SELECT * FROM hourly_performance
            WHERE timestamp > NOW() - $1::INTERVAL
            ORDER BY timestamp DESC
            """,
            f"{hours} hours",
        )

        performance = [dict(row) for row in rows]

        # Convert timestamps
        for p in performance:
            if "timestamp" in p and p["timestamp"]:
                p["timestamp"] = p["timestamp"].isoformat()

        return {
            "performance": performance,
            "count": len(performance),
            "hours": hours,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("performance.hourly_failed")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SYSTEM HEALTH
# ============================================================================


@router.get("/health")
async def get_system_health() -> dict[str, Any]:
    """Get comprehensive system health status.

    Returns:
        Health status of all subsystems
    """
    health = {
        "timestamp": datetime.utcnow().isoformat(),
        "components": {},
    }

    # Check circuit breakers
    try:
        from src.ai.circuit_breakers import get_circuit_breaker_manager

        manager = get_circuit_breaker_manager()
        trading_allowed, reason = manager.is_trading_allowed()
        health["components"]["circuit_breakers"] = {
            "status": "healthy" if trading_allowed else "circuit_open",
            "trading_allowed": trading_allowed,
            "reason": reason,
        }
    except Exception as e:
        health["components"]["circuit_breakers"] = {
            "status": "error",
            "error": str(e),
        }

    # Check database
    try:
        from src.ai.opportunity_logger import get_opportunity_logger

        logger = get_opportunity_logger()
        await logger.connect()
        health["components"]["database"] = {
            "status": "healthy" if logger.pool else "unavailable",
            "connected": logger.pool is not None,
        }
    except Exception as e:
        health["components"]["database"] = {"status": "error", "error": str(e)}

    # Check ML models
    try:
        from src.ai.model_versioning import get_model_version_manager

        manager = get_model_version_manager()
        model_count = 0
        for model_name in ["route_success_model", "profit_maximizer"]:
            try:
                manager.load_model(model_name)
                model_count += 1
            except:
                pass

        health["components"]["ml_models"] = {
            "status": "healthy" if model_count >= 2 else "degraded",
            "loaded_models": model_count,
        }
    except Exception as e:
        health["components"]["ml_models"] = {"status": "error", "error": str(e)}

    # Overall status
    component_statuses = [c.get("status") for c in health["components"].values()]
    if all(s == "healthy" for s in component_statuses):
        health["overall_status"] = "healthy"
    elif any(s == "error" for s in component_statuses):
        health["overall_status"] = "degraded"
    else:
        health["overall_status"] = "warning"

    return health
