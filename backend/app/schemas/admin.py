"""Administration schemas (contract §5)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DeviceStatus, MembershipRole

CODE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{1,31}$"


class DepartmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=32, pattern=CODE_PATTERN)
    name: str = Field(min_length=2, max_length=200)
    location: str | None = Field(default=None, max_length=255)


class DepartmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=200)
    location: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class DepartmentView(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    location: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class MembershipView(BaseModel):
    id: uuid.UUID
    department_id: uuid.UUID
    department_code: str
    department_name: str
    role: MembershipRole
    is_active: bool


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=12, max_length=256)
    full_name: str | None = Field(default=None, max_length=200)
    department_id: uuid.UUID
    role: MembershipRole = MembershipRole.DEPARTMENT_USER
    is_super_admin: bool = False


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None
    is_super_admin: bool | None = None


class UserView(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    is_super_admin: bool
    last_login_at: datetime | None
    memberships: list[MembershipView]


class MembershipCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_id: uuid.UUID
    role: MembershipRole = MembershipRole.DEPARTMENT_USER


class MembershipUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: MembershipRole | None = None
    is_active: bool | None = None


class DeviceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_uid: str = Field(min_length=2, max_length=64)
    serial_number: str = Field(min_length=2, max_length=128)
    friendly_name: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=120)
    hardware_revision: str | None = Field(default=None, max_length=64)
    firmware_version: str | None = Field(default=None, max_length=64)
    installation_location: str | None = Field(default=None, max_length=255)
    department_id: uuid.UUID
    activate: bool = True


class DeviceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    friendly_name: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=120)
    firmware_version: str | None = Field(default=None, max_length=64)
    installation_location: str | None = Field(default=None, max_length=255)
    status: DeviceStatus | None = None


class AssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=1000)


class AssignmentView(BaseModel):
    id: uuid.UUID
    device_id: uuid.UUID
    department_id: uuid.UUID
    department_code: str
    effective_from: datetime
    effective_to: datetime | None
    assigned_by_user_id: uuid.UUID | None
    reason: str | None


class DeviceView(BaseModel):
    id: uuid.UUID
    device_uid: str
    serial_number: str
    friendly_name: str | None
    model: str | None
    firmware_version: str | None
    installation_location: str | None
    status: DeviceStatus
    active_department_id: uuid.UUID | None
    last_seen_at: datetime | None
    last_upload_at: datetime | None
    creation_time: datetime


class CredentialIssued(BaseModel):
    id: uuid.UUID
    client_id: str
    client_secret: str
    version: int
    expires_at: datetime | None


class CredentialView(BaseModel):
    id: uuid.UUID
    client_id: str
    version: int
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    revoked_reason: str | None


class CredentialStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=120)


class PaginatedUsers(BaseModel):
    items: list[UserView]
    page: int
    page_size: int
    total: int
