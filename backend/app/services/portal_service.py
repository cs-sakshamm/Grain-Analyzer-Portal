"""Portal read services, always scoped to a resolved department."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.models.analysis import AgeResult, Measurement, QualityEvaluation, Scan
from app.models.device import Device
from app.models.enums import AuditActorType, ScanFileRole, ScanProcessingStatus, UploadStatus
from app.models.files import ScanFile
from app.models.identity import User
from app.models.organization import Department
from app.services.audit import record_audit
from app.storage.base import StorageError, StoragePort

ADVISORY = (
    "Pre-inspection advisory only. Optical estimates are not statutory procurement measurements."
)


def latest_completed_scan(db: Session, department_id: uuid.UUID) -> Scan | None:
    return db.scalar(
        select(Scan)
        .where(
            Scan.department_id == department_id,
            Scan.processing_status == ScanProcessingStatus.COMPLETED,
        )
        .order_by(Scan.analyzed_at.desc(), Scan.received_at.desc())
        .limit(1)
    )


def get_scan_for_department(db: Session, scan_id: uuid.UUID, department_id: uuid.UUID) -> Scan:
    scan = db.get(Scan, scan_id)
    if scan is None or scan.department_id != department_id:
        raise AppError(404, ErrorCode.NOT_FOUND, "Scan not found.")
    return scan


def _measurements(db: Session, scan: Scan) -> list[Measurement]:
    return list(
        db.scalars(
            select(Measurement)
            .where(Measurement.scan_id == scan.id)
            .order_by(Measurement.metric_code, Measurement.basis)
        ).all()
    )


def _age(db: Session, scan: Scan) -> AgeResult | None:
    return db.scalar(select(AgeResult).where(AgeResult.scan_id == scan.id))


def _files(db: Session, scan: Scan) -> list[ScanFile]:
    return list(
        db.scalars(
            select(ScanFile).where(ScanFile.scan_id == scan.id).order_by(ScanFile.created_at)
        ).all()
    )


def scan_detail(db: Session, scan: Scan) -> dict[str, Any]:
    device = db.get(Device, scan.device_id)
    department = db.get(Department, scan.department_id)
    measurements = _measurements(db, scan)
    age = _age(db, scan)
    files = _files(db, scan)
    raw = scan.raw_payload or {}
    return {
        "scan": {
            "id": str(scan.id),
            "sample_id": scan.sample_id,
            "batch_code": scan.batch_code,
            "lot_code": scan.lot_code,
            "variety": scan.variety,
            "analyzed_at": scan.analyzed_at.isoformat(),
            "received_at": scan.received_at.isoformat(),
            "finalized_at": scan.finalized_at.isoformat() if scan.finalized_at else None,
            "processing_status": scan.processing_status.value,
            "quality_verdict": scan.quality_verdict.value if scan.quality_verdict else None,
            "ruleset_version": scan.ruleset_version,
            "certification_status": scan.certification_status,
            "device": {
                "id": str(device.id) if device else None,
                "device_uid": device.device_uid if device else None,
                "friendly_name": device.friendly_name if device else None,
            },
            "department": {
                "id": str(department.id) if department else None,
                "code": department.code if department else None,
                "name": department.name if department else None,
            },
            "grain_count": (raw.get("analysis") or {}).get("grain_count"),
            "measurements": [
                {
                    "metric_code": measurement.metric_code,
                    "metric_label": measurement.metric_label,
                    "value": str(measurement.value),
                    "unit": measurement.unit,
                    "basis": measurement.basis.value,
                    "is_estimated": measurement.is_estimated,
                }
                for measurement in measurements
            ],
            "age": (
                {
                    "age_value_months": str(age.age_value_months)
                    if age.age_value_months is not None
                    else None,
                    "age_min_months": str(age.age_min_months)
                    if age.age_min_months is not None
                    else None,
                    "age_max_months": str(age.age_max_months)
                    if age.age_max_months is not None
                    else None,
                    "age_category": age.age_category,
                    "proportion_percent": str(age.proportion_percent)
                    if age.proportion_percent is not None
                    else None,
                    "unit": age.unit,
                    "method": age.method,
                    "model_version": age.model_version,
                    "validation_status": age.validation_status.value
                    if age.validation_status
                    else None,
                    "raw_value": age.raw_value,
                }
                if age is not None
                else None
            ),
            "files": [
                {
                    "role": file.role.value,
                    "available": file.upload_status is UploadStatus.VERIFIED,
                    "filename": file.original_filename,
                    "size_bytes": file.size_bytes,
                    "mime_type": file.mime_type,
                }
                for file in files
                if file.upload_status is not UploadStatus.REJECTED
            ],
            "advisory": ADVISORY,
        },
        "as_of": scan.updated_at.isoformat(),
    }


def evaluations_for(db: Session, scan: Scan) -> list[QualityEvaluation]:
    return list(
        db.scalars(select(QualityEvaluation).where(QualityEvaluation.scan_id == scan.id)).all()
    )


def report_file(db: Session, scan: Scan) -> ScanFile:
    record = db.scalar(
        select(ScanFile).where(
            ScanFile.scan_id == scan.id,
            ScanFile.role == ScanFileRole.REPORT_PDF,
            ScanFile.upload_status == UploadStatus.VERIFIED,
        )
    )
    if record is None:
        raise AppError(404, "report_unavailable", "No verified report is available for this scan.")
    return record


def audit_cross_department_read(
    db: Session,
    *,
    user: User,
    scan: Scan,
    has_membership: bool,
    action: str,
    request_id: str | None,
    ip: str | None,
    user_agent: str | None,
) -> None:
    """Super-admin reads outside their own departments are audited (contract §1.3)."""

    if user.is_super_admin and not has_membership:
        record_audit(
            db,
            action=action,
            actor_type=AuditActorType.USER,
            actor_user_id=user.id,
            department_id=scan.department_id,
            target_type="scan",
            target_id=scan.id,
            request_id=request_id,
            ip_address=ip,
            user_agent=user_agent,
        )


def read_report_bytes(storage: StoragePort, record: ScanFile) -> bytes:
    try:
        return storage.load(record.storage_key)
    except StorageError as exc:
        raise AppError(
            503, ErrorCode.DEPENDENCY_UNAVAILABLE, "Attachment storage is unavailable."
        ) from exc
