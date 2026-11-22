"""Liveness and readiness behaviour, including a real database dependency."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.db.session import get_db
from app.main import create_app


class _RecordingSession:
    """Stand-in session that records the statement it was asked to execute."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> None:
        self.statements.append(str(statement))
        return None


class _BrokenSession:
    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> None:
        raise SQLAlchemyError("connection refused")


def test_liveness_reports_service_and_version_outside_production(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Rice Age Portal API",
        "version": "0.1.0",
        "environment": "test",
    }


def test_production_liveness_withholds_internal_detail() -> None:
    production = Settings(
        environment="production",
        app_secret_key="production-secret-" + "b" * 40,
        storage_backend="s3",
        storage_s3_bucket="rice-age-test",
        debug=False,
        database_url="postgresql+psycopg://user:pass@db:5432/rice_age",
    )
    with TestClient(create_app(production), raise_server_exceptions=False) as client:
        body = client.get("/api/v1/health").json()

        assert body == {
            "status": "ok",
            "service": "Rice Age Portal API",
            "version": None,
            "environment": None,
        }
        # Interactive docs are disabled outside development.
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_readiness_executes_a_database_check(app: FastAPI, client: TestClient) -> None:
    session = _RecordingSession()
    app.dependency_overrides[get_db] = lambda: session

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}
    assert session.statements == ["SELECT 1"]


def test_readiness_fails_closed_when_database_is_unavailable(
    app: FastAPI, client: TestClient
) -> None:
    app.dependency_overrides[get_db] = lambda: _BrokenSession()

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "dependency_unavailable"
    assert error["message"] == "A required dependency is unavailable."
    assert error["request_id"]
    # The internal driver message must not leak to the client.
    assert "connection refused" not in response.text
