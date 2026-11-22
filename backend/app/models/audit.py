"""Append-only audit trail for administrative and security-sensitive actions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import AuditActorType
from app.models.types import pg_enum


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor_type: Mapped[AuditActorType] = mapped_column(
        pg_enum(AuditActorType, "audit_actor_type"), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_device_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL")
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(64))
    # ``metadata`` is reserved on the declarative class, so the attribute is named
    # ``meta`` while the physical column keeps the documented name.
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    __table_args__ = (
        CheckConstraint(
            "actor_type <> 'user' OR actor_user_id IS NOT NULL",
            name="ck_audit_logs_user_actor",
        ),
        CheckConstraint(
            "actor_type <> 'device' OR actor_device_id IS NOT NULL",
            name="ck_audit_logs_device_actor",
        ),
        Index("idx_audit_logs_occurred", text("occurred_at DESC")),
        Index("idx_audit_logs_department", "department_id", text("occurred_at DESC")),
        Index("idx_audit_logs_actor", "actor_user_id", text("occurred_at DESC")),
        Index("idx_audit_logs_target", "target_type", "target_id"),
    )
