"""AI System API Endpoints for Dashboard Integration.

Provides REST API endpoints for:
- AI metrics and performance stats
- Configuration management
- Model status and controls
- Real-time AI decisions
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.ai.alert_system import Alert, AlertLevel, get_alert_system
from src.ai.circuit_breakers import CircuitBreakerType, get_circuit_breaker_manager
from src.ai.config_manager import get_ai_config_manager, reload_ai_config
from src.ai.metrics import get_metrics_collector
from src.ai.production_safety import get_production_safety_guard
from src.ai.transaction_logger import get_transaction_logger

# Create router
router = APIRouter(prefix="/api/ai", tags=["AI System"])


class AIConfigUpdate(BaseModel):
    """Request model for AI configuration updates."""

    ai_mode: str | None = None
    enable_ai_system: bool | None = None
    ai_min_confidence: float | None = None
    enable_ml_scoring: bool | None = None
    kelly_fraction: float | None = None
    max_leverage: float | None = None
    enable_copy_trading: bool | None = None
    enable_counter_trading: bool | None = None
    portfolio_value_eth: float | None = None


@router.get("/status")
async def get_ai_status() -> dict[str, Any]:
    """Get overall AI system status.

    Returns:
        System enabled status, mode, and uptime
    """
    config_manager = get_ai_config_manager()
    config = config_manager.config

    return {
        "enabled": config.enable_ai_system,
        "mode": config.ai_mode,
        "portfolio_value_eth": config.portfolio_value_eth,
        "ml_enabled": config.advanced_decider.enable_ml_scoring,
    }


@router.get("/metrics")
async def get_ai_metrics() -> dict[str, Any]:
    """Get comprehensive AI performance metrics.

    Returns:
        Decisions, executions, opportunities, profitability, and model stats
    """
    metrics = get_metrics_collector()
    summary = metrics.get_summary()
    recent = metrics.get_recent_performance(window_minutes=60)

    return {
        "summary": summary,
        "recent_hour": recent,
        "timestamp": summary["system"]["last_update"],
    }


@router.get("/metrics/recent")
async def get_recent_metrics(window_minutes: int = 60) -> dict[str, Any]:
    """Get recent AI performance for specified time window.

    Args:
        window_minutes: Time window in minutes (default 60)

    Returns:
        Performance stats for the specified window
    """
    if window_minutes < 1 or window_minutes > 1440:  # Max 24 hours
        raise HTTPException(status_code=400, detail="Window must be 1-1440 minutes")

    metrics = get_metrics_collector()
    return metrics.get_recent_performance(window_minutes=window_minutes)


@router.get("/config")
async def get_ai_config() -> dict[str, Any]:
    """Get current AI configuration.

    Returns:
        All AI component configurations
    """
    config_manager = get_ai_config_manager()
    return config_manager.get_config_dict()


@router.post("/config/update")
async def update_ai_config(updates: AIConfigUpdate) -> dict[str, Any]:
    """Update AI configuration.

    Args:
        updates: Configuration updates to apply

    Returns:
        Updated configuration
    """
    config_manager = get_ai_config_manager()

    # Build update dict from non-None values
    update_dict: dict[str, Any] = {}

    if updates.ai_mode is not None:
        if updates.ai_mode not in ["conservative", "balanced", "aggressive"]:
            raise HTTPException(
                status_code=400,
                detail="ai_mode must be 'conservative', 'balanced', or 'aggressive'",
            )
        update_dict["ai_mode"] = updates.ai_mode

    if updates.enable_ai_system is not None:
        update_dict["enable_ai_system"] = updates.enable_ai_system

    if updates.portfolio_value_eth is not None:
        if updates.portfolio_value_eth <= 0:
            raise HTTPException(status_code=400, detail="portfolio_value_eth must be positive")
        update_dict["portfolio_value_eth"] = updates.portfolio_value_eth

    # Advanced decider updates
    decider_updates: dict[str, Any] = {}
    if updates.ai_min_confidence is not None:
        if not 0.0 <= updates.ai_min_confidence <= 1.0:
            raise HTTPException(status_code=400, detail="ai_min_confidence must be 0.0-1.0")
        decider_updates["confidence_threshold"] = updates.ai_min_confidence

    if updates.enable_ml_scoring is not None:
        decider_updates["enable_ml_scoring"] = updates.enable_ml_scoring

    if updates.kelly_fraction is not None:
        if not 0.0 < updates.kelly_fraction <= 1.0:
            raise HTTPException(status_code=400, detail="kelly_fraction must be 0.0-1.0")
        decider_updates["kelly_fraction"] = updates.kelly_fraction

    if updates.max_leverage is not None:
        if updates.max_leverage < 1.0:
            raise HTTPException(status_code=400, detail="max_leverage must be >= 1.0")
        decider_updates["max_leverage"] = updates.max_leverage

    if decider_updates:
        update_dict["advanced_decider"] = decider_updates

    # Aqua detector updates
    aqua_updates: dict[str, Any] = {}
    if updates.enable_copy_trading is not None:
        aqua_updates["enable_copy_trading"] = updates.enable_copy_trading

    if updates.enable_counter_trading is not None:
        aqua_updates["enable_counter_trading"] = updates.enable_counter_trading

    if aqua_updates:
        update_dict["aqua_detector"] = aqua_updates

    # Apply updates
    try:
        config_manager.update_config(update_dict)
        return {"success": True, "config": config_manager.get_config_dict()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/config/reload")
async def reload_config() -> dict[str, str]:
    """Reload AI configuration from file.

    Returns:
        Success status
    """
    try:
        reload_ai_config()
        return {"status": "success", "message": "Configuration reloaded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models")
async def get_model_status() -> dict[str, Any]:
    """Get AI model training status.

    Returns:
        Status of all ML models
    """
    metrics = get_metrics_collector()
    summary = metrics.get_summary()

    return {
        "models": summary.get("models", {}),
        "total_executions": summary["execution"]["total"],
        "training_data_available": summary["execution"]["total"] >= 50,
    }


@router.get("/decisions/latest")
async def get_latest_decisions(limit: int = 10) -> dict[str, Any]:
    """Get latest AI decisions.

    Args:
        limit: Maximum number of decisions to return (default 10)

    Returns:
        Recent AI decisions with scores and outcomes
    """
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="Limit must be 1-100")

    metrics = get_metrics_collector()

    # Get recent decisions from history
    decisions = list(metrics.decision_history)[-limit:]

    return {
        "decisions": [
            {
                "timestamp": timestamp.isoformat(),
                "confidence": data["confidence"],
                "edge_bps": data["edge_bps"],
                "predicted_profit": data["predicted_profit"],
                "executed": data["executed"],
            }
            for timestamp, data in decisions
        ],
        "count": len(decisions),
    }


@router.get("/performance/chart")
async def get_performance_chart() -> dict[str, Any]:
    """Get performance data formatted for charting.

    Returns:
        Time-series data for profit, win rate, confidence
    """
    metrics = get_metrics_collector()

    # Extract time-series data
    profit_data = [
        {"timestamp": ts.isoformat(), "profit": profit} for ts, profit in metrics.profit_history
    ]

    decision_data = [
        {
            "timestamp": ts.isoformat(),
            "confidence": data["confidence"],
            "edge_bps": data["edge_bps"],
        }
        for ts, data in metrics.decision_history
    ]

    return {
        "profit_over_time": profit_data,
        "decisions_over_time": decision_data,
        "total_points": len(profit_data),
    }


@router.post("/enable")
async def enable_ai_system() -> dict[str, str]:
    """Enable AI system.

    Returns:
        Success status
    """
    config_manager = get_ai_config_manager()
    config_manager.update_config({"enable_ai_system": True})
    return {"status": "success", "message": "AI system enabled"}


@router.post("/disable")
async def disable_ai_system() -> dict[str, str]:
    """Disable AI system.

    Returns:
        Success status
    """
    config_manager = get_ai_config_manager()
    config_manager.update_config({"enable_ai_system": False})
    return {"status": "success", "message": "AI system disabled"}


@router.post("/mode/{mode}")
async def set_ai_mode(mode: str) -> dict[str, str]:
    """Set AI risk mode.

    Args:
        mode: One of 'conservative', 'balanced', 'aggressive'

    Returns:
        Success status with new mode
    """
    if mode not in ["conservative", "balanced", "aggressive"]:
        raise HTTPException(
            status_code=400, detail="Mode must be 'conservative', 'balanced', or 'aggressive'"
        )

    config_manager = get_ai_config_manager()
    config_manager.update_config({"ai_mode": mode})

    return {"status": "success", "mode": mode, "message": f"AI mode set to {mode}"}


@router.get("/health")
async def get_ai_health() -> dict[str, Any]:
    """Get AI system health indicators.

    Returns:
        Health metrics and alert status
    """
    metrics = get_metrics_collector()
    summary = metrics.get_summary()

    # Calculate health indicators
    win_rate = summary["decisions"].get("win_rate", 0.0)
    success_rate = summary["execution"].get("success_rate", 0.0)
    net_profit = summary["execution"].get("net_profit_usd", 0.0)

    # Determine health status
    alerts = []
    if win_rate < 0.45:
        alerts.append({"type": "low_win_rate", "value": win_rate, "threshold": 0.45})

    if success_rate < 0.70:
        alerts.append({"type": "low_success_rate", "value": success_rate, "threshold": 0.70})

    if net_profit < 0:
        alerts.append({"type": "negative_profit", "value": net_profit})

    health_status = "healthy" if not alerts else "warning" if len(alerts) < 2 else "critical"

    return {
        "status": health_status,
        "win_rate": win_rate,
        "success_rate": success_rate,
        "net_profit": net_profit,
        "alerts": alerts,
        "uptime_seconds": summary["system"]["uptime_seconds"],
    }


# ============================================================================
# PRODUCTION SAFETY ENDPOINTS
# ============================================================================


@router.get("/safety/status")
async def get_safety_status() -> dict[str, Any]:
    """Get production safety guard status.

    Returns:
        Safety limits, current usage, and emergency shutdown status
    """
    safety = get_production_safety_guard()
    return safety.get_status()


@router.get("/safety/stats")
async def get_safety_stats() -> dict[str, Any]:
    """Get production safety statistics.

    Returns:
        Trade counts, P&L tracking, limit usage
    """
    safety = get_production_safety_guard()
    return safety.get_status()


@router.post("/safety/reset")
async def reset_safety_shutdown(reason: str = "Manual reset from API") -> dict[str, str]:
    """Reset emergency shutdown state.

    ⚠️ Use with caution - only after addressing the root cause.

    Args:
        reason: Reason for reset

    Returns:
        Success status
    """
    safety = get_production_safety_guard()
    safety.reset_emergency_shutdown(reason=reason)
    return {"status": "success", "message": "Emergency shutdown reset", "reason": reason}


# ============================================================================
# CIRCUIT BREAKER ENDPOINTS
# ============================================================================


@router.get("/circuit-breakers")
async def get_circuit_breakers() -> dict[str, Any]:
    """Get all circuit breaker states.

    Returns:
        Status of all circuit breakers with current values and thresholds
    """
    breakers = get_circuit_breaker_manager()
    return breakers.get_status()


@router.get("/circuit-breakers/{breaker_type}")
async def get_circuit_breaker(breaker_type: str) -> dict[str, Any]:
    """Get specific circuit breaker status.

    Args:
        breaker_type: Type of breaker (win_rate, drawdown, gas_cost, etc.)

    Returns:
        Breaker status with current value and threshold
    """
    breakers = get_circuit_breaker_manager()
    status = breakers.get_status()

    if breaker_type not in status["breakers"]:
        raise HTTPException(status_code=404, detail=f"Circuit breaker '{breaker_type}' not found")

    return {
        "type": breaker_type,
        **status["breakers"][breaker_type],
        "trading_allowed": status["trading_allowed"],
    }


@router.post("/circuit-breakers/{breaker_type}/reset")
async def reset_circuit_breaker(breaker_type: str) -> dict[str, str]:
    """Attempt to reset a specific circuit breaker.

    Args:
        breaker_type: Type of breaker to reset

    Returns:
        Success status with new state
    """
    breakers = get_circuit_breaker_manager()

    # Convert string to enum
    try:
        breaker_enum = CircuitBreakerType(breaker_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid breaker_type '{breaker_type}'. Valid types: {[e.value for e in CircuitBreakerType]}",
        )

    # Attempt recovery
    recovered = breakers.attempt_recovery(breaker_enum)

    if recovered:
        return {
            "status": "success",
            "message": f"Circuit breaker '{breaker_type}' recovered",
            "breaker_type": breaker_type,
        }
    else:
        return {
            "status": "failed",
            "message": f"Circuit breaker '{breaker_type}' could not be recovered - conditions not met",
            "breaker_type": breaker_type,
        }


@router.get("/circuit-breakers/history")
async def get_circuit_breaker_history(limit: int = 50) -> dict[str, Any]:
    """Get circuit breaker event history.

    Args:
        limit: Maximum number of events to return

    Returns:
        Recent circuit breaker trigger events
    """
    # Note: Circuit breaker history tracking not yet implemented
    # Would require adding event logging to CircuitBreakerManager
    return {
        "events": [],
        "count": 0,
        "message": "Circuit breaker event history not yet implemented",
    }


# ============================================================================
# TRANSACTION LOGGER ENDPOINTS
# ============================================================================


@router.get("/trades/history")
async def get_trade_history(limit: int = 50) -> dict[str, Any]:
    """Get trade execution history.

    Args:
        limit: Maximum number of trades to return (1-500)

    Returns:
        Recent trades with decisions and execution results
    """
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="Limit must be 1-500")

    tx_logger = get_transaction_logger()
    return tx_logger.get_session_stats()


@router.get("/trades/stats")
async def get_trade_stats() -> dict[str, Any]:
    """Get comprehensive trading statistics.

    Returns:
        Win rate, P&L, execution metrics, AI performance
    """
    tx_logger = get_transaction_logger()
    return tx_logger.get_session_stats()


@router.get("/trades/export/csv")
async def export_trades_csv() -> dict[str, str]:
    """Export trade history to CSV.

    Returns:
        CSV file path and row count
    """
    tx_logger = get_transaction_logger()

    return {
        "status": "success",
        "filepath": str(tx_logger.csv_path),
        "format": "csv",
        "message": "CSV file is continuously updated during session",
    }


@router.get("/trades/export/json")
async def export_trades_json() -> dict[str, str]:
    """Export trade history to JSON.

    Returns:
        JSON file path and record count
    """
    tx_logger = get_transaction_logger()

    return {
        "status": "success",
        "filepath": str(tx_logger.json_path),
        "format": "json",
        "message": "JSONL file is continuously updated during session",
    }


@router.get("/metrics/prometheus")
async def get_prometheus_metrics() -> str:
    """Export metrics in Prometheus format.

    Returns:
        Metrics in Prometheus exposition format
    """
    metrics = get_metrics_collector()
    summary = metrics.get_summary()

    # Build Prometheus metrics format
    lines = []

    # Decisions metrics
    lines.append("# HELP arbitrage_decisions_total Total number of AI decisions made")
    lines.append("# TYPE arbitrage_decisions_total counter")
    lines.append(f"arbitrage_decisions_total {summary['decisions']['total']}")

    lines.append("# HELP arbitrage_decisions_executed_total Total decisions executed")
    lines.append("# TYPE arbitrage_decisions_executed_total counter")
    lines.append(f"arbitrage_decisions_executed_total {summary['decisions']['executed']}")

    lines.append("# HELP arbitrage_avg_confidence Average AI confidence")
    lines.append("# TYPE arbitrage_avg_confidence gauge")
    lines.append(f"arbitrage_avg_confidence {summary['decisions']['avg_confidence']}")

    lines.append("# HELP arbitrage_avg_edge_bps Average edge in basis points")
    lines.append("# TYPE arbitrage_avg_edge_bps gauge")
    lines.append(f"arbitrage_avg_edge_bps {summary['decisions']['avg_edge_bps']}")

    lines.append("# HELP arbitrage_win_rate Win rate ratio (0-1)")
    lines.append("# TYPE arbitrage_win_rate gauge")
    lines.append(f"arbitrage_win_rate {summary['decisions']['win_rate']}")

    lines.append("# HELP arbitrage_sharpe_ratio Sharpe ratio")
    lines.append("# TYPE arbitrage_sharpe_ratio gauge")
    lines.append(f"arbitrage_sharpe_ratio {summary['decisions']['sharpe_ratio']}")

    # Execution metrics
    lines.append("# HELP arbitrage_executions_total Total execution attempts")
    lines.append("# TYPE arbitrage_executions_total counter")
    lines.append(f"arbitrage_executions_total {summary['execution']['total']}")

    lines.append("# HELP arbitrage_executions_successful_total Successful executions")
    lines.append("# TYPE arbitrage_executions_successful_total counter")
    lines.append(f"arbitrage_executions_successful_total {summary['execution']['successful']}")

    lines.append("# HELP arbitrage_executions_failed_total Failed executions")
    lines.append("# TYPE arbitrage_executions_failed_total counter")
    lines.append(f"arbitrage_executions_failed_total {summary['execution']['failed']}")

    lines.append("# HELP arbitrage_success_rate Execution success rate (0-1)")
    lines.append("# TYPE arbitrage_success_rate gauge")
    lines.append(f"arbitrage_success_rate {summary['execution']['success_rate']}")

    lines.append("# HELP arbitrage_total_profit_usd Total profit in USD")
    lines.append("# TYPE arbitrage_total_profit_usd counter")
    lines.append(f"arbitrage_total_profit_usd {summary['execution']['total_profit_usd']}")

    lines.append("# HELP arbitrage_total_gas_cost_usd Total gas cost in USD")
    lines.append("# TYPE arbitrage_total_gas_cost_usd counter")
    lines.append(f"arbitrage_total_gas_cost_usd {summary['execution']['total_gas_cost_usd']}")

    lines.append("# HELP arbitrage_net_profit_usd Net profit (profit - gas) in USD")
    lines.append("# TYPE arbitrage_net_profit_usd gauge")
    lines.append(f"arbitrage_net_profit_usd {summary['execution']['net_profit_usd']}")

    lines.append("# HELP arbitrage_avg_execution_time_ms Average execution time in milliseconds")
    lines.append("# TYPE arbitrage_avg_execution_time_ms gauge")
    lines.append(f"arbitrage_avg_execution_time_ms {summary['execution']['avg_execution_time_ms']}")

    # Opportunities metrics
    lines.append("# HELP arbitrage_opportunities_detected_total Total opportunities detected")
    lines.append("# TYPE arbitrage_opportunities_detected_total counter")
    lines.append(f"arbitrage_opportunities_detected_total {summary['opportunities']['detected']}")

    lines.append("# HELP arbitrage_opportunities_executed_total Opportunities executed")
    lines.append("# TYPE arbitrage_opportunities_executed_total counter")
    lines.append(f"arbitrage_opportunities_executed_total {summary['opportunities']['executed']}")

    lines.append("# HELP arbitrage_conversion_rate Opportunity conversion rate (0-1)")
    lines.append("# TYPE arbitrage_conversion_rate gauge")
    lines.append(f"arbitrage_conversion_rate {summary['opportunities']['conversion_rate']}")

    lines.append("# HELP arbitrage_avg_opportunity_quality Average opportunity quality score")
    lines.append("# TYPE arbitrage_avg_opportunity_quality gauge")
    lines.append(f"arbitrage_avg_opportunity_quality {summary['opportunities']['avg_quality']}")

    # System metrics
    lines.append("# HELP arbitrage_uptime_seconds System uptime in seconds")
    lines.append("# TYPE arbitrage_uptime_seconds counter")
    lines.append(f"arbitrage_uptime_seconds {summary['system']['uptime_seconds']}")

    return "\n".join(lines)


# ============================================================================
# ALERT SYSTEM ENDPOINTS
# ============================================================================


@router.post("/alerts/test")
async def test_alert_system() -> dict[str, str]:
    """Send a test alert to verify Discord integration.

    Returns:
        Success status
    """
    from datetime import datetime

    alert_system = get_alert_system()

    # Create a test alert
    test_alert = Alert(
        level=AlertLevel.INFO,
        title="🧪 Test Alert",
        message="This is a test alert from the API endpoint. If you see this, your alert system is working correctly!",
        timestamp=datetime.utcnow(),
        data={"source": "API", "endpoint": "/api/ai/alerts/test"},
    )

    # Send the alert
    alert_system._send_alert(test_alert, force=True)

    return {
        "status": "success",
        "message": "Test alert sent - check Discord channel",
    }
