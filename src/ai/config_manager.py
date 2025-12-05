"""Unified AI configuration management for all AI components.

Centralizes configuration for:
- Advanced AI Decider
- RL Policy
- Aqua Opportunity Detector
- Flash Arbitrage AI Runner

Supports:
- Environment variable overrides
- JSON config file loading
- Dynamic updates
- Validation and defaults
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from src.ai.advanced_decider import AdvancedAIConfig
from src.ai.rl_policy import RLPolicyConfig
from src.ai.aqua_opportunity_detector import AquaOpportunityConfig
from src.live.ai_flash_runner import AIFlashArbConfig

log = structlog.get_logger()


@dataclass
class AISystemConfig:
    """Master configuration for entire AI system."""

    # Component configs
    advanced_decider: AdvancedAIConfig = field(default_factory=AdvancedAIConfig)
    rl_policy: RLPolicyConfig = field(default_factory=RLPolicyConfig)
    aqua_detector: AquaOpportunityConfig = field(default_factory=AquaOpportunityConfig)
    flash_runner: AIFlashArbConfig = field(default_factory=AIFlashArbConfig)

    # Global AI settings
    enable_ai_system: bool = True  # Master switch for all AI
    ai_mode: str = "conservative"  # "conservative", "balanced", "aggressive"
    portfolio_value_eth: float = 100.0  # Current portfolio value

    # Model paths
    model_directory: Path = field(default_factory=lambda: Path("models"))
    route_predictor_path: Path = field(
        default_factory=lambda: Path("models/route_success_model.pkl")
    )
    rl_policy_path: Path = field(default_factory=lambda: Path("models/rl_policy_model.pkl"))

    # Monitoring
    enable_metrics: bool = True
    metrics_port: int = 9090
    log_level: str = "INFO"


class AIConfigManager:
    """Centralized configuration manager for AI system.

    Features:
    - Load from JSON config file
    - Override with environment variables
    - Validate configurations
    - Apply risk profiles (conservative/balanced/aggressive)
    - Hot-reload configuration
    """

    def __init__(self, config_path: Path | None = None):
        """Initialize config manager.

        Args:
            config_path: Path to JSON config file (optional)
        """
        self.config_path = config_path or Path("config/ai_config.json")
        self.config = AISystemConfig()
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file and environment."""
        # Load from JSON file if exists
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    config_dict = json.load(f)
                self._apply_config_dict(config_dict)
                log.info("ai_config.loaded_from_file", path=str(self.config_path))
            except Exception:
                log.exception("ai_config.load_failed")

        # Override with environment variables
        self._apply_env_overrides()

        # Apply risk profile
        self._apply_risk_profile()

        # Validate configuration
        self._validate_config()

        log.info(
            "ai_config.initialized",
            mode=self.config.ai_mode,
            ai_enabled=self.config.enable_ai_system,
        )

    def _apply_config_dict(self, config_dict: dict[str, Any]) -> None:
        """Apply configuration from dictionary."""
        # Advanced Decider config
        if "advanced_decider" in config_dict:
            decider_config = config_dict["advanced_decider"]
            for key, value in decider_config.items():
                if hasattr(self.config.advanced_decider, key):
                    setattr(self.config.advanced_decider, key, value)

        # RL Policy config
        if "rl_policy" in config_dict:
            rl_config = config_dict["rl_policy"]
            for key, value in rl_config.items():
                if hasattr(self.config.rl_policy, key):
                    setattr(self.config.rl_policy, key, value)

        # Aqua Detector config
        if "aqua_detector" in config_dict:
            aqua_config = config_dict["aqua_detector"]
            for key, value in aqua_config.items():
                if hasattr(self.config.aqua_detector, key):
                    setattr(self.config.aqua_detector, key, value)

        # Flash Runner config
        if "flash_runner" in config_dict:
            flash_config = config_dict["flash_runner"]
            for key, value in flash_config.items():
                if hasattr(self.config.flash_runner, key):
                    setattr(self.config.flash_runner, key, value)

        # Global AI settings
        for key in ["enable_ai_system", "ai_mode", "portfolio_value_eth"]:
            if key in config_dict:
                setattr(self.config, key, config_dict[key])

    def _apply_env_overrides(self) -> None:
        """Override config with environment variables."""
        # Global settings
        if "AI_ENABLED" in os.environ:
            self.config.enable_ai_system = os.environ["AI_ENABLED"].lower() == "true"

        if "AI_MODE" in os.environ:
            self.config.ai_mode = os.environ["AI_MODE"]

        if "PORTFOLIO_VALUE_ETH" in os.environ:
            self.config.portfolio_value_eth = float(os.environ["PORTFOLIO_VALUE_ETH"])

        # Advanced Decider settings
        if "AI_MIN_CONFIDENCE" in os.environ:
            self.config.advanced_decider.confidence_threshold = float(
                os.environ["AI_MIN_CONFIDENCE"]
            )
            self.config.flash_runner.ai_min_confidence = float(os.environ["AI_MIN_CONFIDENCE"])

        if "AI_ML_ENABLED" in os.environ:
            self.config.advanced_decider.enable_ml_scoring = (
                os.environ["AI_ML_ENABLED"].lower() == "true"
            )

        # Aqua Detector settings
        if "AQUA_ENABLE_COPY_TRADING" in os.environ:
            self.config.aqua_detector.enable_copy_trading = (
                os.environ["AQUA_ENABLE_COPY_TRADING"].lower() == "true"
            )

        if "AQUA_ENABLE_COUNTER_TRADING" in os.environ:
            self.config.aqua_detector.enable_counter_trading = (
                os.environ["AQUA_ENABLE_COUNTER_TRADING"].lower() == "true"
            )

        # RL Policy settings
        if "RL_EPSILON" in os.environ:
            self.config.rl_policy.epsilon_start = float(os.environ["RL_EPSILON"])

        if "RL_LEARNING_RATE" in os.environ:
            self.config.rl_policy.learning_rate = float(os.environ["RL_LEARNING_RATE"])

    def _apply_risk_profile(self) -> None:
        """Apply risk profile adjustments."""
        mode = self.config.ai_mode

        if mode == "conservative":
            # Conservative: Lower leverage, higher confidence requirements
            self.config.advanced_decider.confidence_threshold = 0.75
            self.config.advanced_decider.kelly_fraction = 0.15
            self.config.advanced_decider.max_leverage = 2.0

            self.config.flash_runner.ai_min_confidence = 0.75
            self.config.flash_runner.max_flash_borrow_eth = 50.0
            self.config.flash_runner.min_flash_profit_eth = 0.20

            self.config.rl_policy.max_position_size = 5.0
            self.config.rl_policy.min_edge_bps = 35.0

            self.config.aqua_detector.enable_copy_trading = False
            self.config.aqua_detector.max_position_size_usd = 2_000.0

            log.info("ai_config.profile_applied", mode="conservative")

        elif mode == "balanced":
            # Balanced: Default settings (already set)
            log.info("ai_config.profile_applied", mode="balanced")

        elif mode == "aggressive":
            # Aggressive: Higher leverage, lower confidence requirements
            self.config.advanced_decider.confidence_threshold = 0.60
            self.config.advanced_decider.kelly_fraction = 0.35
            self.config.advanced_decider.max_leverage = 5.0

            self.config.flash_runner.ai_min_confidence = 0.65
            self.config.flash_runner.max_flash_borrow_eth = 200.0
            self.config.flash_runner.min_flash_profit_eth = 0.10

            self.config.rl_policy.max_position_size = 20.0
            self.config.rl_policy.min_edge_bps = 15.0

            self.config.aqua_detector.enable_copy_trading = True
            self.config.aqua_detector.max_position_size_usd = 10_000.0

            log.info("ai_config.profile_applied", mode="aggressive")

        else:
            log.warning("ai_config.unknown_mode", mode=mode)

    def _validate_config(self) -> None:
        """Validate configuration values."""
        # Confidence thresholds
        assert 0.0 <= self.config.advanced_decider.confidence_threshold <= 1.0
        assert 0.0 <= self.config.flash_runner.ai_min_confidence <= 1.0

        # Kelly fraction
        assert 0.0 < self.config.advanced_decider.kelly_fraction <= 1.0

        # Leverage
        assert self.config.advanced_decider.max_leverage >= 1.0

        # Portfolio value
        assert self.config.portfolio_value_eth > 0

        # Flash loan amounts
        assert (
            self.config.flash_runner.min_flash_borrow_eth
            <= self.config.flash_runner.max_flash_borrow_eth
        )

        log.debug("ai_config.validation_passed")

    def save_config(self, path: Path | None = None) -> None:
        """Save current configuration to JSON file."""
        save_path = path or self.config_path

        config_dict = {
            "enable_ai_system": self.config.enable_ai_system,
            "ai_mode": self.config.ai_mode,
            "portfolio_value_eth": self.config.portfolio_value_eth,
            "advanced_decider": {
                "confidence_threshold": self.config.advanced_decider.confidence_threshold,
                "enable_ml_scoring": self.config.advanced_decider.enable_ml_scoring,
                "kelly_fraction": self.config.advanced_decider.kelly_fraction,
                "max_leverage": self.config.advanced_decider.max_leverage,
                "edge_weight": self.config.advanced_decider.edge_weight,
                "execution_risk_weight": self.config.advanced_decider.execution_risk_weight,
            },
            "rl_policy": {
                "learning_rate": self.config.rl_policy.learning_rate,
                "epsilon_start": self.config.rl_policy.epsilon_start,
                "max_position_size": self.config.rl_policy.max_position_size,
                "min_edge_bps": self.config.rl_policy.min_edge_bps,
            },
            "aqua_detector": {
                "enable_copy_trading": self.config.aqua_detector.enable_copy_trading,
                "enable_counter_trading": self.config.aqua_detector.enable_counter_trading,
                "min_confidence": self.config.aqua_detector.min_confidence,
                "max_position_size_usd": self.config.aqua_detector.max_position_size_usd,
            },
            "flash_runner": {
                "enable_ai_scoring": self.config.flash_runner.enable_ai_scoring,
                "ai_min_confidence": self.config.flash_runner.ai_min_confidence,
                "max_flash_borrow_eth": self.config.flash_runner.max_flash_borrow_eth,
                "min_flash_profit_eth": self.config.flash_runner.min_flash_profit_eth,
            },
        }

        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w") as f:
            json.dump(config_dict, f, indent=2)

        log.info("ai_config.saved", path=str(save_path))

    def update_config(self, updates: dict[str, Any]) -> None:
        """Update configuration dynamically.

        Args:
            updates: Dictionary of config updates
        """
        self._apply_config_dict(updates)
        self._validate_config()
        log.info("ai_config.updated", updates=updates)

    def get_config(self) -> AISystemConfig:
        """Get current configuration."""
        return self.config

    def get_config_dict(self) -> dict[str, Any]:
        """Get configuration as dictionary."""
        return {
            "enable_ai_system": self.config.enable_ai_system,
            "ai_mode": self.config.ai_mode,
            "portfolio_value_eth": self.config.portfolio_value_eth,
            "advanced_decider": {
                "confidence_threshold": self.config.advanced_decider.confidence_threshold,
                "enable_ml_scoring": self.config.advanced_decider.enable_ml_scoring,
                "kelly_fraction": self.config.advanced_decider.kelly_fraction,
            },
            "rl_policy": {
                "learning_rate": self.config.rl_policy.learning_rate,
                "epsilon": self.config.rl_policy.epsilon_start,
            },
            "aqua_detector": {
                "enable_copy_trading": self.config.aqua_detector.enable_copy_trading,
                "enable_counter_trading": self.config.aqua_detector.enable_counter_trading,
            },
            "flash_runner": {
                "enable_ai_scoring": self.config.flash_runner.enable_ai_scoring,
                "ai_min_confidence": self.config.flash_runner.ai_min_confidence,
            },
        }


# Singleton instance
_config_manager: AIConfigManager | None = None


def get_ai_config_manager() -> AIConfigManager:
    """Get global AI config manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = AIConfigManager()
    return _config_manager


def reload_ai_config() -> None:
    """Reload configuration from file."""
    global _config_manager
    _config_manager = AIConfigManager()
    log.info("ai_config.reloaded")
