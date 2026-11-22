"""Administration services.

Authorization is decided here, not in the route handlers, so every caller inherits the
same rules. Every mutation writes an audit row in the same transaction. Interim DR-019
policy: a department administrator may manage users in their own department only and
may never grant super-admin status.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.security import (
    generate_client_id,
    generate_device_secret,
    hash_password,
)
from app.models.device import Device, DeviceAssignment, DeviceCredential
from app.models.enums import AuditActorType, DeviceStatus, MembershipRole
from app.models.identity import Membership, User
from app.models.organization import Department
from app.schemas.admin import (
    AssignmentCreate,
    AssignmentView,
    CredentialIssued,
    CredentialView,
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentView,
    DeviceCreate,
    DeviceUpdate,
    DeviceView,
    MembershipCreate,
    MembershipUpdate,
    MembershipView,
    UserCreate,
    UserUpdate,
    UserView,
)
from app.services.audit import record_audit
from app.services.auth_service import MembershipContext, revoke_all_user_sessions
from app.services.authorization import (
    can_manage_department,
    can_read_department,
    not_visible,
    require_department_admin,
)


@dataclass(frozen=True)
class AuditContext:
    user_id: uuid.UUID
    ip_address: str | None = None
    user_agent: str | None = None
    request_id: str | None = None


def utcnow() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- views


def _department_view(department: Department) -> DepartmentView:
    return DepartmentView(
        id=department.id,
        code=department.code,
        name=department.name,
        location=department.location,
        is_active=department.is_active,
        created_at=department.created_at,
        updated_at=department.updated_at,
    )


def _membership_views(db: Session, user_id: uuid.UUID) -> list[MembershipView]:
    rows = db.execute(
        select(Membership, Department)
        .join(Department, Department.id == Membership.department_id)
        .where(Membership.user_id == user_id)
        .order_by(Department.code)
    ).all()
    return [
        MembershipView(
            id=membership.id,
            department_id=department.id,
            department_code=department.code,
            department_name=department.name,
            role=membership.role,
            is_active=membership.is_active,
        )
        for membership, department in rows
    ]


def user_view(db: Session, user: User) -> UserView:
    return UserView(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_super_admin=user.is_super_admin,
        last_login_at=user.last_login_at,
        memberships=_membership_views(db, user.id),
    )


def _active_assignment(db: Session, device_id: uuid.UUID) -> DeviceAssignment | None:
    return db.scalar(
        select(DeviceAssignment).where(
            DeviceAssignment.device_id == device_id,
            DeviceAssignment.effective_to.is_(None),
        )
    )


def _device_view(db: Session, device: Device) -> DeviceView:
    assignment = _active_assignment(db, device.id)
    return DeviceView(
        id=device.id,
        device_uid=device.device_uid,
        serial_number=device.serial_number,
        friendly_name=device.friendly_name,
        model=device.model,
        firmware_version=device.firmware_version,
        installation_location=device.installation_location,
        status=device.status,
        active_department_id=assignment.department_id if assignment else None,
        last_seen_at=device.last_seen_at,
        last_upload_at=device.last_upload_at,
        creation_time=device.created_at,
    )


# --------------------------------------------------------------------- departments


def _get_department(db: Session, department_id: uuid.UUID) -> Department:
    department = db.get(Department, department_id)
    if department is None:
        raise not_visible("Department not found.")
    return department


def create_department(
    db: Session, payload: DepartmentCreate, actor: User, ctx: AuditContext
) -> DepartmentView:
    if not actor.is_super_admin:
        raise AppError(403, ErrorCode.FORBIDDEN, "Super administrator permission is required.")
    department = Department(code=payload.code, name=payload.name, location=payload.location)
    db.add(department)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            409, "department_code_taken", "That department code is already in use."
        ) from exc
    record_audit(
        db,
        action="department.created",
        actor_type=AuditActorType.USER,
        actor_user_id=actor.id,
        department_id=department.id,
        target_type="department",
        target_id=department.id,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        request_id=ctx.request_id,
        metadata={"code": department.code},
    )
    db.commit()
    db.refresh(department)
    return _department_view(department)


def list_departments(db: Session, actor: User) -> list[DepartmentView]:
    if not actor.is_super_admin:
        raise AppError(403, ErrorCode.FORBIDDEN, "Super administrator permission is required.")
    departments = db.scalars(select(Department).order_by(Department.code)).all()
    return [_department_view(department) for department in departments]


def get_department(
    db: Session, department_id: uuid.UUID, actor: User, memberships: list[MembershipContext]
) -> DepartmentView:
    department = _get_department(db, department_id)
    if not can_read_department(actor, memberships, department.id):
        raise not_visible("Department not found.")
    return _department_view(department)


def update_department(
    db: Session,
    department_id: uuid.UUID,
    payload: DepartmentUpdate,
    actor: User,
    ctx: AuditContext,
) -> DepartmentView:
    if not actor.is_super_admin:
        raise AppError(403, ErrorCode.FORBIDDEN, "Super administrator permission is required.")
    department = _get_department(db, department_id)
    before = {
        "name": department.name,
        "location": department.location,
        "is_active": department.is_active,
    }
    if payload.name is not None:
        department.name = payload.name
    if payload.location is not None:
        department.location = payload.location
    if payload.is_active is not None:
        if not payload.is_active:
            active_devices = db.scalar(
                select(func.count())
                .select_from(DeviceAssignment)
                .where(
                    DeviceAssignment.department_id == department.id,
                    DeviceAssignment.effective_to.is_(None),
                )
            )
            if active_devices:
                raise AppError(
                    409,
                    "department_has_active_devices",
                    "Reassign active devices before deactivating this department.",
                )
        department.is_active = payload.is_active
    record_audit(
        db,
        action="department.updated",
        actor_type=AuditActorType.USER,
        actor_user_id=actor.id,
        department_id=department.id,
        target_type="department",
        target_id=department.id,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        request_id=ctx.request_id,
        metadata={
            "before": before,
            "after": {
                "name": department.name,
                "location": department.location,
                "is_active": department.is_active,
            },
        },
    )
    db.commit()
    db.refresh(department)
    return _department_view(department)


# --------------------------------------------------------------------------- users


def create_user(
    db: Session,
    payload: UserCreate,
    actor: User,
    memberships: list[MembershipContext],
    ctx: AuditContext,
) -> UserView:
    department = _get_department(db, payload.department_id)
    if not department.is_active:
        raise AppError(422, ErrorCode.VALIDATION_ERROR, "The department is inactive.")
    if payload.is_super_admin and not actor.is_super_admin:
        raise AppError(403, ErrorCode.FORBIDDEN, "Only a super administrator can grant that role.")
    if not actor.is_super_admin:
        require_department_admin(actor, memberships, department.id)

    if db.scalar(select(User.id).where(func.lower(User.email) == payload.email.lower())):
        raise AppError(409, "email_taken", "That email address is already registered.")

    user = User(
        email=payload.email.strip(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        is_super_admin=payload.is_super_admin,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "email_taken", "That email address is already registered.") from exc

    db.add(Membership(user_id=user.id, department_id=department.id, role=payload.role))
    record_audit(
        db,
        action="user.created",
        actor_type=AuditActorType.USER,
        actor_user_id=actor.id,
        department_id=department.id,
        target_type="user",
        target_id=user.id,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        request_id=ctx.request_id,
        metadata={"role": payload.role.value, "is_super_admin": payload.is_super_admin},
    )
    db.commit()
    db.refresh(user)
    return user_view(db, user)


def list_users(
    db: Session, actor: User, memberships: list[MembershipContext], *, page: int, page_size: int
) -> tuple[list[UserView], int]:
    statement = select(User)
    count_statement = select(func.count()).select_from(User)
    if not actor.is_super_admin:
        administered = [
            context.department.id
            for context in memberships
            if context.role is MembershipRole.DEPARTMENT_ADMIN
        ]
        if not administered:
            raise AppError(
                403, ErrorCode.FORBIDDEN, "Department administrator permission is required."
            )
        allowed_ids = [context.department.id for context in memberships]
        statement = statement.join(Membership).where(
            Membership.department_id.in_(allowed_ids), Membership.is_active.is_(True)
        )
        count_statement = count_statement.join(Membership).where(
            Membership.department_id.in_(allowed_ids), Membership.is_active.is_(True)
        )
        del administered
    total = db.scalar(count_statement) or 0
    rows = db.scalars(
        statement.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).unique()
    return [user_view(db, user) for user in rows], total


def get_user(
    db: Session, user_id: uuid.UUID, actor: User, memberships: list[MembershipContext]
) -> UserView:
    user = db.get(User, user_id)
    if user is None:
        raise not_visible("User not found.")
    if actor.is_super_admin:
        return user_view(db, user)
    visible_departments = {context.department.id for context in memberships}
    user_departments = {membership.department_id for membership in _membership_views(db, user.id)}
    if not visible_departments.intersection(user_departments):
        raise not_visible("User not found.")
    return user_view(db, user)


def update_user(
    db: Session,
    user_id: uuid.UUID,
    payload: UserUpdate,
    actor: User,
    ctx: AuditContext,
) -> UserView:
    if not actor.is_super_admin:
        raise AppError(403, ErrorCode.FORBIDDEN, "Super administrator permission is required.")
    user = db.get(User, user_id)
    if user is None:
        raise not_visible("User not found.")
    before = {
        "full_name": user.full_name,
        "is_active": user.is_active,
        "is_super_admin": user.is_super_admin,
    }
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.is_super_admin is not None:
        user.is_super_admin = payload.is_super_admin
    if payload.is_active is not None:
        user.is_active = payload.is_active
        if not payload.is_active:
            revoke_all_user_sessions(db, user.id)
    record_audit(
        db,
        action="user.updated",
        actor_type=AuditActorType.USER,
        actor_user_id=actor.id,
        target_type="user",
        target_id=user.id,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        request_id=ctx.request_id,
        metadata={
            "before": before,
            "after": {
                "full_name": user.full_name,
                "is_active": user.is_active,
                "is_super_admin": user.is_super_admin,
            },
        },
    )
    db.commit()
    db.refresh(user)
    return user_view(db, user)


def add_membership(
    db: Session,
    user_id: uuid.UUID,
    payload: MembershipCreate,
    actor: User,
    memberships: list[MembershipContext],
    ctx: AuditContext,
) -> UserView:
    user = db.get(User, user_id)
    if user is None:
        raise not_visible("User not found.")
    department = _get_department(db, payload.department_id)
    if not department.is_active:
        raise AppError(422, ErrorCode.VALIDATION_ERROR, "The department is inactive.")
    if not can_manage_department(actor, memberships, department.id):
        raise AppError(403, ErrorCode.FORBIDDEN, "Department administrator permission is required.")

    existing = db.scalar(
        select(Membership).where(
            Membership.user_id == user.id, Membership.department_id == department.id
        )
    )
    if existing is not None:
        raise AppError(409, "membership_exists", "This user already belongs to that department.")
    db.add(Membership(user_id=user.id, department_id=department.id, role=payload.role))
    record_audit(
        db,
        action="membership.created",
        actor_type=AuditActorType.USER,
        actor_user_id=actor.id,
        department_id=department.id,
        target_type="user",
        target_id=user.id,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        request_id=ctx.request_id,
        metadata={"role": payload.role.value},
    )
    db.commit()
    return user_view(db, user)


def update_membership(
    db: Session,
    membership_id: uuid.UUID,
    payload: MembershipUpdate,
    actor: User,
    memberships: list[MembershipContext],
    ctx: AuditContext,
) -> UserView:
    membership = db.get(Membership, membership_id)
    if membership is None:
        raise not_visible("Membership not found.")
    if not can_manage_department(actor, memberships, membership.department_id):
        raise AppError(403, ErrorCode.FORBIDDEN, "Department administrator permission is required.")
    before = {"role": membership.role.value, "is_active": membership.is_active}
    if payload.role is not None:
        membership.role = payload.role
    if payload.is_active is not None:
        membership.is_active = payload.is_active
    record_audit(
        db,
        action="membership.updated",
        actor_type=AuditActorType.USER,
        actor_user_id=actor.id,
        department_id=membership.department_id,
        target_type="membership",
        target_id=membership.id,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        request_id=ctx.request_id,
        metadata={
            "before": before,
            "after": {"role": membership.role.value, "is_active": membership.is_active},
        },
    )
    db.commit()
    user = db.get(User, membership.user_id)
    assert user is not None
    return user_view(db, user)


# ------------------------------------------------------------------------- devices


def register_device(
    db: Session, payload: DeviceCreate, actor: User, ctx: AuditContext
) -> DeviceView:
    if not actor.is_super_admin:
        raise AppError(403, ErrorCode.FORBIDDEN, "Super administrator permission is required.")
    department = _get_department(db, payload.department_id)
    if not department.is_active:
        raise AppError(422, ErrorCode.VALIDATION_ERROR, "The department is inactive.")

    device = Device(
        device_uid=payload.device_uid,
        serial_number=payload.serial_number,
        friendly_name=payload.friendly_name,
        model=payload.model,
        hardware_revision=payload.hardware_revision,
        firmware_version=payload.firmware_version,
        installation_location=payload.installation_location,
        status=DeviceStatus.ACTIVE if payload.activate else DeviceStatus.PROVISIONED,
        provisioned_at=utcnow(),
        activated_at=utcnow() if payload.activate else None,
    )
    db.add(device)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            409, "device_exists", "That device identifier is already registered."
        ) from exc

    db.add(
        DeviceAssignment(
            device_id=device.id,
            department_id=department.id,
            assigned_by_user_id=actor.id,
        )
    )
    record_audit(
        db,
        action="device.registered",
        actor_type=AuditActorType.USER,
        actor_user_id=actor.id,
        department_id=department.id,
        target_type="device",
        target_id=device.id,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        request_id=ctx.request_id,
        metadata={"device_uid": device.device_uid, "status": device.status.value},
    )
    db.commit()
    db.refresh(device)
    return _device_view(db, device)


def list_devices(
    db: Session,
    actor: User,
    memberships: list[MembershipContext],
    department_id: uuid.UUID | None,
) -> list[DeviceView]:
    statement = (
        select(Device)
        .join(DeviceAssignment, DeviceAssignment.device_id == Device.id)
        .where(DeviceAssignment.effective_to.is_(None))
    )
    if actor.is_super_admin:
        if department_id is not None:
            statement = statement.where(DeviceAssignment.department_id == department_id)
    else:
        if not any(context.role is MembershipRole.DEPARTMENT_ADMIN for context in memberships):
            raise AppError(
                403, ErrorCode.FORBIDDEN, "Department administrator permission is required."
            )
        if department_id is None:
            department_id = memberships[0].department.id if len(memberships) == 1 else None
        if department_id is None:
            raise AppError(400, ErrorCode.DEPARTMENT_REQUIRED, "department_id is required.")
        if not can_read_department(actor, memberships, department_id):
            raise not_visible("Department not found.")
        statement = statement.where(DeviceAssignment.department_id == department_id)
    devices = db.scalars(statement.order_by(Device.device_uid)).all()
    return [_device_view(db, device) for device in devices]


def get_device(
    db: Session, device_id: uuid.UUID, actor: User, memberships: list[MembershipContext]
) -> DeviceView:
    device = db.get(Device, device_id)
    if device is None:
        raise not_visible("Device not found.")
    assignment = _active_assignment(db, device.id)
    if not actor.is_super_admin:
        is_department_admin = any(
            context.role is MembershipRole.DEPARTMENT_ADMIN for context in memberships
        )
        if (
            not is_department_admin
            or assignment is None
            or not can_read_department(actor, memberships, assignment.department_id)
        ):
            raise not_visible("Device not found.")
    return _device_view(db, device)


def update_device(
    db: Session, device_id: uuid.UUID, payload: DeviceUpdate, actor: User, ctx: AuditContext
) -> DeviceView:
    if not actor.is_super_admin:
        raise AppError(403, ErrorCode.FORBIDDEN, "Super administrator permission is required.")
    device = db.get(Device, device_id)
    if device is None:
        raise not_visible("Device not found.")
    before = {"status": device.status.value, "firmware_version": device.firmware_version}
    for field in ("friendly_name", "model", "firmware_version", "installation_location"):
        value = getattr(payload, field)
        if value is not None:
            setattr(device, field, value)
    if payload.status is not None:
        device.status = payload.status
        if payload.status is DeviceStatus.ACTIVE and device.activated_at is None:
            device.activated_at = utcnow()
    record_audit(
        db,
        action="device.updated",
        actor_type=AuditActorType.USER,
        actor_user_id=actor.id,
        target_type="device",
        target_id=device.id,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        request_id=ctx.request_id,
        metadata={
            "before": before,
            "after": {"status": device.status.value, "firmware_version": device.firmware_version},
        },
    )
    db.commit()
    db.refresh(device)
    return _device_view(db, device)


def list_assignments(
    db: Session, device_id: uuid.UUID, actor: User, memberships: list[MembershipContext]
) -> list[AssignmentView]:
    get_device(db, device_id, actor, memberships)
    rows = db.execute(
        select(DeviceAssignment, Department)
        .join(Department, Department.id == DeviceAssignment.department_id)
        .where(DeviceAssignment.device_id == device_id)
        .order_by(DeviceAssignment.effective_from.desc())
    ).all()
    return [
        AssignmentView(
            id=assignment.id,
            device_id=assignment.device_id,
            department_id=department.id,
            department_code=department.code,
            effective_from=assignment.effective_from,
            effective_to=assignment.effective_to,
            assigned_by_user_id=assignment.assigned_by_user_id,
            reason=assignment.reason,
        )
        for assignment, department in rows
    ]


def assign_device(
    db: Session,
    device_id: uuid.UUID,
    payload: AssignmentCreate,
    actor: User,
    ctx: AuditContext,
) -> AssignmentView:
    if not actor.is_super_admin:
        raise AppError(403, ErrorCode.FORBIDDEN, "Super administrator permission is required.")
    device = db.get(Device, device_id)
    if device is None:
        raise not_visible("Device not found.")
    department = _get_department(db, payload.department_id)
    if not department.is_active:
        raise AppError(422, ErrorCode.VALIDATION_ERROR, "The department is inactive.")

    now = utcnow()
    previous = _active_assignment(db, device.id)
    previous_department_id = previous.department_id if previous else None

    # Close the prior assignment before creating its replacement.  The explicit
    # flush is deliberate: PostgreSQL's partial unique index permits only one
    # active row, and SQLAlchemy otherwise may schedule the INSERT before this
    # UPDATE.  Retaining the closed row is the device-assignment audit history.
    if previous is not None:
        # ``effective_from`` can be database-generated and slightly ahead of
        # the application clock.  The period constraint is strictly greater,
        # so keep both ends monotonic even when those clocks differ.
        now = max(now, previous.effective_from + timedelta(microseconds=1))
        previous.effective_to = now
        db.flush()

    assignment = DeviceAssignment(
        device_id=device.id,
        department_id=department.id,
        effective_from=now,
        assigned_by_user_id=actor.id,
        reason=payload.reason,
    )
    db.add(assignment)
    record_audit(
        db,
        action="device.reassigned" if previous else "device.assigned",
        actor_type=AuditActorType.USER,
        actor_user_id=actor.id,
        department_id=department.id,
        target_type="device",
        target_id=device.id,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        request_id=ctx.request_id,
        metadata={
            "previous_department_id": str(previous_department_id)
            if previous_department_id
            else None,
            "new_department_id": str(department.id),
            "reason": payload.reason,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            409, "assignment_conflict", "The device assignment changed concurrently."
        ) from exc
    db.refresh(assignment)
    return AssignmentView(
        id=assignment.id,
        device_id=assignment.device_id,
        department_id=department.id,
        department_code=department.code,
        effective_from=assignment.effective_from,
        effective_to=assignment.effective_to,
        assigned_by_user_id=assignment.assigned_by_user_id,
        reason=assignment.reason,
    )


# --------------------------------------------------------------------- credentials


def _next_version(db: Session, device_id: uuid.UUID) -> int:
    current = db.scalar(
        select(func.max(DeviceCredential.version)).where(DeviceCredential.device_id == device_id)
    )
    return (current or 0) + 1


def _active_credential(db: Session, device_id: uuid.UUID) -> DeviceCredential | None:
    return db.scalar(
        select(DeviceCredential).where(
            DeviceCredential.device_id == device_id,
            DeviceCredential.revoked_at.is_(None),
        )
    )


def _issue(db: Session, device: Device, actor: User, ctx: AuditContext) -> CredentialIssued:
    secret = generate_device_secret()
    credential = DeviceCredential(
        device_id=device.id,
        client_id=generate_client_id(),
        secret_hash=hash_password(secret),
        version=_next_version(db, device.id),
        created_by_user_id=actor.id,
    )
    db.add(credential)
    record_audit(
        db,
        action="device.credential_issued",
        actor_type=AuditActorType.USER,
        actor_user_id=actor.id,
        target_type="device",
        target_id=device.id,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        request_id=ctx.request_id,
        metadata={"version": credential.version, "client_id": credential.client_id},
    )
    db.commit()
    db.refresh(credential)
    return CredentialIssued(
        id=credential.id,
        client_id=credential.client_id,
        client_secret=secret,
        version=credential.version,
        expires_at=credential.expires_at,
    )


def issue_credential(
    db: Session, device_id: uuid.UUID, actor: User, ctx: AuditContext
) -> CredentialIssued:
    if not actor.is_super_admin:
        raise AppError(403, ErrorCode.FORBIDDEN, "Super administrator permission is required.")
    device = db.get(Device, device_id)
    if device is None:
        raise not_visible("Device not found.")
    if _active_credential(db, device.id) is not None:
        raise AppError(409, "credential_exists", "This device already has an active credential.")
    return _issue(db, device, actor, ctx)


def rotate_credential(
    db: Session, device_id: uuid.UUID, actor: User, ctx: AuditContext
) -> CredentialIssued:
    if not actor.is_super_admin:
        raise AppError(403, ErrorCode.FORBIDDEN, "Super administrator permission is required.")
    device = db.get(Device, device_id)
    if device is None:
        raise not_visible("Device not found.")
    active = _active_credential(db, device.id)
    if active is None:
        raise AppError(409, "no_active_credential", "Issue a credential before rotating one.")
    active.revoked_at = utcnow()
    active.revoked_reason = "rotated"
    record_audit(
        db,
        action="device.credential_rotated",
        actor_type=AuditActorType.USER,
        actor_user_id=actor.id,
        target_type="device",
        target_id=device.id,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        request_id=ctx.request_id,
        metadata={"revoked_version": active.version},
    )
    return _issue(db, device, actor, ctx)


def revoke_credential(
    db: Session,
    device_id: uuid.UUID,
    credential_id: uuid.UUID,
    actor: User,
    ctx: AuditContext,
    reason: str | None = None,
) -> CredentialView:
    if not actor.is_super_admin:
        raise AppError(403, ErrorCode.FORBIDDEN, "Super administrator permission is required.")
    credential = db.get(DeviceCredential, credential_id)
    if credential is None or credential.device_id != device_id:
        raise not_visible("Credential not found.")
    if credential.revoked_at is None:
        credential.revoked_at = utcnow()
        credential.revoked_reason = (reason or "revoked")[:120]
        record_audit(
            db,
            action="device.credential_revoked",
            actor_type=AuditActorType.USER,
            actor_user_id=actor.id,
            target_type="device",
            target_id=device_id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            request_id=ctx.request_id,
            metadata={"version": credential.version, "reason": credential.revoked_reason},
        )
        db.commit()
    return CredentialView(
        id=credential.id,
        client_id=credential.client_id,
        version=credential.version,
        created_at=credential.created_at,
        expires_at=credential.expires_at,
        revoked_at=credential.revoked_at,
        revoked_reason=credential.revoked_reason,
    )
