"""Authentication and authorization dependencies.

The token type is enforced on every request, and the principal is re-loaded from the
database so deactivation and membership changes take effect immediately rather than
waiting for access-token expiry.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.security import (
    DEVICE_TOKEN_TYPE,
    HUMAN_TOKEN_TYPE,
    TokenError,
    decode_access_token,
)
from app.db.session import get_db
from app.models.device import Device
from app.models.enums import DeviceStatus
from app.models.identity import User
from app.services.auth_service import MembershipContext, active_memberships

bearer_scheme = HTTPBearer(auto_error=False)


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _unauthorized(
    code: str = "invalid_token", message: str = "Authentication is required."
) -> AppError:
    return AppError(status_code=401, code=code, message=message)


def _bearer_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None or not credentials.credentials:
        raise _unauthorized()
    return credentials.credentials


@dataclass(frozen=True)
class CurrentUser:
    user: User
    memberships: list[MembershipContext]


@dataclass(frozen=True)
class CurrentDevice:
    device: Device


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> CurrentUser:
    token = _bearer_token(credentials)
    try:
        claims = decode_access_token(
            token=token,
            secret=settings.app_secret_key,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            expected_type=HUMAN_TOKEN_TYPE,
        )
    except TokenError as exc:
        if "wrong token type" in str(exc):
            raise AppError(
                status_code=403,
                code="device_token_used_on_user_route",
                message="A device credential cannot access the portal.",
            ) from exc
        raise _unauthorized() from exc

    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise _unauthorized() from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("account_inactive", "This account is inactive.")
    return CurrentUser(user=user, memberships=active_memberships(db, user.id))


def get_current_device(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> CurrentDevice:
    token = _bearer_token(credentials)
    try:
        claims = decode_access_token(
            token=token,
            secret=settings.app_secret_key,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            expected_type=DEVICE_TOKEN_TYPE,
        )
    except TokenError as exc:
        if "wrong token type" in str(exc):
            raise AppError(
                status_code=403,
                code="user_token_used_on_device_route",
                message="A portal session cannot submit device data.",
            ) from exc
        raise _unauthorized() from exc

    try:
        device_id = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise _unauthorized() from exc

    device = db.get(Device, device_id)
    if device is None:
        raise _unauthorized()
    if device.status in {DeviceStatus.SUSPENDED, DeviceStatus.RETIRED}:
        raise AppError(
            status_code=403,
            code="device_suspended",
            message="This device is not permitted to submit data.",
        )
    return CurrentDevice(device=device)


def require_portal_user(
    principal: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    if not principal.user.is_super_admin and not principal.memberships:
        raise AppError(
            status_code=403,
            code=ErrorCode.FORBIDDEN,
            message="This account has no active department membership.",
        )
    return principal


def require_super_admin(
    principal: CurrentUser = Depends(require_portal_user),
) -> CurrentUser:
    if not principal.user.is_super_admin:
        raise AppError(
            status_code=403,
            code=ErrorCode.FORBIDDEN,
            message="Super administrator permission is required.",
        )
    return principal
