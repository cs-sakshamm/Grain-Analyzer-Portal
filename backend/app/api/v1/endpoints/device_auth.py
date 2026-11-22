"""Device authentication: per-device client credentials (contract §3.1)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, request_id
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.ratelimit import device_token_limiter
from app.core.security import (
    DEVICE_TOKEN_TYPE,
    create_access_token,
    verify_password,
)
from app.db.session import get_db
from app.models.device import DeviceCredential
from app.models.enums import AuditActorType, DeviceStatus
from app.services.audit import record_audit
from app.services.scan_service import active_assignment

router = APIRouter(prefix="/device-auth", tags=["device-auth"])


class DeviceTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grant_type: Literal["client_credentials"]
    client_id: str = Field(min_length=4, max_length=64)
    client_secret: str = Field(min_length=8, max_length=256)


class DeviceTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    device_id: str
    scope: str = "device:scan"


def _invalid_client() -> AppError:
    return AppError(
        status_code=401,
        code="invalid_client",
        message="Device credentials are invalid.",
    )


@router.post("/token", response_model=DeviceTokenResponse)
def issue_device_token(
    payload: DeviceTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> DeviceTokenResponse:
    ip = request.client.host if request.client else None
    allowed, retry_after = device_token_limiter.check(
        f"device-token:{payload.client_id}",
        limit=10,
        window_seconds=60,
    )
    if not allowed:
        raise AppError(
            429,
            ErrorCode.RATE_LIMITED,
            "Too many token requests.",
            headers={"Retry-After": str(retry_after)},
        )

    credential = db.scalar(
        select(DeviceCredential).where(
            DeviceCredential.client_id == payload.client_id,
            DeviceCredential.revoked_at.is_(None),
        )
    )
    if credential is None:
        record_audit(
            db,
            action="device.auth_failed",
            actor_type=AuditActorType.SYSTEM,
            ip_address=ip,
            user_agent=request.headers.get("user-agent"),
            request_id=request_id(request),
            metadata={"client_id": payload.client_id, "reason": "unknown_credential"},
        )
        db.commit()
        raise _invalid_client()

    now = datetime.now(UTC)
    if credential.expires_at is not None and credential.expires_at <= now:
        raise _invalid_client()
    if not verify_password(credential.secret_hash, payload.client_secret):
        record_audit(
            db,
            action="device.auth_failed",
            actor_type=AuditActorType.SYSTEM,
            ip_address=ip,
            user_agent=request.headers.get("user-agent"),
            request_id=request_id(request),
            metadata={"client_id": payload.client_id, "reason": "bad_secret"},
        )
        db.commit()
        raise _invalid_client()

    device = credential.device
    if device.status in {DeviceStatus.SUSPENDED, DeviceStatus.RETIRED}:
        raise AppError(403, "device_suspended", "This device is not permitted to submit data.")
    assignment = active_assignment(db, device.id)
    if assignment is None or not assignment[1].is_active:
        raise AppError(403, "device_unassigned", "This device has no active department assignment.")

    access_token, expires_in = create_access_token(
        secret=settings.app_secret_key,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        ttl_minutes=settings.access_token_ttl_minutes,
        subject=device.id,
        token_type=DEVICE_TOKEN_TYPE,
        claims={"scope": "device:scan", "device_uid": device.device_uid},
    )
    device.last_seen_at = now
    db.commit()
    return DeviceTokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        device_id=device.device_uid,
    )
