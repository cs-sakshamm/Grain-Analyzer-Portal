"""IoT device registry, credentials and department assignment history."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import DeviceStatus
from app.models.types import pg_enum


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_uid: Mapped[str] = mapped_column(String(64), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(128), nullable=False)
    friendly_name: Mapped[str | None] = mapped_column(String(200))
    model: Mapped[str | None] = mapped_column(String(120))
    hardware_revision: Mapped[str | None] = mapped_column(String(64))
    firmware_version: Mapped[str | None] = mapped_column(String(64))
    installation_location: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[DeviceStatus] = mapped_column(
        pg_enum(DeviceStatus, "device_status"),
        nullable=False,
        default=DeviceStatus.PROVISIONED,
        server_default=text("'provisioned'"),
    )
    provisioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_upload_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    credentials: Mapped[list[DeviceCredential]] = relationship(
        back_populates="device", cascade="all, delete-orphan", lazy="selectin"
    )
    assignments: Mapped[list[DeviceAssignment]] = relationship(
        back_populates="device", cascade="all, delete-orphan", lazy="select"
    )

    __table_args__ = (
        Index("uq_devices_device_uid", "device_uid", unique=True),
        Index("uq_devices_serial_number", "serial_number", unique=True),
        Index("idx_devices_status", "status"),
        Index("idx_devices_last_seen", text("last_seen_at DESC")),
    )


class DeviceCredential(Base):
    __tablename__ = "device_credentials"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False
    )
    client_id: Mapped[str] = mapped_column(String(64), nullable=False)
    secret_hash: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(120))

    device: Mapped[Device] = relationship(back_populates="credentials")

    __table_args__ = (
        Index("uq_device_credentials_client_id", "client_id", unique=True),
        Index("uq_device_credentials_device_version", "device_id", "version", unique=True),
        Index(
            "uq_device_credentials_active",
            "device_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("idx_device_credentials_device", "device_id", text("created_at DESC")),
        CheckConstraint("version > 0", name="ck_device_credentials_version_positive"),
    )


class DeviceAssignment(Base):
    __tablename__ = "device_assignments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    device: Mapped[Device] = relationship(back_populates="assignments")

    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_device_assignments_period",
        ),
        Index(
            "uq_device_assignments_active",
            "device_id",
            unique=True,
            postgresql_where=text("effective_to IS NULL"),
        ),
        Index("idx_device_assignments_device", "device_id", text("effective_from DESC")),
        Index(
            "idx_device_assignments_department",
            "department_id",
            text("effective_from DESC"),
        ),
    )
