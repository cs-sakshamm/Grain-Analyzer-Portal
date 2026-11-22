"""Liveness and readiness endpoints.

Readiness performs a real database round-trip so a broken deployment is reported as
unready instead of accepting traffic. No dependency detail is exposed beyond a stable
status string.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.db.session import get_db
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health(request: Request) -> HealthResponse:
    settings = _settings(request)
    if settings.is_production:
        return HealthResponse(status="ok", service=settings.app_name)
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness probe")
def readiness(db: Annotated[Session, Depends(get_db)]) -> ReadinessResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        # Logged by the global handler; the client only learns it is unready.
        raise AppError(
            status_code=503,
            code=ErrorCode.DEPENDENCY_UNAVAILABLE,
            message="A required dependency is unavailable.",
        ) from exc
    return ReadinessResponse()
