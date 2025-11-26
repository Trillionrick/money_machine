"""Feature engineering for ML models.

The AI layer needs features that capture:
1. Asymmetric payoff opportunities (convexity)
2. Regime information (volatility, trend)
3. Market microstructure (liquidity, spreads)
4. Sentiment/momentum signals
"""

import polars as pl


class FeatureEngine:
    """Generate ML features from raw market data.

    Philosophy: Features should capture ASYMMETRY and CONVEXITY,
    not just "is price going up?"

    Example:
        >>> engine = FeatureEngine()
        >>> features = engine.transform(ohlcv_data)
    """

    def transform(self, df: pl.DataFrame) -> pl.DataFrame:
        """Transform OHLCV data into ML features.

        Args:
            df: DataFrame with columns [timestamp, open, high, low, close, volume]

        Returns:
            DataFrame with original columns + engineered features
        """
        # Start with copy
        result = df.clone()

        # Returns and volatility
        result = result.with_columns([
            # Returns (multiple horizons)
            (pl.col("close").pct_change().alias("return_1")),
            (pl.col("close").pct_change(5).alias("return_5")),
            (pl.col("close").pct_change(20).alias("return_20")),

            # Volatility (rolling std of returns)
            (
                pl.col("close")
                .pct_change()
                .rolling_std(window_size=20)
                .alias("volatility_20")
            ),

            # Volume features
            (pl.col("volume").pct_change().alias("volume_change")),
            (
                (pl.col("volume") / pl.col("volume").rolling_mean(window_size=20))
                .alias("volume_ratio")
            ),
        ])

        # Momentum features (convexity indicators)
        result = result.with_columns([
            # Momentum: recent > long-term?
            (
                (pl.col("close").rolling_mean(window_size=5)
                 / pl.col("close").rolling_mean(window_size=20))
                .alias("momentum_5_20")
            ),

            # Acceleration: momentum changing?
            (
                pl.col("close")
                .pct_change()
                .rolling_mean(window_size=5)
                .alias("acceleration")
            ),
        ])

        # Asymmetry features (what we really care about)
        result = result.with_columns([
            # Upside vs downside: asymmetric?
            (
                (pl.col("high") - pl.col("open"))
                / (pl.col("open") - pl.col("low") + 1e-8)
            ).alias("upside_downside_ratio"),

            # Skewness of recent returns (positive skew = convex)
            (
                pl.col("close")
                .pct_change()
                .rolling_apply(
                    lambda s: float(s.skew()) if len(s) > 3 else 0.0,
                    window_size=20,
                )
                .alias("return_skewness")
            ),

            # Tail ratio: big moves vs typical moves
            (
                pl.col("close")
                .pct_change()
                .abs()
                .rolling_quantile(0.95, window_size=20)
                / (pl.col("close").pct_change().abs().rolling_mean(window_size=20) + 1e-8)
            ).alias("tail_ratio"),
        ])

        # Regime features
        result = result.with_columns([
            # Volatility regime (expanding vol = opportunity)
            (
                pl.col("volatility_20")
                / pl.col("volatility_20").rolling_mean(window_size=60)
            ).alias("vol_regime"),

            # Trend strength
            (
                (pl.col("close") - pl.col("close").rolling_min(window_size=20))
                / (
                    pl.col("close").rolling_max(window_size=20)
                    - pl.col("close").rolling_min(window_size=20)
                    + 1e-8
                )
            ).alias("trend_strength"),
        ])

        # Convexity score (composite feature)
        result = result.with_columns([
            # High convexity = high vol + positive skew + momentum
            (
                pl.col("volatility_20").fill_null(0)
                * pl.col("return_skewness").fill_null(0).clip(-3, 3)
                * pl.col("momentum_5_20").fill_null(1)
            ).alias("convexity_score"),
        ])

        return result

    def select_features(self, df: pl.DataFrame) -> list[str]:
        """Return list of feature column names.

        Args:
            df: DataFrame with features

        Returns:
            List of feature column names (excludes OHLCV)
        """
        exclude = {"timestamp", "open", "high", "low", "close", "volume"}
        return [col for col in df.columns if col not in exclude]


class ConvexityScanner:
    """Scan markets for high-convexity opportunities.

    This is the "AI" that finds asymmetric payoffs.
    """

    def __init__(self, min_convexity_score: float = 0.1) -> None:
        """Initialize scanner.

        Args:
            min_convexity_score: Minimum score to flag opportunity
        """
        self.min_convexity_score = min_convexity_score
        self.feature_engine = FeatureEngine()

    def scan(
        self,
        market_data: dict[str, pl.DataFrame],
    ) -> list[dict]:
        """Scan multiple symbols for convexity opportunities.

        Args:
            market_data: Dict of symbol -> OHLCV DataFrame

        Returns:
            List of opportunities, sorted by convexity score
        """
        opportunities = []

        for symbol, df in market_data.items():
            # Generate features
            df_features = self.feature_engine.transform(df)

            # Get most recent row
            if len(df_features) == 0:
                continue

            latest = df_features.tail(1)

            convexity_score = latest["convexity_score"][0]

            if convexity_score is None or convexity_score < self.min_convexity_score:
                continue

            # Extract key metrics
            opportunity = {
                "symbol": symbol,
                "convexity_score": float(convexity_score),
                "volatility": float(latest["volatility_20"][0] or 0),
                "momentum": float(latest["momentum_5_20"][0] or 0),
                "skewness": float(latest["return_skewness"][0] or 0),
                "vol_regime": float(latest["vol_regime"][0] or 0),
                "price": float(latest["close"][0]),
            }

            opportunities.append(opportunity)

        # Sort by convexity score (highest first)
        opportunities.sort(key=lambda x: x["convexity_score"], reverse=True)

        return opportunities
