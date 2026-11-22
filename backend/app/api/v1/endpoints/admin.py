"""Administration endpoints for departments, users, devices and credentials."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, request_id, require_portal_user
from app.db.session import get_db
from app.schemas.admin import (
    AssignmentCreate,
    AssignmentView,
    CredentialIssued,
    CredentialStatusUpdate,
    CredentialView,
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentView,
    DeviceCreate,
    DeviceUpdate,
    DeviceView,
    MembershipCreate,
    MembershipUpdate,
    UserCreate,
    UserUpdate,
    UserView,
)
from app.services import admin_service
from app.services.admin_service import AuditContext

router = APIRouter(prefix="/admin", tags=["admin"])


def _audit(request: Request, principal: CurrentUser) -> AuditContext:
    return AuditContext(
        user_id=principal.user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=request_id(request),
    )


# --------------------------------------------------------------------- departments


@router.post(
    "/departments",
    response_model=DepartmentView,
    status_code=status.HTTP_201_CREATED,
)
def create_department(
    payload: DepartmentCreate,
    request: Request,
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> DepartmentView:
    return admin_service.create_department(db, payload, principal.user, _audit(request, principal))


@router.get("/departments", response_model=list[DepartmentView])
def list_departments(
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> list[DepartmentView]:
    return admin_service.list_departments(db, principal.user)


@router.get("/departments/{department_id}", response_model=DepartmentView)
def get_department(
    department_id: uuid.UUID,
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> DepartmentView:
    return admin_service.get_department(db, department_id, principal.user, principal.memberships)


@router.patch("/departments/{department_id}", response_model=DepartmentView)
def update_department(
    department_id: uuid.UUID,
    payload: DepartmentUpdate,
    request: Request,
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> DepartmentView:
    return admin_service.update_department(
        db, department_id, payload, principal.user, _audit(request, principal)
    )


# --------------------------------------------------------------------------- users


@router.post("/users", response_model=UserView, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> UserView:
    return admin_service.create_user(
        db, payload, principal.user, principal.memberships, _audit(request, principal)
    )


@router.get("/users")
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> dict:
    items, total = admin_service.list_users(
        db, principal.user, principal.memberships, page=page, page_size=page_size
    )
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.get("/users/{user_id}", response_model=UserView)
def get_user(
    user_id: uuid.UUID,
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> UserView:
    return admin_service.get_user(db, user_id, principal.user, principal.memberships)


@router.patch("/users/{user_id}", response_model=UserView)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    request: Request,
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> UserView:
    return admin_service.update_user(
        db, user_id, payload, principal.user, _audit(request, principal)
    )


@router.post(
    "/users/{user_id}/memberships",
    response_model=UserView,
    status_code=status.HTTP_201_CREATED,
)
def add_membership(
    user_id: uuid.UUID,
    payload: MembershipCreate,
    request: Request,
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> UserView:
    return admin_service.add_membership(
        db, user_id, payload, principal.user, principal.memberships, _audit(request, principal)
    )


@router.patch("/memberships/{membership_id}", response_model=UserView)
def update_membership(
    membership_id: uuid.UUID,
    payload: MembershipUpdate,
    request: Request,
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> UserView:
    return admin_service.update_membership(
        db,
        membership_id,
        payload,
        principal.user,
        principal.memberships,
        _audit(request, principal),
    )


# ------------------------------------------------------------------------- devices


@router.post("/devices", response_model=DeviceView, status_code=status.HTTP_201_CREATED)
def register_device(
    payload: DeviceCreate,
    request: Request,
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> DeviceView:
    return admin_service.register_device(db, payload, principal.user, _audit(request, principal))


@router.get("/devices", response_model=list[DeviceView])
def list_devices(
    department_id: uuid.UUID | None = Query(default=None),
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> list[DeviceView]:
    return admin_service.list_devices(db, principal.user, principal.memberships, department_id)


@router.get("/devices/{device_id}", response_model=DeviceView)
def get_device(
    device_id: uuid.UUID,
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> DeviceView:
    return admin_service.get_device(db, device_id, principal.user, principal.memberships)


@router.patch("/devices/{device_id}", response_model=DeviceView)
def update_device(
    device_id: uuid.UUID,
    payload: DeviceUpdate,
    request: Request,
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> DeviceView:
    return admin_service.update_device(
        db, device_id, payload, principal.user, _audit(request, principal)
    )


@router.get("/devices/{device_id}/assignments", response_model=list[AssignmentView])
def list_assignments(
    device_id: uuid.UUID,
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> list[AssignmentView]:
    return admin_service.list_assignments(db, device_id, principal.user, principal.memberships)


@router.post(
    "/devices/{device_id}/assignments",
    response_model=AssignmentView,
    status_code=status.HTTP_201_CREATED,
)
def assign_device(
    device_id: uuid.UUID,
    payload: AssignmentCreate,
    request: Request,
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> AssignmentView:
    return admin_service.assign_device(
        db, device_id, payload, principal.user, _audit(request, principal)
    )


@router.post(
    "/devices/{device_id}/credentials",
    response_model=CredentialIssued,
    status_code=status.HTTP_201_CREATED,
)
def issue_credential(
    device_id: uuid.UUID,
    request: Request,
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> CredentialIssued:
    return admin_service.issue_credential(db, device_id, principal.user, _audit(request, principal))


@router.post("/devices/{device_id}/credentials/rotate", response_model=CredentialIssued)
def rotate_credential(
    device_id: uuid.UUID,
    request: Request,
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> CredentialIssued:
    return admin_service.rotate_credential(
        db, device_id, principal.user, _audit(request, principal)
    )


@router.post(
    "/devices/{device_id}/credentials/{credential_id}/revoke",
    response_model=CredentialView,
)
def revoke_credential(
    device_id: uuid.UUID,
    credential_id: uuid.UUID,
    request: Request,
    payload: CredentialStatusUpdate | None = None,
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> CredentialView:
    return admin_service.revoke_credential(
        db,
        device_id,
        credential_id,
        principal.user,
        _audit(request, principal),
        reason=payload.reason if payload else None,
    )
