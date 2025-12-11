"""Machine learning layer for pattern discovery and signal generation.

This module implements ML-powered trading policies optimized for aggressive
target-hitting strategies (opposite of Kelly criterion). Key components:

- FeatureEngine: Transform OHLCV data into convexity/asymmetry features
- ConvexityScanner: Scan markets for high-convexity opportunities
- AggressiveMLPolicy: ML-powered policy sized for wealth targets
- AdaptiveAggressivePolicy: Adaptive version that adjusts aggression based on progress

Philosophy: Find asymmetric opportunities, size aggressively for targets,
accept high variance as the cost of attempting rapid wealth generation.
"""

from src.ml.aggressive_policy import (
    AdaptiveAggressivePolicy,
    AggressiveMLPolicy,
)
from src.ml.feature_engine import (
    ConvexityScanner,
    FeatureEngine,
)

__all__ = [
    "FeatureEngine",
    "ConvexityScanner",
    "AggressiveMLPolicy",
    "AdaptiveAggressivePolicy",
]
