"""Modern credential management with pydantic-settings (2025 standard).

Features:
- Type-safe configuration with validation
- SecretStr for sensitive data (doesn't leak in logs)
- Multiple sources: .env files, environment variables, OS keyring
- Automatic environment variable aliasing
"""

from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class BrokerCredentials(BaseSettings):
    """Unified broker credentials with modern Pydantic V2.

    Loads from .env file or environment variables.
    Sensitive values use SecretStr to prevent accidental leakage.

    Example:
        >>> creds = BrokerCredentials()
        >>> # Access with .get_secret_value()
        >>> api_key = creds.alpaca_api_key.get_secret_value()
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore unknown environment variables
    )

    # ========================================================================
    # Alpaca (US Stocks + Crypto)
    # ========================================================================

    alpaca_api_key: SecretStr = Field(
        default="",
        alias="ALPACA_API_KEY",
        description="Alpaca API key (paper or live)",
    )
    alpaca_api_secret: SecretStr = Field(
        default="",
        alias="ALPACA_API_SECRET",
        description="Alpaca API secret",
    )
    alpaca_paper: bool = Field(
        default=True,
        alias="ALPACA_PAPER",
        description="Use paper trading (True) or live (False)",
    )

    # OAuth2 for Alpaca Broker API (white-label solutions)
    alpaca_oauth_client_id: Optional[SecretStr] = Field(
        default=None,
        alias="ALPACA_OAUTH_CLIENT_ID",
    )
    alpaca_oauth_client_secret: Optional[SecretStr] = Field(
        default=None,
        alias="ALPACA_OAUTH_CLIENT_SECRET",
    )

    # ========================================================================
    # Kraken (Crypto Exchange)
    # ========================================================================

    kraken_api_key: Optional[SecretStr] = Field(
        default=None,
        alias="KRAKEN_API_KEY",
    )
    kraken_api_secret: Optional[SecretStr] = Field(
        default=None,
        alias="KRAKEN_API_SECRET",
    )

    # ========================================================================
    # Bybit (Crypto Derivatives)
    # ========================================================================

    bybit_api_key: Optional[SecretStr] = Field(
        default=None,
        alias="BYBIT_API_KEY",
    )
    bybit_api_secret: Optional[SecretStr] = Field(
        default=None,
        alias="BYBIT_API_SECRET",
    )
    bybit_testnet: bool = Field(
        default=True,
        alias="BYBIT_TESTNET",
    )

    # ========================================================================
    # Interactive Brokers (Everything)
    # ========================================================================

    ibkr_host: str = Field(
        default="127.0.0.1",
        alias="IB_HOST",
    )
    ibkr_port: int = Field(
        default=7497,  # 7497 for paper, 7496 for live
        alias="IB_PORT",
    )
    ibkr_client_id: int = Field(
        default=1,
        alias="IB_CLIENT_ID",
    )

    # IBKR Web API (OAuth2) - alternative to TWS
    ibkr_oauth_client_id: Optional[SecretStr] = Field(
        default=None,
        alias="IBKR_CLIENT_ID",
    )
    ibkr_oauth_client_secret: Optional[SecretStr] = Field(
        default=None,
        alias="IBKR_CLIENT_SECRET",
    )

    # ========================================================================
    # Binance (Crypto - existing)
    # ========================================================================

    binance_api_key: Optional[SecretStr] = Field(
        default=None,
        alias="BINANCE_API_KEY",
    )
    binance_api_secret: Optional[SecretStr] = Field(
        default=None,
        alias="BINANCE_API_SECRET",
    )
    binance_testnet: bool = Field(
        default=True,
        alias="BINANCE_TESTNET",
    )

    # ========================================================================
    # OANDA (Forex)
    # ========================================================================

    oanda_api_key: Optional[SecretStr] = Field(
        default=None,
        alias="OANDA_API_KEY",
    )
    oanda_account_id: Optional[str] = Field(
        default=None,
        alias="OANDA_ACCOUNT_ID",
    )

    # ========================================================================
    # Tradier (US Stocks - Alternative)
    # ========================================================================

    tradier_access_token: Optional[SecretStr] = Field(
        default=None,
        alias="TRADIER_ACCESS_TOKEN",
    )

    def has_alpaca(self) -> bool:
        """Check if Alpaca credentials are configured."""
        return bool(
            self.alpaca_api_key.get_secret_value()
            and self.alpaca_api_secret.get_secret_value()
        )

    def has_kraken(self) -> bool:
        """Check if Kraken credentials are configured."""
        return bool(
            self.kraken_api_key
            and self.kraken_api_secret
            and self.kraken_api_key.get_secret_value()
            and self.kraken_api_secret.get_secret_value()
        )

    def has_bybit(self) -> bool:
        """Check if Bybit credentials are configured."""
        return bool(
            self.bybit_api_key
            and self.bybit_api_secret
            and self.bybit_api_key.get_secret_value()
            and self.bybit_api_secret.get_secret_value()
        )

    def has_ibkr(self) -> bool:
        """Check if IBKR connection is configured."""
        return self.ibkr_host != ""

    def has_binance(self) -> bool:
        """Check if Binance credentials are configured."""
        return bool(
            self.binance_api_key
            and self.binance_api_secret
            and self.binance_api_key.get_secret_value()
            and self.binance_api_secret.get_secret_value()
        )

    @classmethod
    def from_keyring(cls, service_name: str = "trading_system") -> "BrokerCredentials":
        """Alternative: Load credentials from OS keyring for enhanced security.

        This is more secure than .env files as credentials are stored
        in the operating system's credential manager.

        Args:
            service_name: Keyring service name

        Returns:
            BrokerCredentials loaded from keyring

        Example:
            >>> import keyring
            >>> keyring.set_password("trading_system", "alpaca_api_key", "PK...")
            >>> creds = BrokerCredentials.from_keyring()
        """
        import keyring

        return cls(
            alpaca_api_key=keyring.get_password(service_name, "alpaca_api_key") or "",
            alpaca_api_secret=keyring.get_password(service_name, "alpaca_api_secret")
            or "",
            kraken_api_key=keyring.get_password(service_name, "kraken_api_key"),
            kraken_api_secret=keyring.get_password(service_name, "kraken_api_secret"),
            bybit_api_key=keyring.get_password(service_name, "bybit_api_key"),
            bybit_api_secret=keyring.get_password(service_name, "bybit_api_secret"),
        )
