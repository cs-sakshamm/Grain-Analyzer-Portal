"""Private attachment metadata and upload diagnostics."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ScanFileRole, UploadStatus
from app.models.types import pg_enum


class ScanFile(Base):
    __tablename__ = "scan_files"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[ScanFileRole] = mapped_column(
        pg_enum(ScanFileRole, "scan_file_role"), nullable=False
    )
    storage_backend: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width_px: Mapped[int | None] = mapped_column(Integer)
    height_px: Mapped[int | None] = mapped_column(Integer)
    upload_status: Mapped[UploadStatus] = mapped_column(
        pg_enum(UploadStatus, "upload_status"),
        nullable=False,
        default=UploadStatus.PENDING,
        server_default=text("'pending'"),
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("uq_scan_files_storage_key", "storage_key", unique=True),
        Index(
            "uq_scan_files_fixed_role",
            "scan_id",
            "role",
            unique=True,
            postgresql_where=text("role <> 'other'"),
        ),
        Index("idx_scan_files_scan", "scan_id"),
        Index(
            "idx_scan_files_status",
            "upload_status",
            postgresql_where=text("upload_status <> 'verified'"),
        ),
        CheckConstraint("size_bytes > 0", name="ck_scan_files_size_positive"),
        CheckConstraint(
            "upload_status <> 'verified' OR verified_at IS NOT NULL",
            name="ck_scan_files_verified_has_timestamp",
        ),
    )


class UploadAttempt(Base):
    __tablename__ = "upload_attempts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )
    scan_file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scan_files.id", ondelete="SET NULL")
    )
    role: Mapped[ScanFileRole] = mapped_column(
        pg_enum(ScanFileRole, "scan_file_role"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    diagnostic_code: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("stage IN ('prepare','upload','verify')", name="ck_upload_attempts_stage"),
        CheckConstraint(
            "status IN ('started','succeeded','failed')", name="ck_upload_attempts_status"
        ),
        Index("idx_upload_attempts_scan", "scan_id", text("created_at DESC")),
    )
