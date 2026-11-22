"""Device scan ingestion and lifecycle.

Ownership comes only from the authenticated device's active assignment; any department
value in the payload is never read. Idempotency is enforced by a database unique
constraint, with the stored canonical payload hash deciding replay vs conflict.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.models.analysis import AgeResult, Batch, Measurement, QualityEvaluation, Scan
from app.models.device import Device, DeviceAssignment
from app.models.enums import (
    AuditActorType,
    DeviceStatus,
    NotificationEventType,
    NotificationSeverity,
    QualityVerdict,
    ScanFileRole,
    ScanProcessingStatus,
    UploadStatus,
)
from app.models.files import ScanFile, UploadAttempt
from app.models.identity import Membership
from app.models.notifications import Notification, NotificationRecipient
from app.models.organization import Department
from app.schemas.scan import DevicePayload, FinalizeResult, ScanAccepted, UploadResult
from app.services.audit import record_audit
from app.storage.base import StorageError, StoragePort

ROLE_CONTENT_TYPES: dict[ScanFileRole, set[str]] = {
    ScanFileRole.REPORT_PDF: {"application/pdf"},
    ScanFileRole.BOTTOM_IMAGE: {"image/png", "image/jpeg"},
    ScanFileRole.TOP_IMAGE: {"image/png", "image/jpeg"},
    ScanFileRole.OTHER: {"application/pdf", "image/png", "image/jpeg"},
}

EXTENSIONS = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}

MAGIC_PREFIXES = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
}

ALL_ROLES = [
    ScanFileRole.REPORT_PDF,
    ScanFileRole.BOTTOM_IMAGE,
    ScanFileRole.TOP_IMAGE,
    ScanFileRole.OTHER,
]


@dataclass(frozen=True)
class DeviceContext:
    device_id: uuid.UUID
    ip_address: str | None = None
    user_agent: str | None = None
    request_id: str | None = None


def utcnow() -> datetime:
    return datetime.now(UTC)


def canonical_hash(raw_payload: dict[str, Any]) -> str:
    canonical = json.dumps(raw_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _size_limit(settings: Settings, role: ScanFileRole) -> int:
    if role is ScanFileRole.REPORT_PDF:
        return settings.max_report_bytes
    return settings.max_image_bytes


def required_roles(settings: Settings) -> list[ScanFileRole]:
    roles: list[ScanFileRole] = []
    for value in settings.required_attachment_role_list:
        try:
            roles.append(ScanFileRole(value))
        except ValueError:
            continue
    return roles


def optional_roles(settings: Settings) -> list[ScanFileRole]:
    required = set(required_roles(settings))
    return [role for role in ALL_ROLES if role is not ScanFileRole.OTHER and role not in required]


def active_assignment(
    db: Session, device_id: uuid.UUID
) -> tuple[DeviceAssignment, Department] | None:
    row = db.execute(
        select(DeviceAssignment, Department)
        .join(Department, Department.id == DeviceAssignment.department_id)
        .where(
            DeviceAssignment.device_id == device_id,
            DeviceAssignment.effective_to.is_(None),
        )
    ).first()
    return (row[0], row[1]) if row else None


def get_owned_scan(db: Session, scan_id: uuid.UUID, device: Device) -> Scan:
    scan = db.get(Scan, scan_id)
    if scan is None or scan.device_id != device.id:
        raise AppError(404, ErrorCode.NOT_FOUND, "Scan not found.")
    return scan


def _existing_scan(db: Session, device_id: uuid.UUID, client_scan_id: str) -> Scan | None:
    return db.scalar(
        select(Scan).where(Scan.device_id == device_id, Scan.client_scan_id == client_scan_id)
    )


def _accepted(scan: Scan, settings: Settings, *, replayed: bool) -> ScanAccepted:
    return ScanAccepted(
        scan_id=scan.id,
        client_scan_id=scan.client_scan_id,
        processing_status=scan.processing_status,
        required_attachments=[role.value for role in required_roles(settings)],
        optional_attachments=[role.value for role in optional_roles(settings)],
        received_at=scan.received_at,
        replayed=replayed,
    )


def _replay_or_conflict(scan: Scan, payload_hash: str, settings: Settings) -> ScanAccepted:
    if scan.payload_sha256 != payload_hash:
        raise AppError(
            status_code=409,
            code=ErrorCode.SCAN_CONFLICT,
            message="A different payload was already accepted for this client_scan_id.",
            details={"existing_scan_id": str(scan.id)},
        )
    if scan.processing_status is ScanProcessingStatus.FAILED:
        raise AppError(
            status_code=409,
            code="scan_already_failed",
            message="The original submission failed. Use a new client_scan_id.",
            details={"failure_code": scan.failure_code},
        )
    return _accepted(scan, settings, replayed=True)


def _get_or_create_batch(
    db: Session,
    department_id: uuid.UUID,
    batch_code: str,
    lot_code: str | None,
    variety: str | None,
) -> Batch:
    batch = db.scalar(
        select(Batch).where(
            Batch.department_id == department_id,
            Batch.batch_code == batch_code,
            Batch.lot_code.is_(None) if lot_code is None else Batch.lot_code == lot_code,
        )
    )
    if batch is not None:
        return batch
    batch = Batch(
        department_id=department_id,
        batch_code=batch_code,
        lot_code=lot_code,
        variety=variety,
    )
    db.add(batch)
    db.flush()
    return batch


def submit_scan(
    db: Session,
    settings: Settings,
    device: Device,
    payload: DevicePayload,
    raw_payload: dict[str, Any],
    ctx: DeviceContext,
) -> ScanAccepted:
    if device.status is not DeviceStatus.ACTIVE:
        raise AppError(403, "device_suspended", "This device is not permitted to submit data.")
    if payload.device_id is not None and payload.device_id != device.device_uid:
        raise AppError(403, "device_mismatch", "The payload device does not match the credential.")

    assignment = active_assignment(db, device.id)
    if assignment is None or not assignment[1].is_active:
        raise AppError(
            403,
            "device_unassigned",
            "This device has no active department assignment.",
        )
    department = assignment[1]

    now = utcnow()
    if payload.analyzed_at > now + timedelta(hours=1):
        raise AppError(422, "invalid_timestamp", "analyzed_at is too far in the future.")

    payload_hash = canonical_hash(raw_payload)
    existing = _existing_scan(db, device.id, payload.client_scan_id)
    if existing is not None:
        return _replay_or_conflict(existing, payload_hash, settings)

    batch = None
    if payload.sample.batch_id:
        batch = _get_or_create_batch(
            db,
            department.id,
            payload.sample.batch_id,
            payload.sample.lot_id,
            payload.sample.variety,
        )

    scan = Scan(
        device_id=device.id,
        department_id=department.id,
        client_scan_id=payload.client_scan_id,
        schema_version=payload.schema_version,
        sample_id=payload.sample.sample_id,
        batch_id=batch.id if batch else None,
        batch_code=payload.sample.batch_id,
        lot_code=payload.sample.lot_id,
        variety=payload.sample.variety,
        analyzed_at=payload.analyzed_at,
        processing_status=ScanProcessingStatus.AWAITING_FILES,
        ruleset_version=payload.evaluation.ruleset_version if payload.evaluation else None,
        certification_status=payload.evaluation.certification_status
        if payload.evaluation
        else None,
        raw_payload=raw_payload,
        payload_sha256=payload_hash,
    )
    db.add(scan)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raced = _existing_scan(db, device.id, payload.client_scan_id)
        if raced is None:
            raise
        return _replay_or_conflict(raced, payload_hash, settings)

    for measurement in payload.analysis.measurements:
        db.add(
            Measurement(
                scan_id=scan.id,
                metric_code=measurement.code,
                metric_label=measurement.label,
                value=Decimal(measurement.value),
                unit=measurement.unit,
                basis=measurement.basis,
                is_estimated=measurement.is_estimated,
                source_path=measurement.source_path,
            )
        )

    if payload.rice_age is not None:
        age = payload.rice_age
        db.add(
            AgeResult(
                scan_id=scan.id,
                age_value_months=age.age_value_months,
                age_min_months=age.age_min_months,
                age_max_months=age.age_max_months,
                age_category=age.age_category,
                proportion_percent=age.proportion_percent,
                unit=age.unit,
                method=age.method,
                model_version=age.model_version,
                confidence=age.confidence,
                validation_status=age.validation_status,
                raw_value=age.raw_value,
            )
        )

    if payload.evaluation is not None:
        for parameter in payload.evaluation.parameters:
            db.add(
                QualityEvaluation(
                    scan_id=scan.id,
                    parameter_code=parameter.code,
                    basis=parameter.basis,
                    measured_value=parameter.measured_value,
                    threshold_value=parameter.threshold_value,
                    comparison_operator=parameter.comparison_operator,
                    source_limit_text=parameter.source_limit_text,
                    status=parameter.status,
                    ruleset_version=payload.evaluation.ruleset_version,
                )
            )

    device.last_seen_at = now
    record_audit(
        db,
        action="scan.accepted",
        actor_type=AuditActorType.DEVICE,
        actor_device_id=device.id,
        department_id=department.id,
        target_type="scan",
        target_id=scan.id,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        request_id=ctx.request_id,
        metadata={"client_scan_id": scan.client_scan_id, "sample_id": scan.sample_id},
    )
    db.commit()
    db.refresh(scan)
    return _accepted(scan, settings, replayed=False)


def _sanitise_filename(name: str, fallback: str) -> str:
    cleaned = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    cleaned = "".join(character for character in cleaned if character.isprintable())
    return cleaned[:255] or fallback


def prepare_attachment(
    db: Session,
    settings: Settings,
    storage: StoragePort,
    device: Device,
    scan_id: uuid.UUID,
    *,
    role: ScanFileRole,
    content_type: str,
    size_bytes: int,
    sha256: str,
    filename: str,
    ctx: DeviceContext,
) -> tuple[ScanFile, str, datetime]:
    scan = get_owned_scan(db, scan_id, device)
    if scan.processing_status in {ScanProcessingStatus.COMPLETED, ScanProcessingStatus.FAILED}:
        raise AppError(409, "scan_not_finalizable", "This scan is already terminal.")
    if content_type not in ROLE_CONTENT_TYPES[role]:
        raise AppError(
            415,
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            "That content type is not allowed for this attachment role.",
        )
    if size_bytes > _size_limit(settings, role):
        raise AppError(413, ErrorCode.FILE_TOO_LARGE, "The file exceeds the configured limit.")

    existing = db.scalar(select(ScanFile).where(ScanFile.scan_id == scan.id, ScanFile.role == role))
    if existing is not None and existing.upload_status is UploadStatus.VERIFIED:
        raise AppError(409, "role_already_verified", "This attachment is already verified.")
    if existing is not None:
        db.delete(existing)
        db.flush()

    file_id = uuid.uuid4()
    extension = EXTENSIONS[content_type]
    key = f"scans/{scan.department_id}/{scan.id}/{role.value}/{file_id}.{extension}"
    record = ScanFile(
        id=file_id,
        scan_id=scan.id,
        role=role,
        storage_backend=storage.backend,
        storage_key=key,
        original_filename=_sanitise_filename(filename, f"{role.value}.{extension}"),
        mime_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        upload_status=UploadStatus.PENDING,
    )
    db.add(record)
    db.add(
        UploadAttempt(
            scan_id=scan.id,
            scan_file_id=file_id,
            role=role,
            stage="prepare",
            status="succeeded",
        )
    )
    direct_url = storage.presigned_put(
        key, content_type=content_type, expires_in=settings.storage_signed_url_ttl_seconds
    )
    if direct_url is None:
        url = f"{settings.api_v1_prefix}/device/scans/{scan.id}/files/{file_id}"
    else:
        url = direct_url
    expires_at = utcnow() + timedelta(seconds=settings.storage_signed_url_ttl_seconds)
    db.commit()
    return record, url, expires_at


def store_upload(
    db: Session,
    settings: Settings,
    storage: StoragePort,
    device: Device,
    scan_id: uuid.UUID,
    upload_id: uuid.UUID,
    *,
    body: bytes,
    content_type: str,
    ctx: DeviceContext,
) -> UploadResult:
    scan = get_owned_scan(db, scan_id, device)
    record = db.get(ScanFile, upload_id)
    if record is None or record.scan_id != scan.id:
        raise AppError(404, ErrorCode.NOT_FOUND, "Upload target not found.")
    if record.upload_status is UploadStatus.VERIFIED:
        raise AppError(409, "role_already_verified", "This attachment is already verified.")
    if content_type.split(";")[0].strip().lower() != record.mime_type:
        raise AppError(415, ErrorCode.UNSUPPORTED_MEDIA_TYPE, "Content type does not match.")

    limit = _size_limit(settings, record.role)
    if len(body) > limit:
        raise AppError(413, ErrorCode.FILE_TOO_LARGE, "The file exceeds the configured limit.")

    actual_hash = hashlib.sha256(body).hexdigest()
    if actual_hash != record.sha256:
        db.add(
            UploadAttempt(
                scan_id=scan.id,
                scan_file_id=record.id,
                role=record.role,
                stage="upload",
                status="failed",
                diagnostic_code=ErrorCode.CHECKSUM_MISMATCH,
            )
        )
        db.commit()
        raise AppError(422, ErrorCode.CHECKSUM_MISMATCH, "The uploaded checksum does not match.")

    prefixes = MAGIC_PREFIXES.get(record.mime_type, ())
    if not prefixes or not body.startswith(prefixes):
        raise AppError(
            415,
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            "The file content does not match its declared type.",
        )

    try:
        storage.save(record.storage_key, body, content_type=record.mime_type)
    except StorageError as exc:
        raise AppError(
            503, ErrorCode.DEPENDENCY_UNAVAILABLE, "Attachment storage is unavailable."
        ) from exc

    record.size_bytes = len(body)
    record.upload_status = UploadStatus.VERIFIED
    record.verified_at = utcnow()
    db.add(
        UploadAttempt(
            scan_id=scan.id,
            scan_file_id=record.id,
            role=record.role,
            stage="upload",
            status="succeeded",
        )
    )
    record_audit(
        db,
        action="scan.attachment_verified",
        actor_type=AuditActorType.DEVICE,
        actor_device_id=device.id,
        department_id=scan.department_id,
        target_type="scan",
        target_id=scan.id,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        request_id=ctx.request_id,
        metadata={"role": record.role.value, "size_bytes": len(body)},
    )
    db.commit()
    return UploadResult(
        upload_id=record.id,
        received_bytes=len(body),
        sha256=actual_hash,
        upload_status=record.upload_status.value,
    )


def _create_notification(
    db: Session,
    *,
    scan: Scan,
    event_type: NotificationEventType,
    severity: NotificationSeverity,
    title: str,
    body: str | None,
) -> bool:
    """Insert once per scan/event. Returns ``True`` if a new notification was created."""

    event_key = f"{event_type.value}:{scan.id}"
    if db.scalar(select(Notification.id).where(Notification.event_key == event_key)):
        return False
    notification = Notification(
        department_id=scan.department_id,
        scan_id=scan.id,
        event_type=event_type,
        event_key=event_key,
        severity=severity,
        title=title,
        body=body,
    )
    db.add(notification)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False

    recipient_ids = db.scalars(
        select(Membership.user_id).where(
            Membership.department_id == scan.department_id,
            Membership.is_active.is_(True),
        )
    ).all()
    for user_id in set(recipient_ids):
        db.add(NotificationRecipient(notification_id=notification.id, user_id=user_id))
    return True


def finalize_scan(
    db: Session, settings: Settings, device: Device, scan_id: uuid.UUID, ctx: DeviceContext
) -> FinalizeResult:
    scan = get_owned_scan(db, scan_id, device)
    if scan.processing_status is ScanProcessingStatus.COMPLETED:
        return FinalizeResult(
            scan_id=scan.id,
            processing_status=scan.processing_status,
            quality_verdict=scan.quality_verdict,
            finalized_at=scan.finalized_at,
            notifications_created=0,
        )
    if scan.processing_status is ScanProcessingStatus.FAILED:
        raise AppError(409, "scan_not_finalizable", "This scan failed and cannot be finalized.")

    verified = set(
        db.scalars(
            select(ScanFile.role).where(
                ScanFile.scan_id == scan.id, ScanFile.upload_status == UploadStatus.VERIFIED
            )
        ).all()
    )
    missing = [role.value for role in required_roles(settings) if role not in verified]
    if missing:
        raise AppError(
            status_code=409,
            code=ErrorCode.MISSING_ATTACHMENTS,
            message="Required attachments are missing.",
            details={"roles": missing},
        )

    scan.processing_status = ScanProcessingStatus.VERIFYING
    db.flush()

    evaluation = (scan.raw_payload or {}).get("evaluation") or {}
    verdict_value = evaluation.get("overall")
    if verdict_value:
        scan.quality_verdict = QualityVerdict(verdict_value)
    scan.processing_status = ScanProcessingStatus.COMPLETED
    scan.finalized_at = utcnow()
    device.last_upload_at = scan.finalized_at
    device.last_seen_at = scan.finalized_at

    created = 0
    if _create_notification(
        db,
        scan=scan,
        event_type=NotificationEventType.SCAN_COMPLETED,
        severity=NotificationSeverity.INFO,
        title=f"Scan completed for {scan.sample_id}",
        body="A device analysis submission finished processing and is available.",
    ):
        created += 1

    if (
        scan.quality_verdict is QualityVerdict.FLAGGED
        and _create_notification(
            db,
            scan=scan,
            event_type=NotificationEventType.QUALITY_FLAGGED,
            severity=NotificationSeverity.WARNING,
            title=f"Quality flag on {scan.sample_id}",
            body=(
                "The device reported a flagged quality result. "
                "This is advisory, not a statutory grading."
            ),
        )
        or scan.quality_verdict is QualityVerdict.LAB_CONFIRMATION_REQUIRED
        and _create_notification(
            db,
            scan=scan,
            event_type=NotificationEventType.LAB_CONFIRMATION_REQUIRED,
            severity=NotificationSeverity.CRITICAL,
            title=f"Lab confirmation requested for {scan.sample_id}",
            body="The device requested laboratory confirmation.",
        )
    ):
        created += 1

    record_audit(
        db,
        action="scan.completed",
        actor_type=AuditActorType.DEVICE,
        actor_device_id=device.id,
        department_id=scan.department_id,
        target_type="scan",
        target_id=scan.id,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        request_id=ctx.request_id,
        metadata={"verdict": scan.quality_verdict.value if scan.quality_verdict else None},
    )
    db.commit()
    db.refresh(scan)
    return FinalizeResult(
        scan_id=scan.id,
        processing_status=scan.processing_status,
        quality_verdict=scan.quality_verdict,
        finalized_at=scan.finalized_at,
        notifications_created=created,
    )
