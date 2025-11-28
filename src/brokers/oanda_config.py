"""OANDA v20 REST API configuration.

OANDA-specific configuration for forex trading integration.
Follows the same patterns as existing broker configs (Alpaca, Kraken).
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OandaEnvironment(StrEnum):
    """OANDA API environments."""

    PRACTICE = "practice"  # Demo/paper trading
    LIVE = "live"  # Real money trading


# OANDA API base URLs by environment
OANDA_BASE_URLS = {
    OandaEnvironment.PRACTICE: "https://api-fxpractice.oanda.com",
    OandaEnvironment.LIVE: "https://api-fxtrade.oanda.com",
}

# OANDA streaming endpoints (separate from REST)
OANDA_STREAM_URLS = {
    OandaEnvironment.PRACTICE: "https://stream-fxpractice.oanda.com",
    OandaEnvironment.LIVE: "https://stream-fxtrade.oanda.com",
}


class OandaConfig(BaseSettings):
    """Typed configuration for OANDA connectivity.

    OANDA quirks handled:
    - Bearer token authentication (no expiration but rotatable)
    - Account ID required for most endpoints
    - Separate streaming and REST base URLs
    - Decimal precision varies by instrument (stored as strings in API)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Authentication
    oanda_token: SecretStr = Field(
        alias="OANDA_API_TOKEN",
        description="OANDA v20 API Bearer token",
    )
    oanda_account_id: str = Field(
        alias="OANDA_ACCOUNT_ID",
        description="OANDA account ID (e.g., '001-001-1234567-001')",
    )

    # Environment selection
    oanda_environment: OandaEnvironment = Field(
        default=OandaEnvironment.PRACTICE,
        alias="OANDA_ENVIRONMENT",
        description="'practice' for demo, 'live' for real trading",
    )

    # Rate limiting (OANDA doesn't publish explicit limits; use adaptive approach)
    max_requests_per_second: int = Field(
        default=100,
        description="Conservative rate limit (actual limit may be higher)",
    )

    # Streaming configuration
    streaming_heartbeat_interval: int = Field(
        default=5,
        description="Heartbeat interval in seconds for streaming connection",
    )
    streaming_reconnect_delay: float = Field(
        default=1.0,
        description="Initial delay before reconnecting stream (seconds)",
    )
    streaming_max_reconnect_delay: float = Field(
        default=60.0,
        description="Maximum delay between reconnect attempts (seconds)",
    )

    # Market data configuration
    candle_alignment: Literal["first", "last"] = Field(
        default="last",
        description="Candle alignment for daily candles (OANDA uses 17:00 ET)",
    )
    max_candles_per_request: int = Field(
        default=5000,
        description="Maximum candles returned per request (OANDA limit)",
    )

    # Connection pooling
    max_keepalive_connections: int = Field(
        default=10,
        description="Max HTTP/2 keepalive connections",
    )
    max_connections: int = Field(
        default=20,
        description="Max total HTTP connections",
    )
    connection_timeout: float = Field(
        default=30.0,
        description="HTTP connection timeout (seconds)",
    )

    @field_validator("oanda_account_id")
    @classmethod
    def validate_account_id(cls, v: str) -> str:
        """Validate OANDA account ID format."""
        if not v:
            msg = "OANDA account ID cannot be empty"
            raise ValueError(msg)
        # OANDA account IDs typically follow pattern: XXX-XXX-XXXXXXX-XXX
        if "-" not in v:
            msg = f"Invalid OANDA account ID format: {v}"
            raise ValueError(msg)
        return v

    @field_validator("oanda_environment", mode="before")
    @classmethod
    def validate_environment(cls, v: str | OandaEnvironment) -> OandaEnvironment:
        """Validate and convert environment string."""
        if isinstance(v, OandaEnvironment):
            return v
        v_lower = str(v).lower()
        if v_lower not in ("practice", "live"):
            msg = f"Invalid environment: {v}. Must be 'practice' or 'live'"
            raise ValueError(msg)
        return OandaEnvironment(v_lower)

    @classmethod
    def from_env(cls) -> OandaConfig:
        """Load configuration from environment variables.

        Returns:
            OandaConfig instance

        Raises:
            ValueError: If required credentials are missing
        """
        return cls()

    def get_base_url(self) -> str:
        """Get REST API base URL for current environment."""
        return OANDA_BASE_URLS[self.oanda_environment]

    def get_stream_url(self) -> str:
        """Get streaming API base URL for current environment."""
        return OANDA_STREAM_URLS[self.oanda_environment]

    def is_live(self) -> bool:
        """Check if using live trading environment."""
        return self.oanda_environment == OandaEnvironment.LIVE


# Instrument-specific metadata for decimal precision
# OANDA returns prices with varying decimal places
INSTRUMENT_PRECISION: dict[str, int] = {
    # JPY pairs (3 decimals)
    "USD_JPY": 3,
    "EUR_JPY": 3,
    "GBP_JPY": 3,
    "AUD_JPY": 3,
    "CAD_JPY": 3,
    "CHF_JPY": 3,
    "NZD_JPY": 3,
    # Most other pairs (5 decimals)
    "EUR_USD": 5,
    "GBP_USD": 5,
    "AUD_USD": 5,
    "NZD_USD": 5,
    "USD_CAD": 5,
    "USD_CHF": 5,
    # Cross pairs (5 decimals)
    "EUR_GBP": 5,
    "EUR_AUD": 5,
    "GBP_AUD": 5,
    # Metals (2-3 decimals)
    "XAU_USD": 2,  # Gold
    "XAG_USD": 3,  # Silver
}


def get_instrument_precision(instrument: str) -> int:
    """Get decimal precision for OANDA instrument.

    Args:
        instrument: OANDA instrument name (e.g., "EUR_USD")

    Returns:
        Number of decimal places for price precision
    """
    return INSTRUMENT_PRECISION.get(instrument, 5)  # Default to 5 decimals


def normalize_instrument_name(symbol: str) -> str:
    """Convert standard symbol to OANDA instrument format.

    Args:
        symbol: Standard format (e.g., "EUR/USD", "EURUSD")

    Returns:
        OANDA format (e.g., "EUR_USD")

    Examples:
        >>> normalize_instrument_name("EUR/USD")
        'EUR_USD'
        >>> normalize_instrument_name("EURUSD")
        'EUR_USD'
        >>> normalize_instrument_name("EUR_USD")
        'EUR_USD'
    """
    # Remove slashes and spaces
    clean = symbol.replace("/", "").replace(" ", "").upper()

    # If already in OANDA format, return as-is
    if "_" in clean:
        return clean

    # Standard forex pairs are 6 characters (XXXYYY)
    if len(clean) == 6:
        return f"{clean[:3]}_{clean[3:]}"

    # For metals and other instruments, attempt smart detection
    # XAU = Gold, XAG = Silver, etc.
    if clean.startswith("XAU"):
        return "XAU_USD" if "USD" in clean else clean
    if clean.startswith("XAG"):
        return "XAG_USD" if "USD" in clean else clean

    # Fallback: return as-is
    return clean


def denormalize_instrument_name(instrument: str) -> str:
    """Convert OANDA instrument format to standard symbol.

    Args:
        instrument: OANDA format (e.g., "EUR_USD")

    Returns:
        Standard format (e.g., "EUR/USD")

    Examples:
        >>> denormalize_instrument_name("EUR_USD")
        'EUR/USD'
    """
    return instrument.replace("_", "/")
