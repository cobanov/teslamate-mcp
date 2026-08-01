"""Application configuration loaded from environment variables."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    All values can be supplied via environment variables or a `.env` file.
    `DATABASE_URL` is the only required field.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = Field(
        ...,
        description="PostgreSQL connection string for the TeslaMate database.",
    )
    auth_token: SecretStr | None = Field(
        default=None,
        description="Bearer token for HTTP transport. Auth is disabled when empty.",
    )

    host: str = Field(default="0.0.0.0", description="HTTP bind host.")
    port: int = Field(default=8888, description="HTTP bind port.", ge=1, le=65535)

    pool_min_size: int = Field(default=1, ge=1)
    pool_max_size: int = Field(default=10, ge=1)

    query_timeout_ms: int = Field(
        default=5000,
        ge=100,
        description="statement_timeout applied to custom SQL queries.",
    )
    statement_timeout_ms: int = Field(
        default=30000,
        ge=100,
        description=(
            "Connection-level statement_timeout bounding every query, including "
            "the bundled reports. Ignored when DATABASE_URL sets its own options."
        ),
    )
    custom_sql_row_limit: int = Field(
        default=1000,
        ge=1,
        description="Default LIMIT injected into custom SQL queries when absent.",
    )

    enable_charging_writes: bool = Field(
        default=False,
        description=(
            "Register the set_charging_cost write tool. Requires the DB role to "
            "hold UPDATE (cost) ON charging_processes. Off by default."
        ),
    )

    report_timezone: str = Field(
        default="UTC",
        description="IANA timezone applied to date bucketing in predefined queries.",
    )

    log_level: str = Field(default="INFO")
    debug: bool = Field(default=False, description="Enable Starlette debug mode.")

    @field_validator("report_timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        # Fail fast at startup; PostgreSQL would otherwise error on the first query.
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone: {value!r}") from exc
        return value


def load_settings() -> Settings:
    """Load settings from the environment. Raises ValidationError on missing required fields."""
    return Settings()  # type: ignore[call-arg]
