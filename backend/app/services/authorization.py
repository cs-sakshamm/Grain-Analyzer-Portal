"""Department scope resolution and role checks.

Every service that touches a department-scoped row calls through here; routes never
compute scope themselves. Cross-department access by a non-member is reported as 404 so
existence is not disclosed.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.models.enums import MembershipRole
from app.models.identity import User
from app.models.organization import Department
from app.services.auth_service import MembershipContext


def department_required() -> AppError:
    return AppError(
        status_code=400,
        code=ErrorCode.DEPARTMENT_REQUIRED,
        message="department_id is required for this account.",
    )


def not_visible(message: str = "The requested resource was not found.") -> AppError:
    return AppError(status_code=404, code=ErrorCode.NOT_FOUND, message=message)


def resolve_department_id(
    db: Session,
    *,
    user: User,
    memberships: list[MembershipContext],
    requested_department_id: uuid.UUID | None,
) -> uuid.UUID:
    """Resolve the single department a request operates on.

    Super admins must name the department they are acting for (the read is audited by
    the caller). Other users may omit it only when they belong to exactly one.
    """

    if user.is_super_admin:
        if requested_department_id is None:
            raise department_required()
        department = db.get(Department, requested_department_id)
        if department is None:
            raise not_visible("Department not found.")
        return department.id

    allowed = {context.department.id: context for context in memberships}
    if requested_department_id is not None:
        if requested_department_id not in allowed:
            raise not_visible("Department not found.")
        return requested_department_id

    if len(allowed) == 1:
        return next(iter(allowed))
    if not allowed:
        raise AppError(
            status_code=403,
            code=ErrorCode.FORBIDDEN,
            message="This account has no active department membership.",
        )
    raise department_required()


def role_in_department(
    memberships: list[MembershipContext], department_id: uuid.UUID
) -> MembershipRole | None:
    for context in memberships:
        if context.department.id == department_id:
            return context.role
    return None


def require_department_admin(
    user: User, memberships: list[MembershipContext], department_id: uuid.UUID
) -> None:
    if user.is_super_admin:
        return
    if role_in_department(memberships, department_id) is not MembershipRole.DEPARTMENT_ADMIN:
        raise AppError(
            status_code=403,
            code=ErrorCode.FORBIDDEN,
            message="Department administrator permission is required.",
        )


def can_manage_department(
    user: User, memberships: list[MembershipContext], department_id: uuid.UUID
) -> bool:
    """Interim DR-019 policy: super admin anywhere, department admin in own department."""

    if user.is_super_admin:
        return True
    return role_in_department(memberships, department_id) is MembershipRole.DEPARTMENT_ADMIN


def can_read_department(
    user: User, memberships: list[MembershipContext], department_id: uuid.UUID
) -> bool:
    if user.is_super_admin:
        return True
    return role_in_department(memberships, department_id) is not None
