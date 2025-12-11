"""Shared TimescaleDB/Postgres settings for scripts and services (2025-ready).

Modern implementation with:
- Pydantic BaseSettings v2 with SettingsConfigDict
- TypedDict for type-safe connection parameters
- PostgresDsn validation for connection strings
- Environment variable integration with validation
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, TypedDict

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AsyncPGConnection(TypedDict):
    """Type-safe asyncpg connection parameters.

    Used to ensure proper types when unpacking to asyncpg.connect().
    """

    host: str
    port: int
    user: str
    password: str
    database: str


class DatabaseSettings(BaseSettings):
    """Centralized database configuration with environment variable support.

    Configuration priority (highest to lowest):
    1. Environment variables (POSTGRES_HOST, POSTGRES_PORT, etc.)
    2. .env file
    3. Default values

    Example .env:
        POSTGRES_HOST=localhost
        POSTGRES_PORT=5433
        POSTGRES_USER=trading_user
        POSTGRES_PASSWORD=secure_password_here
        POSTGRES_DB=trading_db
        POSTGRES_MIN_SIZE=5
        POSTGRES_MAX_SIZE=20
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )

    # Connection parameters
    host: Annotated[
        str,
        Field(
            description="PostgreSQL host address",
            examples=["localhost", "timescaledb", "192.168.1.100"],
        ),
    ] = "localhost"

    port: Annotated[
        int,
        Field(
            ge=1,
            le=65535,
            description="PostgreSQL port number",
        ),
    ] = 5433

    user: Annotated[
        str,
        Field(
            min_length=1,
            description="PostgreSQL username",
        ),
    ] = "trading_user"

    password: Annotated[
        SecretStr,
        Field(
            description="PostgreSQL password (stored securely)",
        ),
    ] = SecretStr("trading_pass_change_in_production")

    database: Annotated[
        str,
        Field(
            min_length=1,
            description="PostgreSQL database name",
        ),
    ] = "trading_db"

    # Connection pool settings (optional)
    min_size: Annotated[
        int,
        Field(
            ge=1,
            le=100,
            description="Minimum connection pool size",
        ),
    ] = 5

    max_size: Annotated[
        int,
        Field(
            ge=1,
            le=100,
            description="Maximum connection pool size",
        ),
    ] = 20

    timeout: Annotated[
        float,
        Field(
            ge=1.0,
            le=300.0,
            description="Connection timeout in seconds",
        ),
    ] = 10.0

    @field_validator("max_size")
    @classmethod
    def validate_max_size(cls, v: int, info) -> int:
        """Ensure max_size >= min_size."""
        if "min_size" in info.data and v < info.data["min_size"]:
            msg = f"max_size ({v}) must be >= min_size ({info.data['min_size']})"
            raise ValueError(msg)
        return v

    def asyncpg_kwargs(self) -> AsyncPGConnection:
        """Return type-safe connection kwargs for asyncpg.connect().

        Returns:
            TypedDict with properly typed connection parameters
        """
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password.get_secret_value(),
            "database": self.database,
        }

    def get_dsn(self) -> str:
        """Get PostgreSQL DSN connection string.

        Returns:
            Connection string in format:
            postgresql://user:password@host:port/database
        """
        password = self.password.get_secret_value()
        return f"postgresql://{self.user}:{password}@{self.host}:{self.port}/{self.database}"

    def get_pool_kwargs(self) -> dict[str, int | float]:
        """Get connection pool configuration.

        Returns:
            Pool configuration parameters
        """
        return {
            "min_size": self.min_size,
            "max_size": self.max_size,
            "timeout": self.timeout,
        }


@lru_cache
def get_database_settings() -> DatabaseSettings:
    """Get cached database settings instance.

    Uses lru_cache to ensure settings are only loaded once from environment.

    Returns:
        Singleton DatabaseSettings instance
    """
    return DatabaseSettings()
