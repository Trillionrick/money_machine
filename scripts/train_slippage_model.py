#!/usr/bin/env python3
"""Train slippage prediction model from historical arbitrage data.

Usage:
    python scripts/train_slippage_model.py
    python scripts/train_slippage_model.py --days 60 --min-samples 100
"""

import argparse
import asyncio
from datetime import datetime

import structlog

from src.ai.opportunity_logger import get_opportunity_logger
from src.ai.slippage_predictor import SlippageFeatures, SlippagePredictor

log = structlog.get_logger()


async def train_model(days: int = 30, min_samples: int = 50, n_rounds: int = 100) -> None:
    """Train slippage predictor on historical data."""

    print("=" * 70)
    print("SLIPPAGE PREDICTOR TRAINING")
    print("=" * 70)
    print()

    # Fetch training data from database
    logger = get_opportunity_logger()
    print(f"Fetching training data (last {days} days)...")

    training_data_raw = await logger.get_training_data(days=days, min_samples=min_samples)

    if len(training_data_raw) < min_samples:
        print(f"❌ Insufficient data: {len(training_data_raw)} samples (need {min_samples})")
        print()
        print("Recommendation:")
        print("  1. Run your arbitrage system for at least 1 week")
        print("  2. Execute at least 50 trades")
        print("  3. Ensure actual_slippage_bps is recorded")
        return

    print(f"✅ Found {len(training_data_raw)} training samples")
    print()

    # Convert to SlippageFeatures format
    training_data = []
    for row in training_data_raw:
        # Skip rows missing critical data
        if row["actual_slippage_bps"] is None:
            continue

        if row["pool_liquidity_quote"] is None or float(row["pool_liquidity_quote"]) <= 0:
            continue

        features = SlippageFeatures(
            trade_size_quote=float(row.get("trade_size_quote") or 5000.0),
            pool_liquidity_quote=float(row["pool_liquidity_quote"]),
            price_volatility_1h=2.5,  # TODO: Calculate from candles data
            gas_price_gwei=float(row["gas_price_gwei"]),
            hour_of_day=int(row["hour_of_day"]),
            is_polygon=(row["chain"] == "polygon"),
            hop_count=int(row.get("hop_count") or 2),
        )

        actual_slippage = float(row["actual_slippage_bps"])
        training_data.append((features, actual_slippage))

    if len(training_data) < min_samples:
        print(f"❌ After filtering: {len(training_data)} samples (need {min_samples})")
        return

    print(f"Training on {len(training_data)} samples...")
    print(f"  XGBoost rounds: {n_rounds}")
    print()

    # Train model
    predictor = SlippagePredictor()
    predictor.train(training_data, n_rounds=n_rounds)

    print()
    print("✅ Model trained successfully!")
    print(f"   Saved to: {predictor.model_path}")
    print()

    # Validate on recent samples
    print("Validation on last 10 samples:")
    print("-" * 70)
    print(f"{'Predicted':>10} {'Actual':>10} {'Error':>10} {'Symbol':>10}")
    print("-" * 70)

    validation_samples = training_data[-10:]
    errors = []

    for features, actual in validation_samples:
        predicted = predictor.predict_slippage_bps(features)
        error = abs(predicted - actual)
        errors.append(error)

        print(f"{predicted:>10.2f} {actual:>10.2f} {error:>10.2f}")

    avg_error = sum(errors) / len(errors) if errors else 0
    print("-" * 70)
    print(f"Mean Absolute Error: {avg_error:.2f} bps")
    print()

    # Log metrics to database
    # TODO: Implement ml_model_metrics insertion

    print("Next steps:")
    print("  1. Update FlashArbitrageRunner to load this model")
    print("  2. Monitor predicted vs actual slippage in production")
    print("  3. Retrain weekly with new data")
    print()


def main():
    parser = argparse.ArgumentParser(description="Train slippage prediction model")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days of historical data to use (default: 30)",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=50,
        help="Minimum number of samples required for training (default: 50)",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=100,
        help="Number of XGBoost training rounds (default: 100)",
    )

    args = parser.parse_args()

    asyncio.run(train_model(days=args.days, min_samples=args.min_samples, n_rounds=args.rounds))


if __name__ == "__main__":
    main()
