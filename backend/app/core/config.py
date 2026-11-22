"""Typed application configuration.

All runtime wiring comes from environment variables (see ``.env.example`` at the
repository root). Secrets have no safe production default: the application refuses to
start in production with the development placeholder secret.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_PLACEHOLDER = "dev-only-change-me"
MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    """Application settings resolved from the environment and ``.env`` files."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Rice Age Portal API"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    app_secret_key: str = DEV_SECRET_PLACEHOLDER
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=120)
    refresh_token_ttl_days: int = Field(default=7, ge=1, le=30)

    database_url: str = "postgresql+psycopg://rice_age:rice_age@localhost:5432/rice_age"
    database_echo: bool = False

    cors_origins: str = "http://localhost:5173"

    storage_backend: Literal["local", "s3"] = "local"
    storage_local_root: str = "./storage"
    storage_signed_url_ttl_seconds: int = Field(default=300, ge=30, le=3600)

    # PROVISIONAL until the device team confirms limits (decision DR-005).
    max_report_bytes: int = Field(default=25 * 1024 * 1024, ge=1024)
    max_image_bytes: int = Field(default=15 * 1024 * 1024, ge=1024)
    max_scan_payload_bytes: int = Field(default=1 * 1024 * 1024, ge=1024)

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        normalised = value.upper()
        if normalised not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return normalised

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS allowlist parsed from a comma-separated value.

        Wildcards are rejected because credentialed requests must never be allowed
        against an open origin list.
        """

        origins = [origin.strip().rstrip("/") for origin in self.cors_origins.split(",")]
        return [origin for origin in origins if origin and origin != "*"]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @model_validator(mode="after")
    def _guard_production_secrets(self) -> Settings:
        if self.is_production:
            if self.app_secret_key == DEV_SECRET_PLACEHOLDER:
                raise ValueError(
                    "app_secret_key must be set to a real secret in production; "
                    "the development placeholder is not allowed"
                )
            if len(self.app_secret_key) < MIN_SECRET_LENGTH:
                raise ValueError(
                    f"app_secret_key must be at least {MIN_SECRET_LENGTH} characters in production"
                )
            if self.storage_backend == "local":
                raise ValueError(
                    "storage_backend must be 's3' in production; local storage is for "
                    "development and tests only"
                )
            if self.debug:
                raise ValueError("debug must be disabled in production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
