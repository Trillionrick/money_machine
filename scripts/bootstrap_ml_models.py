"""Bootstrap ML models with synthetic training data for cold-start.

This script generates synthetic execution history to pre-train ML models
before live trading data is available. Useful for:
1. Testing ML pipeline end-to-end
2. Providing baseline models before real data collection
3. Validating model training infrastructure

Run this before starting live trading to initialize ML models.

Modern implementation (2025):
- Pydantic BaseSettings for configuration management
- Explicit type conversions for numpy types
- Environment variable integration
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

import numpy as np
import structlog
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.ai.advanced_decider import AdvancedAIConfig, AdvancedAIDecider, ExecutionHistory
from src.ai.profit_maximizer import (
    FlashLoanProfitPredictor,
    ProfitMaximizerConfig,
)
from src.ai.slippage_predictor import SlippageFeatures, SlippagePredictor

log = structlog.get_logger()


class BootstrapConfig(BaseSettings):
    """Configuration for ML model bootstrapping with optional overrides.

    All fields have sensible defaults and can be overridden via environment variables.
    Example:
        BOOTSTRAP_NUM_SAMPLES=200 python scripts/bootstrap_ml_models.py
    """

    model_config = SettingsConfigDict(
        env_prefix="BOOTSTRAP_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Sample generation
    num_samples: Annotated[
        int,
        Field(
            ge=10,
            le=10000,
            description="Number of synthetic samples to generate",
        ),
    ] = 100

    success_rate: Annotated[
        float,
        Field(
            ge=0.1,
            le=1.0,
            description="Target success rate for synthetic executions",
        ),
    ] = 0.70

    slippage_samples: Annotated[
        int,
        Field(
            ge=10,
            le=1000,
            description="Number of synthetic slippage samples",
        ),
    ] = 50

    # Model paths (optional overrides)
    model_dir: Annotated[
        Path,
        Field(description="Directory for saving trained models"),
    ] = Path("models")

    data_dir: Annotated[
        Path,
        Field(description="Directory for training data"),
    ] = Path("data")

    # Training parameters
    xgb_rounds: Annotated[
        int,
        Field(
            ge=10,
            le=1000,
            description="Number of XGBoost training rounds",
        ),
    ] = 100

    # Trading pairs and chains
    symbols: Annotated[
        list[str],
        Field(description="Trading pairs for synthetic data generation"),
    ] = [
        "ETH/USDC",
        "WETH/USDC",
        "ETH/USDT",
        "BTC/USDT",
        "WBTC/USDC",
        "LINK/USDC",
        "UNI/USDC",
        "AAVE/USDC",
    ]

    chains: Annotated[
        list[str],
        Field(description="Blockchain networks for synthetic data"),
    ] = ["ethereum", "polygon"]


# Global config instance (can be overridden via env vars)
config = BootstrapConfig()


def generate_synthetic_execution_history(
    num_samples: int | None = None,
    success_rate: float | None = None,
) -> list[ExecutionHistory]:
    """Generate synthetic execution history for ML training.

    Args:
        num_samples: Number of synthetic executions (uses config default if None)
        success_rate: Target success rate 0.0-1.0 (uses config default if None)

    Returns:
        List of synthetic ExecutionHistory objects
    """
    num_samples = num_samples or config.num_samples
    success_rate = success_rate or config.success_rate

    log.info("bootstrap.generating_history", samples=num_samples, success_rate=success_rate)

    history: list[ExecutionHistory] = []
    start_time = datetime.now(timezone.utc) - timedelta(days=30)

    for i in range(num_samples):
        # Random parameters
        symbol = random.choice(config.symbols)
        chain = random.choice(config.chains)
        timestamp = start_time + timedelta(hours=i * 0.5)

        # Edge: higher edges have higher success probability
        edge_bps = random.uniform(10.0, 150.0)
        edge_quality = edge_bps / 150.0  # Normalize to [0, 1]

        # Predicted profit based on edge
        predicted_profit = random.uniform(50.0, 500.0) * (edge_quality + 0.5)

        # Gas cost (Ethereum higher than Polygon)
        if chain == "ethereum":
            gas_cost = random.uniform(20.0, 80.0)
        else:
            gas_cost = random.uniform(5.0, 20.0)

        # Slippage increases with trade size and decreases with liquidity
        slippage_bps = random.uniform(5.0, 50.0)

        # Success probability based on multiple factors
        # Higher edge, lower gas ratio, lower slippage = higher success
        gas_ratio = gas_cost / max(1.0, predicted_profit)
        success_factors = [
            edge_quality,  # Higher edge
            1.0 - min(1.0, gas_ratio),  # Lower gas ratio
            1.0 - min(1.0, slippage_bps / 100.0),  # Lower slippage
            0.7,  # Base success rate
        ]
        base_success_prob = float(np.mean(success_factors))

        # Add randomness - explicitly convert to Python bool to avoid numpy.bool_
        success = bool(random.random() < (base_success_prob * (success_rate / 0.7)))

        # Actual profit
        if success:
            # Successful trades capture 80-100% of predicted profit
            capture_ratio = random.uniform(0.80, 1.00)
            actual_profit = predicted_profit * capture_ratio - gas_cost
        else:
            # Failed trades lose gas cost
            actual_profit = -gas_cost

        # Route ID
        route_id = f"{symbol}:{chain}"

        history.append(
            ExecutionHistory(
                timestamp=timestamp,
                symbol=symbol,
                edge_bps=edge_bps,
                predicted_profit=predicted_profit,
                actual_profit=actual_profit,
                success=success,
                gas_cost=gas_cost,
                slippage_bps=slippage_bps,
                route_id=route_id,
                chain=chain,
            )
        )

    successful = sum(1 for h in history if h.success)
    actual_success_rate = successful / len(history) if history else 0.0
    successful_profits = [h.actual_profit for h in history if h.success]

    log.info(
        "bootstrap.history_generated",
        total=len(history),
        successful=successful,
        success_rate=actual_success_rate,
        avg_profit=float(np.mean(successful_profits)) if successful_profits else 0.0,
    )

    return history


def generate_synthetic_slippage_data(
    num_samples: int | None = None,
) -> list[tuple[SlippageFeatures, float]]:
    """Generate synthetic slippage training data.

    Args:
        num_samples: Number of samples (uses config default if None)

    Returns:
        List of (features, actual_slippage_bps) tuples
    """
    num_samples = num_samples or config.slippage_samples

    log.info("bootstrap.generating_slippage_data", samples=num_samples)

    training_data: list[tuple[SlippageFeatures, float]] = []

    for _ in range(num_samples):
        # Trade parameters
        trade_size_quote = random.uniform(100.0, 50000.0)
        pool_liquidity_quote = random.uniform(10000.0, 5000000.0)
        price_volatility_1h = random.uniform(0.1, 10.0)
        gas_price_gwei = random.uniform(10.0, 200.0)
        hour_of_day = random.randint(0, 23)
        is_polygon = random.choice([True, False])
        hop_count = random.randint(1, 3)

        # Slippage model:
        # Base: size ratio effect
        size_ratio = trade_size_quote / pool_liquidity_quote
        base_slippage = 10.0 * size_ratio  # 1% trade = 10 bps slippage

        # Volatility increases slippage
        volatility_multiplier = 1.0 + (price_volatility_1h / 10.0)

        # High gas (congestion) increases slippage
        gas_multiplier = 1.0 + (gas_price_gwei - 50.0) / 100.0

        # Polygon has lower slippage
        chain_multiplier = 0.7 if is_polygon else 1.0

        # Multi-hop increases slippage
        hop_multiplier = 1.0 + (hop_count - 1) * 0.15

        # Calculate actual slippage with noise
        actual_slippage_bps = (
            base_slippage
            * volatility_multiplier
            * gas_multiplier
            * chain_multiplier
            * hop_multiplier
            * random.uniform(0.8, 1.2)  # Add noise
        )

        # Minimum slippage
        actual_slippage_bps = max(1.0, actual_slippage_bps)

        features = SlippageFeatures(
            trade_size_quote=trade_size_quote,
            pool_liquidity_quote=pool_liquidity_quote,
            price_volatility_1h=price_volatility_1h,
            gas_price_gwei=gas_price_gwei,
            hour_of_day=hour_of_day,
            is_polygon=is_polygon,
            hop_count=hop_count,
        )

        training_data.append((features, actual_slippage_bps))

    slippages = [s for _, s in training_data]

    log.info(
        "bootstrap.slippage_data_generated",
        total=len(training_data),
        avg_slippage=float(np.mean(slippages)) if slippages else 0.0,
    )

    return training_data


def bootstrap_route_success_predictor(num_samples: int | None = None) -> None:
    """Bootstrap RouteSuccessPredictor with synthetic data.

    Args:
        num_samples: Number of synthetic executions (uses config default if None)
    """
    log.info("bootstrap.route_predictor_starting")

    # Generate synthetic history
    history = generate_synthetic_execution_history(num_samples)

    # Create predictor and train
    ai_config = AdvancedAIConfig()
    decider = AdvancedAIDecider(ai_config)

    # Train model
    decider.route_predictor.train_model(history)

    # Save model
    decider.route_predictor.save_model()

    log.info(
        "bootstrap.route_predictor_completed",
        model_path=str(decider.route_predictor.model_path),
        is_trained=decider.route_predictor.is_trained,
    )


def bootstrap_profit_maximizer(num_samples: int | None = None) -> None:
    """Bootstrap FlashLoanProfitPredictor with synthetic data.

    Args:
        num_samples: Number of synthetic executions (uses config default if None)
    """
    log.info("bootstrap.profit_maximizer_starting")

    # Generate synthetic history with higher success rate for profit maximizer
    history = generate_synthetic_execution_history(num_samples, success_rate=0.75)

    # Create predictor and train
    pm_config = ProfitMaximizerConfig()
    predictor = FlashLoanProfitPredictor(pm_config)

    # Train model
    predictor.train_model(history)

    # Save model
    predictor.save_model()

    log.info(
        "bootstrap.profit_maximizer_completed",
        model_path=str(pm_config.model_path),
        is_trained=predictor.is_trained,
    )


def bootstrap_slippage_predictor(num_samples: int | None = None) -> None:
    """Bootstrap SlippagePredictor with synthetic data.

    Args:
        num_samples: Number of synthetic slippage samples (uses config default if None)
    """
    log.info("bootstrap.slippage_predictor_starting")

    # Generate synthetic training data
    training_data = generate_synthetic_slippage_data(num_samples)

    # Create predictor and train
    predictor = SlippagePredictor()
    predictor.train(training_data, n_rounds=config.xgb_rounds)

    log.info(
        "bootstrap.slippage_predictor_completed",
        model_path=str(predictor.model_path),
    )


def main() -> None:
    """Bootstrap all ML models with synthetic data.

    Configuration can be overridden via environment variables:
        BOOTSTRAP_NUM_SAMPLES=200
        BOOTSTRAP_SUCCESS_RATE=0.75
        BOOTSTRAP_SLIPPAGE_SAMPLES=100
    """
    log.info(
        "bootstrap.starting_all_models",
        num_samples=config.num_samples,
        success_rate=config.success_rate,
        slippage_samples=config.slippage_samples,
    )

    # Ensure model directories exist
    config.model_dir.mkdir(exist_ok=True, parents=True)
    config.data_dir.mkdir(exist_ok=True, parents=True)

    # Bootstrap each model with error handling
    try:
        bootstrap_route_success_predictor()
    except Exception:
        log.exception("bootstrap.route_predictor_failed")

    try:
        bootstrap_profit_maximizer()
    except Exception:
        log.exception("bootstrap.profit_maximizer_failed")

    try:
        bootstrap_slippage_predictor()
    except Exception:
        log.exception("bootstrap.slippage_predictor_failed")

    log.info("bootstrap.completed_all_models")

    # Print summary
    print("\n" + "=" * 60)
    print("ML Model Bootstrap Complete")
    print("=" * 60)
    print("\nConfiguration:")
    print(f"  Samples: {config.num_samples}")
    print(f"  Success Rate: {config.success_rate:.1%}")
    print(f"  Slippage Samples: {config.slippage_samples}")
    print("\nBootstrapped models:")
    print(f"  1. RouteSuccessPredictor ({config.model_dir}/route_success_model.pkl)")
    print(f"  2. FlashLoanProfitPredictor ({config.model_dir}/profit_maximizer.pkl)")
    print(f"  3. SlippagePredictor ({config.model_dir}/slippage_xgb.json)")
    print("\nThese models are initialized with synthetic data.")
    print("They will improve as real execution data is collected.")
    print("\nNext steps:")
    print("  - Start live trading to collect real execution data")
    print("  - Models will retrain automatically every 25-50 executions")
    print("  - Monitor model accuracy in dashboard metrics")
    print("\nEnvironment variable overrides:")
    print("  BOOTSTRAP_NUM_SAMPLES=200")
    print("  BOOTSTRAP_SUCCESS_RATE=0.75")
    print("  BOOTSTRAP_SLIPPAGE_SAMPLES=100")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
