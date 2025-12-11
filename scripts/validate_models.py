"""ML Model Validation Script

Validates all ML models against recent trading data:
- Route success predictor
- Profit maximizer
- Slippage predictor

Metrics calculated:
- Accuracy, Precision, Recall, F1
- Mean Absolute Error (MAE)
- Root Mean Squared Error (RMSE)
- Prediction correlation
- Feature importance analysis

Usage:
    python scripts/validate_models.py --days 7 --save-report
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pickle
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg
import numpy as np
import polars as pl
import structlog
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    recall_score,
)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

log = structlog.get_logger()


class ModelValidator:
    """Validates ML models against real trading data."""

    def __init__(self, db_url: str, models_dir: Path):
        """Initialize validator.

        Args:
            db_url: PostgreSQL connection URL
            models_dir: Directory containing trained models
        """
        self.db_url = db_url
        self.models_dir = models_dir
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Connect to database."""
        self.pool = await asyncpg.create_pool(
            self.db_url,
            min_size=2,
            max_size=5,
            command_timeout=60,
        )
        log.info("validator.connected")

    async def close(self) -> None:
        """Close database connection."""
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def load_validation_data(self, days: int = 7) -> pl.DataFrame:
        """Load recent executed opportunities for validation.

        Args:
            days: Number of days to look back

        Returns:
            Polars DataFrame with validation data
        """
        if not self.pool:
            raise RuntimeError("Not connected to database")

        query = """
        SELECT
            symbol,
            chain,
            edge_bps,
            pool_liquidity_quote,
            gas_price_gwei,
            hour_of_day,
            estimated_slippage_bps,
            actual_slippage_bps,
            profitable,
            profit_quote,
            gas_cost_eth,
            hop_count,
            execution_path,
            timestamp
        FROM arbitrage_opportunities
        WHERE executed = TRUE
          AND timestamp > NOW() - $1::INTERVAL
        ORDER BY timestamp DESC
        """

        rows = await self.pool.fetch(query, f"{days} days")

        if not rows:
            log.warning("validator.no_data", days=days)
            return pl.DataFrame()

        # Convert to Polars DataFrame
        data = [dict(row) for row in rows]
        df = pl.DataFrame(data)

        log.info("validator.data_loaded", rows=len(df), days=days)

        return df

    def load_model(self, model_name: str) -> Any:
        """Load a trained model from disk.

        Args:
            model_name: Name of model file (e.g., 'route_success_model.pkl')

        Returns:
            Loaded model object
        """
        model_path = self.models_dir / model_name

        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        with open(model_path, "rb") as f:
            model = pickle.load(f)

        log.info("validator.model_loaded", model=model_name)

        return model

    def validate_route_success_model(self, df: pl.DataFrame) -> dict[str, float]:
        """Validate route success prediction model.

        Args:
            df: Validation dataset

        Returns:
            Dict of validation metrics
        """
        try:
            model = self.load_model("route_success_model.pkl")
        except FileNotFoundError:
            log.warning("validator.model_not_found", model="route_success_model.pkl")
            return {}

        # Prepare features
        features = df.select(
            [
                "edge_bps",
                "pool_liquidity_quote",
                "gas_price_gwei",
                "hour_of_day",
                "hop_count",
            ]
        ).to_numpy()

        # Target: profitable trades
        y_true = df["profitable"].to_numpy().astype(int)

        # Predict
        y_pred = model.predict(features)
        y_pred_proba = model.predict_proba(features)[:, 1]  # Probability of success

        # Calculate metrics
        metrics = {
            "accuracy": accuracy_score(y_true, y_pred),
            "precision": precision_score(y_true, y_pred, zero_division=0),
            "recall": recall_score(y_true, y_pred, zero_division=0),
            "f1_score": f1_score(y_true, y_pred, zero_division=0),
            "avg_confidence": float(np.mean(y_pred_proba)),
            "samples": len(y_true),
        }

        log.info("validator.route_success_validated", metrics=metrics)

        return metrics

    def validate_profit_maximizer(self, df: pl.DataFrame) -> dict[str, float]:
        """Validate profit maximizer model.

        Args:
            df: Validation dataset

        Returns:
            Dict of validation metrics
        """
        try:
            model = self.load_model("profit_maximizer.pkl")
        except FileNotFoundError:
            log.warning("validator.model_not_found", model="profit_maximizer.pkl")
            return {}

        # Filter to profitable trades only
        df_profitable = df.filter(pl.col("profitable") == True)

        if len(df_profitable) == 0:
            log.warning("validator.no_profitable_trades")
            return {}

        # Prepare features
        features = df_profitable.select(
            [
                "edge_bps",
                "pool_liquidity_quote",
                "gas_price_gwei",
                "hour_of_day",
            ]
        ).to_numpy()

        # Target: actual profit
        y_true = df_profitable["profit_quote"].to_numpy()

        # Predict
        y_pred = model.predict(features)

        # Calculate metrics
        mae = mean_absolute_error(y_true, y_pred)
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        correlation = np.corrcoef(y_true, y_pred)[0, 1]

        # Calculate percentage error
        pct_errors = np.abs((y_true - y_pred) / y_true) * 100
        mean_pct_error = np.mean(pct_errors)

        metrics = {
            "mae": float(mae),
            "rmse": float(rmse),
            "correlation": float(correlation),
            "mean_pct_error": float(mean_pct_error),
            "samples": len(y_true),
        }

        log.info("validator.profit_maximizer_validated", metrics=metrics)

        return metrics

    def validate_slippage_predictor(self, df: pl.DataFrame) -> dict[str, float]:
        """Validate slippage predictor model.

        Args:
            df: Validation dataset

        Returns:
            Dict of validation metrics
        """
        # Check if slippage predictor model exists
        slippage_model_path = self.models_dir / "slippage_predictor.pkl"

        if not slippage_model_path.exists():
            log.warning("validator.model_not_found", model="slippage_predictor.pkl")
            return {}

        try:
            model = self.load_model("slippage_predictor.pkl")
        except Exception as e:
            log.warning("validator.load_failed", model="slippage_predictor.pkl", error=str(e))
            return {}

        # Prepare features
        features = df.select(
            [
                "edge_bps",
                "pool_liquidity_quote",
                "gas_price_gwei",
            ]
        ).to_numpy()

        # Target: actual slippage
        y_true = df["actual_slippage_bps"].to_numpy()

        # Predict
        y_pred = model.predict(features)

        # Calculate metrics
        mae = mean_absolute_error(y_true, y_pred)
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        correlation = np.corrcoef(y_true, y_pred)[0, 1]

        metrics = {
            "mae_bps": float(mae),
            "rmse_bps": float(rmse),
            "correlation": float(correlation),
            "samples": len(y_true),
        }

        log.info("validator.slippage_predictor_validated", metrics=metrics)

        return metrics

    async def save_validation_results(
        self,
        route_metrics: dict,
        profit_metrics: dict,
        slippage_metrics: dict,
    ) -> None:
        """Save validation results to database.

        Args:
            route_metrics: Route success model metrics
            profit_metrics: Profit maximizer metrics
            slippage_metrics: Slippage predictor metrics
        """
        if not self.pool:
            return

        timestamp = datetime.utcnow()

        # Save route success model metrics
        if route_metrics:
            await self.pool.execute(
                """
                INSERT INTO model_performance (
                    timestamp, model_name, model_version,
                    accuracy, precision_score, recall, f1_score,
                    num_predictions, num_executions
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                timestamp,
                "route_success_predictor",
                datetime.now().strftime("%Y%m%d_%H%M%S"),
                route_metrics.get("accuracy"),
                route_metrics.get("precision"),
                route_metrics.get("recall"),
                route_metrics.get("f1_score"),
                route_metrics.get("samples", 0),
                route_metrics.get("samples", 0),
            )

        # Save profit maximizer metrics
        if profit_metrics:
            await self.pool.execute(
                """
                INSERT INTO model_performance (
                    timestamp, model_name, model_version,
                    avg_predicted_profit, avg_actual_profit,
                    prediction_error_pct,
                    num_predictions, num_executions
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                timestamp,
                "profit_maximizer",
                datetime.now().strftime("%Y%m%d_%H%M%S"),
                None,  # Would need to calculate from predictions
                None,
                profit_metrics.get("mean_pct_error"),
                profit_metrics.get("samples", 0),
                profit_metrics.get("samples", 0),
            )

        log.info("validator.results_saved")

    def generate_report(
        self,
        route_metrics: dict,
        profit_metrics: dict,
        slippage_metrics: dict,
    ) -> str:
        """Generate validation report.

        Args:
            route_metrics: Route success model metrics
            profit_metrics: Profit maximizer metrics
            slippage_metrics: Slippage predictor metrics

        Returns:
            Formatted report string
        """
        report = []
        report.append("=" * 80)
        report.append("ML MODEL VALIDATION REPORT")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 80)
        report.append("")

        # Route Success Model
        report.append("Route Success Predictor")
        report.append("-" * 40)
        if route_metrics:
            report.append(f"  Accuracy:  {route_metrics['accuracy']:.3f}")
            report.append(f"  Precision: {route_metrics['precision']:.3f}")
            report.append(f"  Recall:    {route_metrics['recall']:.3f}")
            report.append(f"  F1 Score:  {route_metrics['f1_score']:.3f}")
            report.append(f"  Samples:   {route_metrics['samples']}")
        else:
            report.append("  Model not found or no data")
        report.append("")

        # Profit Maximizer
        report.append("Profit Maximizer")
        report.append("-" * 40)
        if profit_metrics:
            report.append(f"  MAE:              ${profit_metrics['mae']:.2f}")
            report.append(f"  RMSE:             ${profit_metrics['rmse']:.2f}")
            report.append(f"  Correlation:      {profit_metrics['correlation']:.3f}")
            report.append(f"  Mean % Error:     {profit_metrics['mean_pct_error']:.1f}%")
            report.append(f"  Samples:          {profit_metrics['samples']}")
        else:
            report.append("  Model not found or no data")
        report.append("")

        # Slippage Predictor
        report.append("Slippage Predictor")
        report.append("-" * 40)
        if slippage_metrics:
            report.append(f"  MAE:         {slippage_metrics['mae_bps']:.2f} bps")
            report.append(f"  RMSE:        {slippage_metrics['rmse_bps']:.2f} bps")
            report.append(f"  Correlation: {slippage_metrics['correlation']:.3f}")
            report.append(f"  Samples:     {slippage_metrics['samples']}")
        else:
            report.append("  Model not found or no data")
        report.append("")

        report.append("=" * 80)

        return "\n".join(report)


