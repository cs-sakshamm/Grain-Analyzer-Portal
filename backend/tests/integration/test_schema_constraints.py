"""Database-level guarantees that application code relies on."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AgeResult,
    Batch,
    Department,
    Device,
    DeviceAssignment,
    DeviceCredential,
    Measurement,
    Notification,
    Scan,
    User,
)
from app.models.enums import (
    DeviceStatus,
    MeasurementBasis,
    NotificationEventType,
    ScanProcessingStatus,
)


def _department(db: Session, code: str = "DEPT-A") -> Department:
    department = Department(code=code, name=f"Department {code}")
    db.add(department)
    db.commit()
    return department


def _device(db: Session, department: Department | None = None) -> Device:
    device = Device(
        device_uid=f"DEV-{uuid.uuid4().hex[:8]}",
        serial_number=f"SN-{uuid.uuid4().hex[:8]}",
        status=DeviceStatus.ACTIVE,
    )
    db.add(device)
    db.commit()
    if department is not None:
        db.add(
            DeviceAssignment(
                device_id=device.id,
                department_id=department.id,
                effective_from=datetime.now(UTC),
            )
        )
        db.commit()
    return device


def _scan(
    db: Session, device: Device, department: Department, client_scan_id: str = "SCAN-1"
) -> Scan:
    scan = Scan(
        device_id=device.id,
        department_id=department.id,
        client_scan_id=client_scan_id,
        schema_version="1.0",
        sample_id="Sample-0038",
        analyzed_at=datetime.now(UTC),
        raw_payload={"schema_version": "1.0"},
        payload_sha256="0" * 64,
    )
    db.add(scan)
    db.commit()
    return scan


def test_all_seventeen_tables_exist(db: Session) -> None:
    tables = set(
        db.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )
        ).scalars()
    )
    expected = {
        "departments",
        "users",
        "memberships",
        "user_sessions",
        "devices",
        "device_credentials",
        "device_assignments",
        "batches",
        "scans",
        "measurements",
        "quality_evaluations",
        "age_results",
        "scan_files",
        "upload_attempts",
        "notifications",
        "notification_recipients",
        "audit_logs",
    }
    assert expected <= tables


def test_email_uniqueness_is_case_insensitive(db: Session) -> None:
    db.add(User(email="Officer@Example.test", password_hash="x"))
    db.commit()
    db.add(User(email="officer@example.TEST", password_hash="x"))

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_only_one_active_assignment_per_device(db: Session) -> None:
    department = _department(db)
    other = _department(db, "DEPT-B")
    device = _device(db, department)
    db.add(
        DeviceAssignment(
            device_id=device.id,
            department_id=other.id,
            effective_from=datetime.now(UTC),
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_reassignment_keeps_history_and_one_active_row(db: Session) -> None:
    department = _department(db)
    other = _department(db, "DEPT-B")
    device = _device(db, department)
    db.add(
        DeviceAssignment(
            device_id=device.id,
            department_id=other.id,
            effective_from=datetime.now(UTC),
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    assignment = db.query(DeviceAssignment).filter_by(device_id=device.id).one()
    assignment.effective_to = datetime.now(UTC)
    db.add(
        DeviceAssignment(
            device_id=device.id,
            department_id=other.id,
            effective_from=datetime.now(UTC),
        )
    )
    db.commit()

    rows = db.query(DeviceAssignment).filter_by(device_id=device.id).all()
    assert len(rows) == 2
    assert sum(1 for row in rows if row.effective_to is None) == 1


def test_one_active_credential_per_device(db: Session) -> None:
    device = _device(db)
    db.add(DeviceCredential(device_id=device.id, client_id="dev_a", secret_hash="x", version=1))
    db.commit()
    db.add(DeviceCredential(device_id=device.id, client_id="dev_b", secret_hash="x", version=2))

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.query(DeviceCredential).filter_by(device_id=device.id).one().revoked_at = datetime.now(UTC)
    db.commit()
    db.add(DeviceCredential(device_id=device.id, client_id="dev_c", secret_hash="x", version=2))
    db.commit()
    assert db.query(DeviceCredential).filter_by(device_id=device.id).count() == 2


def test_duplicate_client_scan_id_is_rejected(db: Session) -> None:
    department = _department(db)
    device = _device(db, department)
    _scan(db, device, department, "SCAN-DUP")

    second = Scan(
        device_id=device.id,
        department_id=department.id,
        client_scan_id="SCAN-DUP",
        schema_version="1.0",
        sample_id="Sample-0039",
        analyzed_at=datetime.now(UTC),
        raw_payload={},
        payload_sha256="1" * 64,
    )
    db.add(second)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_completed_scan_requires_finalized_at(db: Session) -> None:
    department = _department(db)
    device = _device(db, department)
    scan = _scan(db, device, department)
    scan.processing_status = ScanProcessingStatus.COMPLETED

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_measurement_bases_coexist_but_duplicates_do_not(db: Session) -> None:
    department = _department(db)
    device = _device(db, department)
    scan = _scan(db, device, department)

    db.add(
        Measurement(
            scan_id=scan.id,
            metric_code="head_rice",
            value=Decimal("50.68"),
            unit="percent",
            basis=MeasurementBasis.ESTIMATED_MASS_PERCENT,
            is_estimated=True,
        )
    )
    db.add(
        Measurement(
            scan_id=scan.id,
            metric_code="head_rice",
            value=Decimal("49.10"),
            unit="percent",
            basis=MeasurementBasis.COUNT_PERCENT,
            is_estimated=False,
        )
    )
    db.commit()

    db.add(
        Measurement(
            scan_id=scan.id,
            metric_code="head_rice",
            value=Decimal("1"),
            unit="percent",
            basis=MeasurementBasis.COUNT_PERCENT,
            is_estimated=False,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_measurement_unit_must_match_basis(db: Session) -> None:
    department = _department(db)
    device = _device(db, department)
    scan = _scan(db, device, department)
    db.add(
        Measurement(
            scan_id=scan.id,
            metric_code="avg_length",
            value=Decimal("5.25"),
            unit="percent",
            basis=MeasurementBasis.DIMENSION,
            is_estimated=False,
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_age_result_must_carry_information(db: Session) -> None:
    department = _department(db)
    device = _device(db, department)
    scan = _scan(db, device, department)
    db.add(AgeResult(scan_id=scan.id))

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_age_result_rejects_inverted_range(db: Session) -> None:
    department = _department(db)
    device = _device(db, department)
    scan = _scan(db, device, department)
    db.add(AgeResult(scan_id=scan.id, age_min_months=Decimal("10"), age_max_months=Decimal("8")))

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_age_result_is_optional_and_zero_is_preserved(db: Session) -> None:
    department = _department(db)
    device = _device(db, department)
    scan = _scan(db, device, department)
    assert db.query(AgeResult).filter_by(scan_id=scan.id).one_or_none() is None

    db.add(AgeResult(scan_id=scan.id, age_value_months=Decimal("0")))
    db.commit()
    stored = db.query(AgeResult).filter_by(scan_id=scan.id).one()
    assert stored.age_value_months == Decimal("0.00")


def test_notification_event_key_is_unique(db: Session) -> None:
    department = _department(db)
    db.add(
        Notification(
            department_id=department.id,
            event_type=NotificationEventType.SCAN_COMPLETED,
            event_key="scan_completed:abc",
            title="Scan completed",
        )
    )
    db.commit()
    db.add(
        Notification(
            department_id=department.id,
            event_type=NotificationEventType.SCAN_COMPLETED,
            event_key="scan_completed:abc",
            title="Duplicate",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_batches_are_unique_per_department_and_lot(db: Session) -> None:
    department = _department(db)
    other = _department(db, "DEPT-B")
    db.add(Batch(department_id=department.id, batch_code="BATCH-1", lot_code="LOT-A"))
    db.commit()
    db.add(Batch(department_id=other.id, batch_code="BATCH-1", lot_code="LOT-A"))
    db.commit()
    db.add(Batch(department_id=department.id, batch_code="BATCH-1", lot_code="LOT-A"))

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
