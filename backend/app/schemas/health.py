"""Health and readiness response models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness payload. Version detail is withheld in production."""

    status: Literal["ok"] = "ok"
    service: str
    version: str | None = None
    environment: str | None = None


class ReadinessResponse(BaseModel):
    """Readiness payload reported only after a successful dependency check."""

    status: Literal["ready"] = "ready"
    database: Literal["ok"] = "ok"
