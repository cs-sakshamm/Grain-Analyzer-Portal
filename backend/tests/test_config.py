"""Configuration parsing and production guardrails."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import DEV_SECRET_PLACEHOLDER, Settings

VALID_PROD = {
    "environment": "production",
    "app_secret_key": "production-secret-" + "c" * 40,
    "storage_backend": "s3",
    "storage_s3_bucket": "rice-age-prod",
    "debug": False,
    "database_url": "postgresql+psycopg://user:pass@db:5432/rice_age",
}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://a.example", ["http://a.example"]),
        ("http://a.example , http://b.example/", ["http://a.example", "http://b.example"]),
        ("*", []),
        ("", []),
        ("http://a.example,,", ["http://a.example"]),
    ],
)
def test_cors_origins_are_normalised(raw: str, expected: list[str]) -> None:
    settings = Settings(cors_origins=raw, database_url="sqlite+pysqlite:///:memory:")

    assert settings.cors_origin_list == expected


def test_production_rejects_the_development_secret() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(**{**VALID_PROD, "app_secret_key": DEV_SECRET_PLACEHOLDER})

    assert "app_secret_key" in str(excinfo.value)


def test_production_rejects_a_short_secret() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(**{**VALID_PROD, "app_secret_key": "too-short"})

    assert "at least" in str(excinfo.value)


def test_production_rejects_local_file_storage() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(**{**VALID_PROD, "storage_backend": "local"})

    assert "storage_backend" in str(excinfo.value)


def test_production_requires_an_s3_bucket() -> None:
    settings = {**VALID_PROD, "storage_s3_bucket": None}

    with pytest.raises(ValidationError) as excinfo:
        Settings(**settings)

    assert "storage_s3_bucket" in str(excinfo.value)


def test_production_rejects_debug_mode() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(**{**VALID_PROD, "debug": True})

    assert "debug" in str(excinfo.value)


def test_production_accepts_hardened_settings() -> None:
    settings = Settings(**VALID_PROD)

    assert settings.is_production is True
    assert settings.cors_origin_list == ["http://localhost:5173"]


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(log_level="verbose", database_url="sqlite+pysqlite:///:memory:")


@pytest.mark.parametrize("field", ["access_token_ttl_minutes", "refresh_token_ttl_days"])
def test_token_ttls_must_be_positive(field: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: 0}, database_url="sqlite+pysqlite:///:memory:")
