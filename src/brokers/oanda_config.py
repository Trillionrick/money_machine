"""OANDA v20 REST API configuration.

OANDA-specific configuration for forex trading integration.
Follows the same patterns as existing broker configs (Alpaca, Kraken).

Modern implementation (2025):
- Pydantic BaseSettings v2 with SettingsConfigDict
- SecretStr for secure credential storage
- Type-safe optional fields with explicit defaults
- Field validators with proper error messages
- Environment variable integration
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, SecretStr, ValidationError, field_validator
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

    Example .env:
        OANDA_API_TOKEN=your_api_token_here
        OANDA_ACCOUNT_ID=001-001-1234567-001
        OANDA_ENVIRONMENT=practice
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
        validate_default=True,
    )

    # Authentication (optional to allow testing/config loading without credentials)
    oanda_token: Annotated[
        SecretStr | None,
        Field(
            description="OANDA v20 API Bearer token (stored securely)",
            examples=["abc123def456..."],
        ),
    ] = None

    oanda_account_id: Annotated[
        str | None,
        Field(
            description="OANDA account ID in format XXX-XXX-XXXXXXX-XXX",
            examples=["001-001-1234567-001"],
        ),
    ] = None

    # Environment selection
    oanda_environment: Annotated[
        OandaEnvironment,
        Field(
            description="Trading environment: 'practice' for demo, 'live' for real money",
        ),
    ] = OandaEnvironment.PRACTICE

    # Rate limiting (OANDA doesn't publish explicit limits; use adaptive approach)
    max_requests_per_second: Annotated[
        int,
        Field(
            ge=1,
            le=1000,
            description="Conservative rate limit (actual limit may be higher)",
        ),
    ] = 100

    # Streaming configuration
    streaming_heartbeat_interval: Annotated[
        int,
        Field(
            ge=1,
            le=60,
            description="Heartbeat interval in seconds for streaming connection",
        ),
    ] = 5

    streaming_reconnect_delay: Annotated[
        float,
        Field(
            ge=0.1,
            le=60.0,
            description="Initial delay before reconnecting stream (seconds)",
        ),
    ] = 1.0

    streaming_max_reconnect_delay: Annotated[
        float,
        Field(
            ge=1.0,
            le=300.0,
            description="Maximum delay between reconnect attempts (seconds)",
        ),
    ] = 60.0

    # Market data configuration
    candle_alignment: Annotated[
        Literal["first", "last"],
        Field(
            description="Candle alignment for daily candles (OANDA uses 17:00 ET)",
        ),
    ] = "last"

    max_candles_per_request: Annotated[
        int,
        Field(
            ge=1,
            le=5000,
            description="Maximum candles returned per request (OANDA limit)",
        ),
    ] = 5000

    # Connection pooling
    max_keepalive_connections: Annotated[
        int,
        Field(
            ge=1,
            le=100,
            description="Max HTTP/2 keepalive connections",
        ),
    ] = 10

    max_connections: Annotated[
        int,
        Field(
            ge=1,
            le=100,
            description="Max total HTTP connections",
        ),
    ] = 20

    connection_timeout: Annotated[
        float,
        Field(
            ge=1.0,
            le=300.0,
            description="HTTP connection timeout (seconds)",
        ),
    ] = 30.0

    @field_validator("oanda_account_id")
    @classmethod
    def validate_account_id(cls, v: str | None) -> str | None:
        """Validate OANDA account ID format."""
        if v is None:
            return None
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
    
        try:
            # Instantiate using environment variables; static type-checkers may
            # complain about missing __init__ args, so ignore that specific check.
            return cls()  # type: ignore[call-arg]
        except Exception as e:
            msg = (
                f"Failed to load OANDA configuration from environment. "
                f"Ensure OANDA_API_TOKEN and OANDA_ACCOUNT_ID are set. "
                f"Error: {e}"
            )
            raise ValueError(msg) from e

    def get_base_url(self) -> str:
        """Get REST API base URL for current environment."""
        return OANDA_BASE_URLS[self.oanda_environment]

    def get_stream_url(self) -> str:
        """Get streaming API base URL for current environment."""
        return OANDA_STREAM_URLS[self.oanda_environment]

    def is_live(self) -> bool:
        """Check if using live trading environment."""
        return self.oanda_environment == OandaEnvironment.LIVE

    def is_configured(self) -> bool:
        """Check if OANDA credentials are configured.

        Returns:
            True if both API token and account ID are set, False otherwise
        """
        return (
            self.oanda_token is not None
            and self.oanda_account_id is not None
        )

    def get_token(self) -> str:
        """Get the API token value safely.

        Returns:
            API token string

        Raises:
            ValueError: If token is not configured
        """
        if self.oanda_token is None:
            msg = (
                "OANDA API token not configured. "
                "Set OANDA_API_TOKEN environment variable."
            )
            raise ValueError(msg)
        return self.oanda_token.get_secret_value()

    def get_account_id(self) -> str:
        """Get the account ID safely.

        Returns:
            Account ID string

        Raises:
            ValueError: If account ID is not configured
        """
        if self.oanda_account_id is None:
            msg = (
                "OANDA account ID not configured. "
                "Set OANDA_ACCOUNT_ID environment variable."
            )
            raise ValueError(msg)
        return self.oanda_account_id


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
