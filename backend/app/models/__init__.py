"""ORM models.

Importing this package registers every table on ``Base.metadata`` for Alembic and
for test schema creation. Keep the imports explicit: an unreferenced model module is
invisible to autogenerate.
"""

from app.db.base import Base
from app.models.analysis import AgeResult, Batch, Measurement, QualityEvaluation, Scan
from app.models.audit import AuditLog
from app.models.device import Device, DeviceAssignment, DeviceCredential
from app.models.enums import (
    AgeValidationStatus,
    AuditActorType,
    DeviceStatus,
    MeasurementBasis,
    MembershipRole,
    NotificationEventType,
    NotificationSeverity,
    QualityVerdict,
    ScanFileRole,
    ScanProcessingStatus,
    UploadStatus,
)
from app.models.files import ScanFile, UploadAttempt
from app.models.identity import Membership, User, UserSession
from app.models.notifications import Notification, NotificationRecipient
from app.models.organization import Department

__all__ = [
    "AgeResult",
    "AgeValidationStatus",
    "AuditActorType",
    "AuditLog",
    "Base",
    "Batch",
    "Department",
    "Device",
    "DeviceAssignment",
    "DeviceCredential",
    "DeviceStatus",
    "Measurement",
    "MeasurementBasis",
    "Membership",
    "MembershipRole",
    "Notification",
    "NotificationEventType",
    "NotificationRecipient",
    "NotificationSeverity",
    "QualityEvaluation",
    "QualityVerdict",
    "Scan",
    "ScanFile",
    "ScanFileRole",
    "ScanProcessingStatus",
    "UploadAttempt",
    "UploadStatus",
    "User",
    "UserSession",
]
