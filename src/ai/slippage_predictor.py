"""XGBoost-based slippage prediction for arbitrage execution.

Predicts actual slippage based on:
- Trade size vs pool liquidity
- Recent volatility
- Gas price (congestion proxy)
- Time of day
- Chain (Ethereum vs Polygon)

Trains on historical execution data from oanda_transactions table.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import joblib
import numpy as np
import structlog

if TYPE_CHECKING:
    import xgboost as xgb

log = structlog.get_logger()


@dataclass
class SlippageFeatures:
    """Input features for slippage prediction."""

    trade_size_quote: float  # Trade size in USDC/USDT
    pool_liquidity_quote: float  # Total pool liquidity
    price_volatility_1h: float  # 1-hour price volatility (%)
    gas_price_gwei: float  # Current gas price
    hour_of_day: int  # 0-23 (captures market activity patterns)
    is_polygon: bool  # Chain indicator
    hop_count: int  # Number of hops in route


class SlippagePredictor:
    """Predicts slippage for arbitrage trades using XGBoost."""

    def __init__(self, model_path: Path | None = None):
        self.model: xgb.Booster | None = None
        self.model_path = model_path or Path("models/slippage_xgb.json")

        if self.model_path.exists():
            self.load_model()
            log.info("slippage_predictor.loaded", path=str(self.model_path))

    def load_model(self) -> None:
        """Load trained XGBoost model."""
        import xgboost as xgb

        self.model = xgb.Booster()
        self.model.load_model(str(self.model_path))

    def save_model(self) -> None:
        """Save trained model to disk."""
        if self.model is None:
            raise ValueError("No model to save")

        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        self.model.save_model(str(self.model_path))
        log.info("slippage_predictor.saved", path=str(self.model_path))

    def predict_slippage_bps(self, features: SlippageFeatures) -> float:
        """Predict slippage in basis points.

        Returns:
            Predicted slippage (bps). Higher is worse.
            Returns conservative default if model not trained.
        """
        if self.model is None:
            # Conservative default: 50 bps for large trades
            size_ratio = features.trade_size_quote / max(features.pool_liquidity_quote, 1.0)
            return 50.0 * (1.0 + 10.0 * size_ratio)

        import xgboost as xgb

        # Convert features to numpy array
        X = np.array(
            [
                [
                    features.trade_size_quote,
                    features.pool_liquidity_quote,
                    features.trade_size_quote / max(features.pool_liquidity_quote, 1.0),
                    features.price_volatility_1h,
                    features.gas_price_gwei,
                    features.hour_of_day,
                    float(features.is_polygon),
                    features.hop_count,
                ]
            ]
        )

        dmatrix = xgb.DMatrix(X)
        slippage_bps = self.model.predict(dmatrix)[0]

        return max(0.0, float(slippage_bps))  # Ensure non-negative

    def train(
        self,
        training_data: list[tuple[SlippageFeatures, float]],
        n_rounds: int = 100,
    ) -> None:
        """Train XGBoost model on historical slippage data.

        Args:
            training_data: List of (features, actual_slippage_bps) tuples
            n_rounds: Number of boosting rounds
        """
        import xgboost as xgb

        if len(training_data) < 10:
            log.warning("slippage_predictor.insufficient_data", count=len(training_data))
            return

        # Extract features and labels
        X = []
        y = []
        for features, actual_slippage in training_data:
            X.append(
                [
                    features.trade_size_quote,
                    features.pool_liquidity_quote,
                    features.trade_size_quote / max(features.pool_liquidity_quote, 1.0),
                    features.price_volatility_1h,
                    features.gas_price_gwei,
                    features.hour_of_day,
                    float(features.is_polygon),
                    features.hop_count,
                ]
            )
            y.append(actual_slippage)

        X_array = np.array(X)
        y_array = np.array(y)

        # Train XGBoost
        dtrain = xgb.DMatrix(X_array, label=y_array)
        params = {
            "objective": "reg:squarederror",
            "max_depth": 6,
            "learning_rate": 0.1,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "seed": 42,
        }

        self.model = xgb.train(params, dtrain, num_boost_round=n_rounds)
        log.info("slippage_predictor.trained", samples=len(training_data), rounds=n_rounds)

        self.save_model()


# Example usage:
# predictor = SlippagePredictor()
# features = SlippageFeatures(
#     trade_size_quote=5000.0,
#     pool_liquidity_quote=1_000_000.0,
#     price_volatility_1h=2.5,
#     gas_price_gwei=80.0,
#     hour_of_day=14,
#     is_polygon=False,
#     hop_count=2,
# )
# predicted_slippage = predictor.predict_slippage_bps(features)
# print(f"Predicted slippage: {predicted_slippage:.2f} bps")
