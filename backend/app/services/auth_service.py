"""Human authentication: credential checks and rotating refresh sessions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    verify_password,
)
from app.models.enums import AuditActorType, MembershipRole
from app.models.identity import Membership, User, UserSession
from app.models.organization import Department
from app.schemas.auth import MembershipView, UserView
from app.services.audit import normalise_ip, record_audit


@dataclass(frozen=True)
class MembershipContext:
    membership: Membership
    department: Department

    @property
    def role(self) -> MembershipRole:
        return self.membership.role


def utcnow() -> datetime:
    return datetime.now(UTC)


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))


def build_user_view(db: Session, user: User) -> UserView:
    contexts = active_memberships(db, user.id)
    return UserView(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_super_admin=user.is_super_admin,
        memberships=[
            MembershipView(
                department_id=context.department.id,
                department_code=context.department.code,
                department_name=context.department.name,
                role=context.role,
            )
            for context in contexts
        ],
    )


def active_memberships(db: Session, user_id: uuid.UUID) -> list[MembershipContext]:
    rows = db.execute(
        select(Membership, Department)
        .join(Department, Department.id == Membership.department_id)
        .where(
            Membership.user_id == user_id,
            Membership.is_active.is_(True),
            Department.is_active.is_(True),
        )
        .order_by(Department.code)
    ).all()
    return [MembershipContext(membership=row[0], department=row[1]) for row in rows]


def authenticate_user(
    db: Session,
    settings: Settings,
    *,
    email: str,
    password: str,
    ip_address: str | None,
    user_agent: str | None,
    request_id: str | None,
) -> User:
    user = find_user_by_email(db, email)
    encoded_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    # Always run the expensive verification, even for an unknown account.
    valid = verify_password(encoded_hash, password)

    if user is None or not valid:
        record_audit(
            db,
            action="auth.login_failed",
            actor_type=AuditActorType.SYSTEM,
            target_type="user",
            target_id=user.id if user is not None else None,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        db.commit()
        raise AppError(
            status_code=401,
            code=ErrorCode.INVALID_CREDENTIALS,
            message="Email or password is incorrect.",
        )

    if not user.is_active:
        raise AppError(
            status_code=403,
            code="account_inactive",
            message="This account is inactive.",
        )

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = utcnow()
    record_audit(
        db,
        action="auth.login_succeeded",
        actor_type=AuditActorType.USER,
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )
    return user


def create_session(
    db: Session,
    settings: Settings,
    *,
    user: User,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[str, UserSession]:
    raw_token = generate_refresh_token()
    now = utcnow()
    session = UserSession(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(raw_token),
        token_family_id=uuid.uuid4(),
        issued_at=now,
        expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        ip_address=normalise_ip(ip_address),
        user_agent=(user_agent or "")[:1000] or None,
    )
    db.add(session)
    return raw_token, session


def _revoke_family(db: Session, family_id: uuid.UUID, now: datetime) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.token_family_id == family_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def rotate_session(
    db: Session,
    settings: Settings,
    *,
    raw_token: str,
    ip_address: str | None,
    user_agent: str | None,
    request_id: str | None,
) -> tuple[str, User]:
    """Rotate a refresh token, detecting reuse of an already-rotated token."""

    now = utcnow()
    session = db.scalar(
        select(UserSession).where(UserSession.refresh_token_hash == hash_refresh_token(raw_token))
    )
    if session is None:
        raise AppError(
            status_code=401,
            code="invalid_refresh",
            message="The session is invalid. Sign in again.",
        )

    if session.revoked_at is not None:
        # Reuse of a rotated token: assume theft and kill every descendant session.
        _revoke_family(db, session.token_family_id, now)
        record_audit(
            db,
            action="auth.refresh_reuse_detected",
            actor_type=AuditActorType.USER,
            actor_user_id=session.user_id,
            target_type="user_session",
            target_id=session.id,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        db.commit()
        raise AppError(
            status_code=401,
            code="session_revoked",
            message="This session was revoked. Sign in again.",
        )

    if session.expires_at <= now:
        session.revoked_at = now
        db.commit()
        raise AppError(
            status_code=401,
            code="session_expired",
            message="This session expired. Sign in again.",
        )

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        _revoke_family(db, session.token_family_id, now)
        db.commit()
        raise AppError(
            status_code=403,
            code="account_inactive",
            message="This account is inactive.",
        )

    new_raw = generate_refresh_token()
    session.revoked_at = now
    session.last_used_at = now
    db.add(
        UserSession(
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(new_raw),
            token_family_id=session.token_family_id,
            issued_at=now,
            expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
            ip_address=normalise_ip(ip_address),
            user_agent=(user_agent or "")[:1000] or None,
        )
    )
    record_audit(
        db,
        action="auth.refresh_rotated",
        actor_type=AuditActorType.USER,
        actor_user_id=user.id,
        target_type="user_session",
        target_id=session.id,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )
    # Persist the revocation and the replacement together; without this the old token
    # would stay valid and reuse detection could never trigger.
    db.commit()
    return new_raw, user


def session_family(db: Session, raw_token: str) -> uuid.UUID | None:
    """Return the token family for a refresh token, used to keep the current login."""

    return db.scalar(
        select(UserSession.token_family_id).where(
            UserSession.refresh_token_hash == hash_refresh_token(raw_token)
        )
    )


def revoke_session_by_token(db: Session, raw_token: str) -> bool:
    session = db.scalar(
        select(UserSession).where(UserSession.refresh_token_hash == hash_refresh_token(raw_token))
    )
    if session is None:
        return False
    _revoke_family(db, session.token_family_id, utcnow())
    return True


def revoke_all_user_sessions(
    db: Session, user_id: uuid.UUID, *, except_family: uuid.UUID | None = None
) -> None:
    statement = update(UserSession).where(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
    )
    if except_family is not None:
        statement = statement.where(UserSession.token_family_id != except_family)
    db.execute(statement.values(revoked_at=utcnow()))


def change_password(
    db: Session,
    *,
    user: User,
    current_password: str,
    new_password: str,
    request_id: str | None,
    keep_family_id: uuid.UUID | None = None,
) -> None:
    if not verify_password(user.password_hash, current_password):
        raise AppError(
            status_code=401,
            code=ErrorCode.INVALID_CREDENTIALS,
            message="The current password is incorrect.",
        )
    if current_password == new_password:
        raise AppError(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="The new password must differ from the current one.",
        )
    user.password_hash = hash_password(new_password)
    revoke_all_user_sessions(db, user.id, except_family=keep_family_id)
    record_audit(
        db,
        action="auth.password_changed",
        actor_type=AuditActorType.USER,
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        request_id=request_id,
    )
