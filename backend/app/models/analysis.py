"""Analysis aggregates: batches, scans, measurements, evaluations and age."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    AgeValidationStatus,
    MeasurementBasis,
    QualityVerdict,
    ScanProcessingStatus,
)
from app.models.types import pg_enum

if TYPE_CHECKING:  # avoids a circular import at module load time
    from app.models.files import ScanFile


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    department_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False
    )
    batch_code: Mapped[str] = mapped_column(String(64), nullable=False)
    lot_code: Mapped[str | None] = mapped_column(String(64))
    variety: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "uq_batches_dept_code_lot_null",
            "department_id",
            "batch_code",
            unique=True,
            postgresql_where=text("lot_code IS NULL"),
        ),
        Index(
            "uq_batches_dept_code_lot",
            "department_id",
            "batch_code",
            "lot_code",
            unique=True,
            postgresql_where=text("lot_code IS NOT NULL"),
        ),
        Index("idx_batches_department", "department_id", "batch_code"),
    )


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False
    )
    client_scan_id: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    sample_id: Mapped[str] = mapped_column(String(128), nullable=False)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("batches.id", ondelete="SET NULL")
    )
    batch_code: Mapped[str | None] = mapped_column(String(64))
    lot_code: Mapped[str | None] = mapped_column(String(64))
    variety: Mapped[str | None] = mapped_column(String(120))
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_status: Mapped[ScanProcessingStatus] = mapped_column(
        pg_enum(ScanProcessingStatus, "scan_processing_status"),
        nullable=False,
        default=ScanProcessingStatus.AWAITING_FILES,
        server_default=text("'awaiting_files'"),
    )
    quality_verdict: Mapped[QualityVerdict | None] = mapped_column(
        pg_enum(QualityVerdict, "quality_verdict")
    )
    ruleset_version: Mapped[str | None] = mapped_column(String(64))
    certification_status: Mapped[str | None] = mapped_column(String(32))
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(64))
    failure_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    measurements: Mapped[list[Measurement]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="Measurement.metric_code"
    )
    evaluations: Mapped[list[QualityEvaluation]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    age_result: Mapped[AgeResult | None] = relationship(
        cascade="all, delete-orphan", lazy="selectin", uselist=False
    )
    files: Mapped[list[ScanFile]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="ScanFile.created_at"
    )

    __table_args__ = (
        Index("uq_scans_device_client_scan", "device_id", "client_scan_id", unique=True),
        CheckConstraint(
            "processing_status <> 'completed' OR finalized_at IS NOT NULL",
            name="ck_scans_completed_has_finalized_at",
        ),
        CheckConstraint(
            "analyzed_at <= received_at + interval '1 hour'",
            name="ck_scans_analyzed_at_not_future",
        ),
        Index(
            "idx_scans_department_completed",
            "department_id",
            text("analyzed_at DESC"),
            postgresql_where=text("processing_status = 'completed'"),
        ),
        Index("idx_scans_department_received", "department_id", text("received_at DESC")),
        Index(
            "idx_scans_batch",
            "department_id",
            "batch_id",
            postgresql_where=text("batch_id IS NOT NULL"),
        ),
        Index("idx_scans_device", "device_id", text("received_at DESC")),
        Index(
            "idx_scans_status",
            "processing_status",
            postgresql_where=text("processing_status <> 'completed'"),
        ),
    )


class Measurement(Base):
    __tablename__ = "measurements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )
    metric_code: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_label: Mapped[str | None] = mapped_column(String(120))
    value: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(24), nullable=False)
    basis: Mapped[MeasurementBasis] = mapped_column(
        pg_enum(MeasurementBasis, "measurement_basis"), nullable=False
    )
    is_estimated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("uq_measurements_scan_metric_basis", "scan_id", "metric_code", "basis", unique=True),
        CheckConstraint("value >= 0", name="ck_measurements_value_non_negative"),
        CheckConstraint(
            "is_estimated OR basis IN "
            "('count_percent','physical_mass_percent','physical_mass_grams','count',"
            "'dimension','ratio','other')",
            name="ck_measurements_estimated_basis",
        ),
        CheckConstraint(
            "basis <> 'count_percent' OR unit = 'percent'",
            name="ck_measurements_count_percent_unit",
        ),
        CheckConstraint(
            "basis <> 'estimated_mass_percent' OR (unit = 'percent' AND is_estimated)",
            name="ck_measurements_estimated_mass_unit",
        ),
        CheckConstraint(
            "basis <> 'physical_mass_percent' OR unit = 'percent'",
            name="ck_measurements_physical_percent_unit",
        ),
        CheckConstraint(
            "basis <> 'physical_mass_grams' OR unit = 'gram'",
            name="ck_measurements_physical_grams_unit",
        ),
        CheckConstraint(
            "basis <> 'dimension' OR unit = 'mm'", name="ck_measurements_dimension_unit"
        ),
        Index("idx_measurements_scan", "scan_id"),
        Index("idx_measurements_metric", "metric_code", "basis"),
    )


class QualityEvaluation(Base):
    __tablename__ = "quality_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )
    parameter_code: Mapped[str] = mapped_column(String(64), nullable=False)
    basis: Mapped[MeasurementBasis] = mapped_column(
        pg_enum(MeasurementBasis, "measurement_basis"), nullable=False
    )
    measured_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    threshold_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    comparison_operator: Mapped[str | None] = mapped_column(String(8))
    source_limit_text: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[QualityVerdict] = mapped_column(
        pg_enum(QualityVerdict, "quality_verdict"), nullable=False
    )
    ruleset_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "uq_quality_evaluations_scan_parameter_basis",
            "scan_id",
            "parameter_code",
            "basis",
            unique=True,
        ),
        Index("idx_quality_evaluations_scan", "scan_id"),
        Index("idx_quality_evaluations_status", "status"),
    )


class AgeResult(Base):
    __tablename__ = "age_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )
    age_value_months: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    age_min_months: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    age_max_months: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    age_category: Mapped[str | None] = mapped_column(String(64))
    proportion_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    unit: Mapped[str | None] = mapped_column(String(24))
    method: Mapped[str | None] = mapped_column(String(64))
    model_version: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    validation_status: Mapped[AgeValidationStatus | None] = mapped_column(
        pg_enum(AgeValidationStatus, "age_validation_status")
    )
    raw_value: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("uq_age_results_scan", "scan_id", unique=True),
        CheckConstraint(
            "age_min_months IS NULL OR age_min_months >= 0",
            name="ck_age_results_min_non_negative",
        ),
        CheckConstraint(
            "age_max_months IS NULL OR age_max_months >= 0",
            name="ck_age_results_max_non_negative",
        ),
        CheckConstraint(
            "age_min_months IS NULL OR age_max_months IS NULL OR age_max_months >= age_min_months",
            name="ck_age_results_range_order",
        ),
        CheckConstraint(
            "age_value_months IS NOT NULL OR age_min_months IS NOT NULL "
            "OR age_max_months IS NOT NULL OR age_category IS NOT NULL",
            name="ck_age_results_has_information",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 100)",
            name="ck_age_results_confidence_range",
        ),
        CheckConstraint(
            "proportion_percent IS NULL OR (proportion_percent >= 0 AND proportion_percent <= 100)",
            name="ck_age_results_proportion_range",
        ),
    )
