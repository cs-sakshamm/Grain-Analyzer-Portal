"""Human authentication endpoints (contract §2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_app_settings, request_id, require_portal_user
from app.core.config import Settings
from app.core.errors import AppError
from app.core.ratelimit import login_limiter
from app.core.security import HUMAN_TOKEN_TYPE, create_access_token
from app.db.session import get_db
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    TokenResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_PATH = "/api/v1/auth"


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _set_refresh_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,
        secure=settings.refresh_cookie_secure_effective,
        samesite="strict",
        path=REFRESH_PATH,
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=REFRESH_PATH,
        httponly=True,
        secure=settings.refresh_cookie_secure_effective,
        samesite="strict",
    )


def _token_response(
    db: Session, settings: Settings, user, response: Response, refresh_token: str
) -> TokenResponse:
    access_token, expires_in = create_access_token(
        secret=settings.app_secret_key,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        ttl_minutes=settings.access_token_ttl_minutes,
        subject=user.id,
        token_type=HUMAN_TOKEN_TYPE,
        claims={"is_super_admin": user.is_super_admin},
    )
    _set_refresh_cookie(response, settings, refresh_token)
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=auth_service.build_user_view(db, user),
    )


@router.post("/login", response_model=TokenResponse, summary="Sign in")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> TokenResponse:
    ip = client_ip(request)
    allowed, retry_after = login_limiter.check(
        f"login:{payload.email.lower()}:{ip}",
        limit=settings.login_max_attempts,
        window_seconds=settings.login_window_seconds,
    )
    if not allowed:
        raise AppError(
            status_code=429,
            code="too_many_attempts",
            message="Too many sign-in attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    user = auth_service.authenticate_user(
        db,
        settings,
        email=payload.email,
        password=payload.password,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        request_id=request_id(request),
    )
    if not user.is_super_admin and not auth_service.active_memberships(db, user.id):
        raise AppError(
            status_code=403,
            code="account_inactive",
            message="This account has no active department membership.",
        )
    refresh_token, _session = auth_service.create_session(
        db,
        settings,
        user=user,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return _token_response(db, settings, user, response, refresh_token)


@router.post("/refresh", response_model=TokenResponse, summary="Rotate the session")
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> TokenResponse:
    raw = request.cookies.get(settings.refresh_cookie_name)
    if not raw:
        _clear_refresh_cookie(response, settings)
        raise AppError(
            status_code=401,
            code="invalid_refresh",
            message="The session is invalid. Sign in again.",
        )
    new_token, user = auth_service.rotate_session(
        db,
        settings,
        raw_token=raw,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=request_id(request),
    )
    return _token_response(db, settings, user, response, new_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Sign out")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> Response:
    raw = request.cookies.get(settings.refresh_cookie_name)
    if raw:
        auth_service.revoke_session_by_token(db, raw)
        db.commit()
    _clear_refresh_cookie(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=MeResponse, summary="Current user")
def me(
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> MeResponse:
    return MeResponse(user=auth_service.build_user_view(db, principal.user))


@router.post(
    "/password/change",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change the current password",
)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> Response:
    raw = request.cookies.get(settings.refresh_cookie_name)
    keep_family = auth_service.session_family(db, raw) if raw else None
    auth_service.change_password(
        db,
        user=principal.user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        request_id=request_id(request),
        keep_family_id=keep_family,
    )
    db.commit()
    _clear_refresh_cookie(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
