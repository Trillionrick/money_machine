"""Shared TimescaleDB/Postgres settings for scripts and services (2025-ready)."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Centralized database configuration pulled from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    host: str = Field(default="localhost", alias="POSTGRES_HOST")
    port: int = Field(default=5433, alias="POSTGRES_PORT")
    user: str = Field(default="trading_user", alias="POSTGRES_USER")
    password: str = Field(
        default="trading_pass_change_in_production", alias="POSTGRES_PASSWORD"
    )
    database: str = Field(default="trading_db", alias="POSTGRES_DB")

    def asyncpg_kwargs(self) -> dict[str, object]:
        """Return connection kwargs compatible with asyncpg."""
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "database": self.database,
        }
