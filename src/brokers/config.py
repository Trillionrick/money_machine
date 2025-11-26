"""Configuration management for broker connections.

Loads from environment variables (.env file).
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env file
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


@dataclass
class AlpacaConfig:
    """Alpaca configuration."""

    api_key: str
    api_secret: str
    paper: bool = True

    @classmethod
    def from_env(cls) -> "AlpacaConfig":
        """Load from environment variables."""
        api_key = os.getenv("ALPACA_API_KEY", "")
        api_secret = os.getenv("ALPACA_API_SECRET", "")
        paper = os.getenv("ALPACA_PAPER", "true").lower() == "true"

        if not api_key or not api_secret:
            msg = (
                "Alpaca credentials not found. "
                "Set ALPACA_API_KEY and ALPACA_API_SECRET in .env"
            )
            raise ValueError(msg)

        return cls(api_key=api_key, api_secret=api_secret, paper=paper)


@dataclass
class BinanceConfig:
    """Binance configuration."""

    api_key: str
    api_secret: str
    testnet: bool = True

    @classmethod
    def from_env(cls) -> "BinanceConfig":
        """Load from environment variables."""
        api_key = os.getenv("BINANCE_API_KEY", "")
        api_secret = os.getenv("BINANCE_API_SECRET", "")
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

        if not api_key or not api_secret:
            msg = (
                "Binance credentials not found. "
                "Set BINANCE_API_KEY and BINANCE_API_SECRET in .env"
            )
            raise ValueError(msg)

        return cls(api_key=api_key, api_secret=api_secret, testnet=testnet)


@dataclass
class TradingConfig:
    """Trading system configuration."""

    trading_mode: str = "paper"
    target_wealth: float = 500_000.0
    starting_capital: float = 5_000.0
    time_horizon_days: int = 365

    max_position_pct: float = 0.30
    max_leverage: float = 2.0
    max_daily_loss_pct: float = 0.10
    max_drawdown_pct: float = 0.50

    kelly_fraction: float = 0.50
    min_convexity_score: float = 0.10
    max_concurrent_positions: int = 3

    enable_circuit_breakers: bool = True
    validate_orders: bool = True
    dry_run: bool = False

    @classmethod
    def from_env(cls) -> "TradingConfig":
        """Load from environment variables."""
        return cls(
            trading_mode=os.getenv("TRADING_MODE", "paper"),
            target_wealth=float(os.getenv("TARGET_WEALTH", "500000")),
            starting_capital=float(os.getenv("STARTING_CAPITAL", "5000")),
            time_horizon_days=int(os.getenv("TIME_HORIZON_DAYS", "365")),
            max_position_pct=float(os.getenv("MAX_POSITION_PCT", "0.30")),
            max_leverage=float(os.getenv("MAX_LEVERAGE", "2.0")),
            max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", "0.10")),
            max_drawdown_pct=float(os.getenv("MAX_DRAWDOWN_PCT", "0.50")),
            kelly_fraction=float(os.getenv("KELLY_FRACTION", "0.50")),
            min_convexity_score=float(os.getenv("MIN_CONVEXITY_SCORE", "0.10")),
            max_concurrent_positions=int(os.getenv("MAX_CONCURRENT_POSITIONS", "3")),
            enable_circuit_breakers=os.getenv("ENABLE_CIRCUIT_BREAKERS", "true").lower() == "true",
            validate_orders=os.getenv("VALIDATE_ORDERS", "true").lower() == "true",
            dry_run=os.getenv("DRY_RUN", "false").lower() == "true",
        )
