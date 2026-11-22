"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        app_secret_key="test-secret-" + "a" * 40,
        database_url="sqlite+pysqlite:///:memory:",
        cors_origins="http://localhost:5173, http://testserver",
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # raise_server_exceptions=False so the unhandled-error handler is exercised
    # instead of the exception escaping the test client.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
