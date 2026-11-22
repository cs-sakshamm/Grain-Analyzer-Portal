"""Stable enumerated values stored in PostgreSQL enum types.

Values are lowercase strings and must never be renamed in place: a rename would
silently change the meaning of stored rows. New values are added by migration.
"""

from __future__ import annotations

import enum


class StrEnum(enum.StrEnum):
    """String enum whose ``str()`` is the stored value (useful in logs and SQL)."""


class MembershipRole(StrEnum):
    DEPARTMENT_ADMIN = "department_admin"
    DEPARTMENT_USER = "department_user"


class DeviceStatus(StrEnum):
    PROVISIONED = "provisioned"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"


class ScanProcessingStatus(StrEnum):
    RECEIVED = "received"
    AWAITING_FILES = "awaiting_files"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


class QualityVerdict(StrEnum):
    PASS = "pass"
    FLAGGED = "flagged"
    INCONCLUSIVE = "inconclusive"
    LAB_CONFIRMATION_REQUIRED = "lab_confirmation_required"


class MeasurementBasis(StrEnum):
    COUNT_PERCENT = "count_percent"
    ESTIMATED_MASS_PERCENT = "estimated_mass_percent"
    PHYSICAL_MASS_PERCENT = "physical_mass_percent"
    PHYSICAL_MASS_GRAMS = "physical_mass_grams"
    COUNT = "count"
    DIMENSION = "dimension"
    RATIO = "ratio"
    OTHER = "other"


class ScanFileRole(StrEnum):
    REPORT_PDF = "report_pdf"
    BOTTOM_IMAGE = "bottom_image"
    TOP_IMAGE = "top_image"
    OTHER = "other"


class UploadStatus(StrEnum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    VERIFIED = "verified"
    REJECTED = "rejected"


class AgeValidationStatus(StrEnum):
    UNVALIDATED = "unvalidated"
    PROVISIONAL = "provisional"
    VALIDATED = "validated"
    REJECTED = "rejected"


class NotificationEventType(StrEnum):
    SCAN_COMPLETED = "scan_completed"
    QUALITY_FLAGGED = "quality_flagged"
    UPLOAD_FAILED = "upload_failed"
    REPORT_AVAILABLE = "report_available"
    LAB_CONFIRMATION_REQUIRED = "lab_confirmation_required"


class NotificationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AuditActorType(StrEnum):
    USER = "user"
    DEVICE = "device"
    SYSTEM = "system"
