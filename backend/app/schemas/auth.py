"""Authentication schemas (contract §2)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MembershipRole

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class MembershipView(BaseModel):
    department_id: uuid.UUID
    department_code: str
    department_name: str
    role: MembershipRole


class UserView(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    is_super_admin: bool
    memberships: list[MembershipView]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserView


class MeResponse(BaseModel):
    user: UserView
