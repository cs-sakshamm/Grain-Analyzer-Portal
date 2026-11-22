"""Device payload and scan lifecycle schemas.

This mirrors ``docs/api/device-payload.schema.json``; contract tests validate both
against the same fixtures. Unknown top-level fields are rejected, which is what stops a
device from smuggling ``department_id`` into a submission.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    AgeValidationStatus,
    MeasurementBasis,
    QualityVerdict,
    ScanFileRole,
    ScanProcessingStatus,
)

Unit = Literal["percent", "mm", "ratio", "count", "gram"]
ComparisonOperator = Literal["gte", "lte", "gt", "lt", "eq"]

BASIS_UNITS: dict[MeasurementBasis, set[str]] = {
    MeasurementBasis.COUNT_PERCENT: {"percent"},
    MeasurementBasis.ESTIMATED_MASS_PERCENT: {"percent"},
    MeasurementBasis.PHYSICAL_MASS_PERCENT: {"percent"},
    MeasurementBasis.PHYSICAL_MASS_GRAMS: {"gram"},
    MeasurementBasis.COUNT: {"count"},
    MeasurementBasis.DIMENSION: {"mm"},
    MeasurementBasis.RATIO: {"ratio"},
    MeasurementBasis.OTHER: {"percent", "mm", "ratio", "count", "gram"},
}


class SampleBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str = Field(min_length=1, max_length=128)
    batch_id: str | None = Field(default=None, max_length=64)
    lot_id: str | None = Field(default=None, max_length=64)
    variety: str | None = Field(default=None, max_length=120)


class MeasurementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    label: str | None = Field(default=None, max_length=120)
    value: Decimal = Field(ge=0)
    unit: Unit
    basis: MeasurementBasis
    is_estimated: bool = False
    source_path: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _unit_matches_basis(self) -> MeasurementIn:
        allowed = BASIS_UNITS[self.basis]
        if self.unit not in allowed:
            raise ValueError(f"unit '{self.unit}' is not valid for basis '{self.basis}'")
        if self.basis is MeasurementBasis.ESTIMATED_MASS_PERCENT and not self.is_estimated:
            raise ValueError("estimated_mass_percent measurements must be marked estimated")
        return self


class AnalysisBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grain_count: int | None = Field(default=None, ge=0)
    measurements: list[MeasurementIn] = Field(min_length=1, max_length=200)


class RiceAgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    age_value_months: Decimal | None = Field(default=None, ge=0)
    age_min_months: Decimal | None = Field(default=None, ge=0)
    age_max_months: Decimal | None = Field(default=None, ge=0)
    age_category: str | None = Field(default=None, max_length=64)
    proportion_percent: Decimal | None = Field(default=None, ge=0, le=100)
    unit: str | None = Field(default=None, max_length=24)
    method: str | None = Field(default=None, max_length=64)
    model_version: str | None = Field(default=None, max_length=64)
    confidence: Decimal | None = Field(default=None, ge=0, le=100)
    validation_status: AgeValidationStatus | None = None
    raw_value: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _has_information_and_ordered_range(self) -> RiceAgeIn:
        if (
            self.age_value_months is None
            and self.age_min_months is None
            and self.age_max_months is None
            and not self.age_category
        ):
            raise ValueError("rice_age must carry at least one age value or category")
        if (
            self.age_min_months is not None
            and self.age_max_months is not None
            and self.age_max_months < self.age_min_months
        ):
            raise ValueError("age_max_months must be greater than or equal to age_min_months")
        return self


class EvaluationParameter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    basis: MeasurementBasis
    measured_value: Decimal | None = Field(default=None, ge=0)
    threshold_value: Decimal | None = Field(default=None, ge=0)
    comparison_operator: ComparisonOperator | None = None
    source_limit_text: str | None = Field(default=None, max_length=120)
    status: QualityVerdict


class EvaluationBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall: QualityVerdict | None = None
    ruleset_version: str | None = Field(default=None, max_length=64)
    certification_status: str | None = Field(default=None, max_length=32)
    parameters: list[EvaluationParameter] = Field(default_factory=list, max_length=200)


class AttachmentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: ScanFileRole
    content_type: str = Field(min_length=3, max_length=127)
    filename: str = Field(min_length=1, max_length=255)


class DevicePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^1\.[0-9]+$")
    client_scan_id: str = Field(min_length=1, max_length=128)
    sample: SampleBlock
    analyzed_at: datetime
    analysis: AnalysisBlock
    rice_age: RiceAgeIn | None = None
    evaluation: EvaluationBlock | None = None
    attachments: list[AttachmentManifest] = Field(default_factory=list, max_length=10)
    device_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _analyzed_at_has_timezone(self) -> DevicePayload:
        if self.analyzed_at.tzinfo is None:
            raise ValueError("analyzed_at must include a timezone offset")
        return self


class ScanAccepted(BaseModel):
    scan_id: uuid.UUID
    client_scan_id: str
    processing_status: ScanProcessingStatus
    required_attachments: list[str]
    optional_attachments: list[str]
    received_at: datetime
    replayed: bool = False


class AttachmentPrepare(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: ScanFileRole
    content_type: str = Field(min_length=3, max_length=127)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    filename: str = Field(min_length=1, max_length=255)


class AttachmentTarget(BaseModel):
    upload_id: uuid.UUID
    method: str
    url: str
    headers: dict[str, str]
    expires_at: datetime


class UploadResult(BaseModel):
    upload_id: uuid.UUID
    received_bytes: int
    sha256: str
    upload_status: str


class ScanStatus(BaseModel):
    scan_id: uuid.UUID
    client_scan_id: str
    processing_status: ScanProcessingStatus
    quality_verdict: QualityVerdict | None
    failure_code: str | None
    failure_detail: str | None
    received_at: datetime
    finalized_at: datetime | None
    attachments: list[dict[str, str]]


class FinalizeResult(BaseModel):
    scan_id: uuid.UUID
    processing_status: ScanProcessingStatus
    quality_verdict: QualityVerdict | None
    finalized_at: datetime | None
    notifications_created: int


class ScanSummary(BaseModel):
    id: uuid.UUID
    sample_id: str
    batch_code: str | None
    lot_code: str | None
    analyzed_at: datetime
    device_uid: str
    quality_verdict: QualityVerdict | None