async def main():
    """Main validation function."""
    parser = argparse.ArgumentParser(description="Validate ML models")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days of data to validate against (default: 7)",
    )
    parser.add_argument(
        "--save-report",
        action="store_true",
        help="Save report to file",
    )
    parser.add_argument(
        "--save-db",
        action="store_true",
        help="Save results to database",
    )

    args = parser.parse_args()

    # Setup logging
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )

    # Build database URL
    host = os.getenv("TIMESCALE_HOST", "localhost")
    port = os.getenv("TIMESCALE_PORT", "5433")
    user = os.getenv("TIMESCALE_USER", "trading_user")
    password = os.getenv("TIMESCALE_PASSWORD", "trading_pass_change_in_production")
    database = os.getenv("TIMESCALE_DB", "trading_db")

    db_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"

    # Models directory
    models_dir = Path(__file__).parent.parent / "models"

    # Create validator
    validator = ModelValidator(db_url, models_dir)

    try:
        # Connect
        await validator.connect()

        # Load validation data
        df = await validator.load_validation_data(days=args.days)

        if len(df) == 0:
            print("❌ No validation data found. Run the system in dry-run mode to collect data.")
            return

        # Validate models
        route_metrics = validator.validate_route_success_model(df)
        profit_metrics = validator.validate_profit_maximizer(df)
        slippage_metrics = validator.validate_slippage_predictor(df)

        # Generate report
        report = validator.generate_report(route_metrics, profit_metrics, slippage_metrics)
        print(report)

        # Save to file if requested
        if args.save_report:
            report_path = Path(__file__).parent.parent / "logs" / "model_validation.txt"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with open(report_path, "w") as f:
                f.write(report)
            print(f"\n✅ Report saved to: {report_path}")

        # Save to database if requested
        if args.save_db:
            await validator.save_validation_results(
                route_metrics, profit_metrics, slippage_metrics
            )
            print("✅ Results saved to database")

    finally:
        await validator.close()


if __name__ == "__main__":
    asyncio.run(main())
