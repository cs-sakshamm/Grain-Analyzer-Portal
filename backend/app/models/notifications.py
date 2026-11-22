"""In-portal notifications with per-user delivery state."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import NotificationEventType, NotificationSeverity
from app.models.types import pg_enum


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    department_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False
    )
    scan_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scans.id", ondelete="SET NULL")
    )
    event_type: Mapped[NotificationEventType] = mapped_column(
        pg_enum(NotificationEventType, "notification_event_type"), nullable=False
    )
    event_key: Mapped[str] = mapped_column(String(160), nullable=False)
    severity: Mapped[NotificationSeverity] = mapped_column(
        pg_enum(NotificationSeverity, "notification_severity"),
        nullable=False,
        default=NotificationSeverity.INFO,
        server_default=text("'info'"),
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("uq_notifications_event_key", "event_key", unique=True),
        Index("idx_notifications_department", "department_id", text("created_at DESC")),
        Index("idx_notifications_scan", "scan_id"),
    )


class NotificationRecipient(Base):
    __tablename__ = "notification_recipients"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "uq_notification_recipients_notification_user",
            "notification_id",
            "user_id",
            unique=True,
        ),
        Index(
            "idx_notification_recipients_unread",
            "user_id",
            text("created_at DESC"),
            postgresql_where=text("read_at IS NULL"),
        ),
    )
