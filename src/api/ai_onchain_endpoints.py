"""AI On-Chain API Endpoints for Dashboard Integration.

Provides REST API endpoints for controlling the AI/ML on-chain system
with focus on flash loan profitability optimization.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import structlog

log = structlog.get_logger()

# Create router
router = APIRouter(prefix="/api/ai/onchain", tags=["AI On-Chain System"])

# Global reference to the AI integrated runner (to be set by web_server)
_ai_runner = None


def set_ai_runner(runner):
    """Set the global AI runner reference."""
    global _ai_runner
    _ai_runner = runner


class AIOnChainConfig(BaseModel):
    """AI On-Chain configuration model."""

    # AI Mode
    ai_mode: str = Field(default="balanced", description="AI mode: conservative, balanced, aggressive")

    # Orchestration
    enable_ai_orchestration: bool = Field(default=True, description="Enable AI orchestration")
    enable_profit_maximization: bool = Field(default=True, description="Enable aggressive profit maximization")
    enable_ml_scoring: bool = Field(default=True, description="Enable ML model scoring")

    # Capital and Targets
    current_capital_eth: float = Field(default=100.0, description="Current capital in ETH", gt=0)
    target_capital_eth: float = Field(default=1000.0, description="Target capital in ETH", gt=0)

    # Decision Thresholds
    ai_min_confidence: float = Field(default=0.70, description="Minimum AI confidence", ge=0.5, le=1.0)
    flash_loan_min_profit_eth: float = Field(default=0.15, description="Min profit for flash loans (ETH)", ge=0.05)

    # Position Sizing
    kelly_fraction: float = Field(default=0.25, description="Kelly criterion fraction", gt=0, le=1.0)
    max_leverage: float = Field(default=3.0, description="Maximum leverage multiplier", ge=1.0, le=10.0)

    # Risk Management
    max_daily_losses_usd: float = Field(default=500.0, description="Max daily losses in USD", ge=100)
    max_concurrent_executions: int = Field(default=3, description="Max concurrent executions", ge=1, le=10)

    # Execution Controls
    enable_flash_loans: bool = Field(default=True, description="Enable flash loan execution")


@router.get("/status")
async def get_ai_onchain_status() -> dict[str, Any]:
    """Get AI on-chain system status.

    Returns:
        System enabled status, mode, configuration, and stats
    """
    if not _ai_runner:
        return {
            "enabled": False,
            "mode": "not_initialized",
            "message": "AI integrated runner not initialized"
        }

    try:
        config = _ai_runner.config
        orchestrator_config = config.orchestrator_config

        return {
            "enabled": config.enable_ai_orchestration,
            "mode": config.ai_mode,
            "ai_orchestration": config.enable_ai_orchestration,
            "profit_maximization": config.enable_profit_maximization,
            "ml_scoring": config.ai_config.enable_ml_scoring,
            "flash_loans_enabled": orchestrator_config.enable_flash_loans,
            "current_capital_eth": config.profit_config.current_capital_eth,
            "target_capital_eth": config.profit_config.target_capital_eth,
            "ai_min_confidence": orchestrator_config.ai_min_confidence,
            "flash_loan_min_profit": orchestrator_config.flash_loan_min_profit,
        }
    except Exception as e:
        log.exception("ai_onchain.status_error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_ai_onchain_stats() -> dict[str, Any]:
    """Get AI on-chain performance statistics.

    Returns:
        Decisions, executions, win rate, progress, profitability
    """
    if not _ai_runner:
        return {
            "ai_decisions_made": 0,
            "ai_decisions_executed": 0,
            "win_rate": 0.0,
            "progress_pct": 0.0,
            "message": "AI runner not initialized"
        }

    try:
        stats = _ai_runner.get_stats()

        # Extract orchestrator stats
        orchestrator_stats = stats.get("orchestrator", {})
        ai_stats = orchestrator_stats.get("ai_stats", {})

        # Extract profit maximizer stats
        profit_max_stats = stats.get("profit_maximizer", {})

        return {
            "ai_decisions_made": ai_stats.get("total_predictions", 0),
            "ai_decisions_executed": ai_stats.get("total_executions", 0),
            "win_rate": ai_stats.get("win_rate", 0.0),
            "total_profit_eth": profit_max_stats.get("total_profit_eth", 0.0),
            "net_profit_eth": profit_max_stats.get("net_profit_eth", 0.0),
            "current_capital_eth": profit_max_stats.get("current_capital_eth", 0.0),
            "target_capital_eth": profit_max_stats.get("target_capital_eth", 0.0),
            "progress_pct": profit_max_stats.get("progress_pct", 0.0),
            "roi": profit_max_stats.get("roi", 0.0),
            "ml_model_trained": ai_stats.get("model_trained", False),
            "opportunities_detected": stats.get("opportunities_detected", 0),
            "opportunities_submitted": stats.get("opportunities_submitted", 0),
            "daily_executions": orchestrator_stats.get("daily_executions", 0),
            "daily_profit_usd": orchestrator_stats.get("daily_profit_usd", 0.0),
        }
    except Exception as e:
        log.exception("ai_onchain.stats_error")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def update_ai_onchain_config(config: AIOnChainConfig) -> dict[str, Any]:
    """Update AI on-chain configuration.

    Args:
        config: New AI on-chain configuration

    Returns:
        Success status and updated configuration
    """
    if not _ai_runner:
        raise HTTPException(status_code=503, detail="AI runner not initialized")

    try:
        # Validate growth target
        if config.target_capital_eth <= config.current_capital_eth:
            raise HTTPException(
                status_code=400,
                detail="Target capital must be greater than current capital"
            )

        # Update integrated runner config
        runner_config = _ai_runner.config

        # Update AI mode
        runner_config.ai_mode = config.ai_mode

        # Update orchestration settings
        runner_config.enable_ai_orchestration = config.enable_ai_orchestration
        runner_config.enable_profit_maximization = config.enable_profit_maximization

        # Update AI config
        runner_config.ai_config.enable_ml_scoring = config.enable_ml_scoring

        # Update orchestrator config
        runner_config.orchestrator_config.enable_ai_scoring = config.enable_ai_orchestration
        runner_config.orchestrator_config.ai_min_confidence = config.ai_min_confidence
        runner_config.orchestrator_config.enable_flash_loans = config.enable_flash_loans
        runner_config.orchestrator_config.flash_loan_min_profit = config.flash_loan_min_profit_eth
        runner_config.orchestrator_config.max_concurrent_executions = config.max_concurrent_executions
        runner_config.orchestrator_config.max_daily_losses_usd = config.max_daily_losses_usd
        runner_config.orchestrator_config.portfolio_value_eth = config.current_capital_eth

        # Update AI advanced config
        runner_config.ai_config.confidence_threshold = config.ai_min_confidence
        runner_config.ai_config.kelly_fraction = config.kelly_fraction
        runner_config.ai_config.max_leverage = config.max_leverage

        # Update profit maximizer config
        runner_config.profit_config.current_capital_eth = config.current_capital_eth
        runner_config.profit_config.target_capital_eth = config.target_capital_eth

        # Update the AI decider if the runner has it
        if hasattr(_ai_runner, 'ai_decider'):
            _ai_runner.ai_decider.config.confidence_threshold = config.ai_min_confidence

        # Update orchestrator
        if hasattr(_ai_runner, 'orchestrator'):
            _ai_runner.orchestrator.update_config({
                "ai_min_confidence": config.ai_min_confidence,
                "enable_flash_loans": config.enable_flash_loans,
                "flash_loan_min_profit": config.flash_loan_min_profit_eth,
                "max_concurrent_executions": config.max_concurrent_executions,
                "max_daily_losses_usd": config.max_daily_losses_usd,
                "portfolio_value_eth": config.current_capital_eth,
            })

        # Update profit maximizer
        if hasattr(_ai_runner, 'profit_maximizer') and _ai_runner.profit_maximizer:
            _ai_runner.profit_maximizer.config.current_capital_eth = config.current_capital_eth
            _ai_runner.profit_maximizer.config.target_capital_eth = config.target_capital_eth

        log.info(
            "ai_onchain.config_updated",
            mode=config.ai_mode,
            current_capital=config.current_capital_eth,
            target_capital=config.target_capital_eth,
            confidence=config.ai_min_confidence,
            flash_min_profit=config.flash_loan_min_profit_eth,
        )

        return {
            "success": True,
            "message": f"AI on-chain configuration updated to {config.ai_mode} mode",
            "config": config.dict(),
            "growth_target": f"{config.target_capital_eth / config.current_capital_eth:.1f}x"
        }

    except HTTPException:
        raise
    except Exception as e:
        log.exception("ai_onchain.config_update_failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_ai_onchain_config() -> dict[str, Any]:
    """Get current AI on-chain configuration.

    Returns:
        Current configuration
    """
    if not _ai_runner:
        raise HTTPException(status_code=503, detail="AI runner not initialized")

    try:
        config = _ai_runner.config

        return {
            "ai_mode": config.ai_mode,
            "enable_ai_orchestration": config.enable_ai_orchestration,
            "enable_profit_maximization": config.enable_profit_maximization,
            "enable_ml_scoring": config.ai_config.enable_ml_scoring,
            "current_capital_eth": config.profit_config.current_capital_eth,
            "target_capital_eth": config.profit_config.target_capital_eth,
            "ai_min_confidence": config.orchestrator_config.ai_min_confidence,
            "flash_loan_min_profit_eth": config.orchestrator_config.flash_loan_min_profit,
            "kelly_fraction": config.ai_config.kelly_fraction,
            "max_leverage": config.ai_config.max_leverage,
            "max_daily_losses_usd": config.orchestrator_config.max_daily_losses_usd,
            "max_concurrent_executions": config.orchestrator_config.max_concurrent_executions,
            "enable_flash_loans": config.orchestrator_config.enable_flash_loans,
        }
    except Exception as e:
        log.exception("ai_onchain.get_config_error")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preset/{preset_name}")
async def apply_preset(preset_name: str) -> dict[str, str]:
    """Apply a preset configuration (conservative, balanced, aggressive).

    Args:
        preset_name: Name of preset to apply

    Returns:
        Success status
    """
    if preset_name not in ["conservative", "balanced", "aggressive"]:
        raise HTTPException(
            status_code=400,
            detail="Preset must be 'conservative', 'balanced', or 'aggressive'"
        )

    # Define preset configs
    presets = {
        "conservative": AIOnChainConfig(
            ai_mode="conservative",
            ai_min_confidence=0.75,
            flash_loan_min_profit_eth=0.20,
            kelly_fraction=0.25,
            max_leverage=2.0,
            current_capital_eth=100.0,
            target_capital_eth=500.0,
            max_daily_losses_usd=300.0,
            max_concurrent_executions=2,
        ),
        "balanced": AIOnChainConfig(
            ai_mode="balanced",
            ai_min_confidence=0.70,
            flash_loan_min_profit_eth=0.15,
            kelly_fraction=0.30,
            max_leverage=3.0,
            current_capital_eth=100.0,
            target_capital_eth=1000.0,
            max_daily_losses_usd=500.0,
            max_concurrent_executions=3,
        ),
        "aggressive": AIOnChainConfig(
            ai_mode="aggressive",
            ai_min_confidence=0.60,
            flash_loan_min_profit_eth=0.10,
            kelly_fraction=0.35,
            max_leverage=5.0,
            current_capital_eth=100.0,
            target_capital_eth=2000.0,
            max_daily_losses_usd=1000.0,
            max_concurrent_executions=5,
        ),
    }

    preset = presets[preset_name]
    await update_ai_onchain_config(preset)

    return {
        "status": "success",
        "preset": preset_name,
        "message": f"Applied {preset_name} preset for optimal flash loan profitability"
    }


@router.get("/health")
async def get_ai_onchain_health() -> dict[str, Any]:
    """Get AI on-chain system health indicators.

    Returns:
        Health metrics and alert status
    """
    if not _ai_runner:
        return {
            "status": "not_initialized",
            "message": "AI runner not initialized"
        }

    try:
        stats = await get_ai_onchain_stats()

        # Calculate health indicators
        win_rate = stats.get("win_rate", 0.0)
        daily_executions = stats.get("daily_executions", 0)
        daily_profit = stats.get("daily_profit_usd", 0.0)
        progress_pct = stats.get("progress_pct", 0.0)

        # Determine health status
        alerts = []

        if win_rate < 0.60 and daily_executions > 10:
            alerts.append({
                "type": "low_win_rate",
                "value": win_rate,
                "threshold": 0.60,
                "message": "Win rate below 60% - consider switching to conservative mode"
            })

        if daily_profit < 0 and daily_executions > 5:
            alerts.append({
                "type": "negative_daily_profit",
                "value": daily_profit,
                "message": "Daily profit is negative - review AI settings"
            })

        if progress_pct > 0 and progress_pct < 5.0 and daily_executions > 20:
            alerts.append({
                "type": "slow_progress",
                "value": progress_pct,
                "message": "Slow progress towards target - consider more aggressive settings"
            })

        ml_trained = stats.get("ml_model_trained", False)
        if not ml_trained and daily_executions > 50:
            alerts.append({
                "type": "ml_not_trained",
                "message": "ML model not trained despite 50+ executions - check training data"
            })

        health_status = "healthy" if not alerts else "warning" if len(alerts) < 2 else "critical"

        return {
            "status": health_status,
            "win_rate": win_rate,
            "daily_executions": daily_executions,
            "daily_profit_usd": daily_profit,
            "progress_pct": progress_pct,
            "ml_model_trained": ml_trained,
            "alerts": alerts,
            "recommendations": _get_recommendations(stats, alerts),
        }

    except Exception as e:
        log.exception("ai_onchain.health_check_error")
        raise HTTPException(status_code=500, detail=str(e))


def _get_recommendations(stats: dict, alerts: list) -> list[str]:
    """Generate recommendations based on stats and alerts."""
    recommendations = []

    win_rate = stats.get("win_rate", 0.0)
    progress_pct = stats.get("progress_pct", 0.0)
    ml_trained = stats.get("ml_model_trained", False)

    if win_rate < 0.65:
        recommendations.append("Increase AI confidence threshold to 0.75 for higher quality trades")

    if not ml_trained:
        recommendations.append("Continue trading to collect training data for ML model (50+ samples needed)")

    if progress_pct < 10 and win_rate > 0.70:
        recommendations.append("Good win rate - consider increasing position sizes or using balanced mode")

    if len(alerts) > 2:
        recommendations.append("Multiple alerts detected - switch to conservative mode and review settings")

    if stats.get("daily_profit_usd", 0.0) > 500:
        recommendations.append("Strong daily performance - maintain current settings")

    return recommendations
