"""Development-only deterministic seed data for Rice Age Portal.

This utility creates demo departments, users, devices, scans and related records
using the existing SQLAlchemy models and API contracts. It is intentionally
idempotent and guarded against production use.

Run: python dev_seed.py

DO NOT run against production databases.
"""

import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, func

from app.core.config import get_settings, Settings
from app.db.session import get_engine, get_session_factory
from app.models.analysis import AgeResult, Measurement, QualityEvaluation
from app.models.device import Device, DeviceAssignment
from app.models.enums import (
    MeasurementBasis,
    QualityVerdict,
    ScanProcessingStatus,
    UploadStatus,
    AgeValidationStatus,
)
from app.models.files import ScanFile, UploadAttempt
from app.models.identity import User, Membership
from app.models.organization import Department
from app.models.notifications import Notification, NotificationRecipient
from app.services.auth_service import hash_password
from app.services.scan_service import utcnow
from app.storage import StorageError, StoragePort, build_storage, get_storage


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def db_session():
    """Return a new SQLAlchemy session bound to the engine."""
    factory = get_session_factory()
    return factory()


def add_if_not_exists(session, model, **filters):
    """Add an instance only if no existing row matches the filters."""
    instance = session.query(model).filter_by(**filters).first()
    if instance:
        return instance
    new_instance = model(**filters)
    session.add(new_instance)
    session.flush()
    return new_instance


def create_departments(session):
    """Create two demo departments."""
    dept_a = add_if_not_exists(
        session, Department, code="DEPT-A", name="Department A", location="Building 1"
    )
    dept_b = add_if_not_exists(
        session, Department, code="DEPT-B", name="Department B", location="Building 2"
    )
    session.commit()
    return dept_a, dept_b


def create_users(session, dept_a, dept_b):
    """Create a Super Admin, a Department Admin, and a Department User."""
    super_admin = add_if_not_exists(
        session,
        User,
        email="super-admin@test.local",
        password=hash_password("SuperAdmin123!"),
        full_name="Super Admin",
        is_super_admin=True,
    )

    admin_user = add_if_not_exists(
        session,
        User,
        email="admin@test.local",
        password=hash_password("Admin123!"),
        full_name="Department Admin",
    )

    regular_user = add_if_not_exists(
        session,
        User,
        email="user@test.local",
        password=hash_password("User123!"),
        full_name="Department User",
    )

    # Membership: super admin has no department limitation
    admin_membership = Membership(
        user_id=admin_user.id,
        department_id=dept_a.id,
        role="department_admin",
        is_active=True,
    )
    user_membership = Membership(
        user_id=regular_user.id,
        department_id=dept_a.id,
        role="department_user",
        is_active=True,
    )
    session.add_all([admin_membership, user_membership])
    session.commit()
    return super_admin, admin_user, regular_user


def create_devices(session, dept_a, dept_b):
    """Create two demo devices with assignments."""
    device_1 = add_if_not_exists(
        session,
        Device,
        device_uid="GRAIN-001",
        serial_number="SN-001",
        friendly_name="Mill #1",
        model="Model 4000",
        hardware_revision="1.0",
        firmware_version="2.1.0",
        installation_location="Line A",
        status="active",
    )

    device_2 = add_if_not_exists(
        session,
        Device,
        device_uid="GRAIN-002",
        serial_number="SN-002",
        friendly_name="Mill #2",
        model="Model 4200",
        hardware_revision="1.1",
        firmware_version="2.3.0",
        installation_location="Line B",
        status="active",
    )

    # Assignment: device 1 -> dept A, device 2 -> dept B
    assignment_1 = DeviceAssignment(
        device_id=device_1.id,
        department_id=dept_a.id,
        effective_from=datetime.now(UTC),
        assigned_by_user_id=None,
        reason="Initial assignment",
    )
    assignment_2 = DeviceAssignment(
        device_id=device_2.id,
        department_id=dept_b.id,
        effective_from=datetime.now(UTC),
        assigned_by_user_id=None,
        reason="Initial assignment",
    )
    session.add_all([assignment_1, assignment_2])
    session.commit()
    return device_1, device_2


def create_scans(session, device_1, device_2, dept_a, dept_b):
    """Create demo scans with varied processing statuses and measurements."""
    from app.models.analysis import AgeResult  # local import

    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # Scan 1: completed, with age result, count_percent measurements
    scan1 = Scan(
        device_id=device_1.id,
        department_id=dept_a.id,
        client_scan_id="SCAN-001",
        schema_version="1.0",
        sample_id="SAMPLE-001",
        batch_code="BATCH-001",
        lot_code="LOT-001",
        variety="Long-grain",
        analyzed_at=week_ago + timedelta(hours=2),
        received_at=week_ago + timedelta(hours=1),
        processing_status=ScanProcessingStatus.COMPLETED,
        quality_verdict=QualityVerdict.PASS,
        ruleset_version="v1.2",
        certification_status="certified",
        raw_payload={"analysis": {"grain_count": 2500}, "variety": "Long-grain"},
        payload_sha256="abc123",
    )
    session.add(scan1)
    session.flush()

    # Measurements for scan 1
    meas1_a = Measurement(
        scan_id=scan1.id,
        metric_code="grain_count",
        metric_label="Grain Count",
        value=2485,
        unit="percent",
        basis=MeasurementBasis.COUNT_PERCENT,
        is_estimated=False,
    )
    meas1_b = Measurement(
        scan_id=scan1.id,
        metric_code="broken_kernels",
        metric_label="Broken Kernels",
        value=2.5,
        unit="percent",
        basis=MeasurementBasis.COUNT_PERCENT,
        is_estimated=False,
    )
    session.add_all([meas1_a, meas1_b])

    # Age result for scan 1
    age1 = AgeResult(
        scan_id=scan1.id,
        age_value_months=12,
        age_min_months=10,
        age_max_months=14,
        age_category="mature",
        proportion_percent=85.5,
        unit="months",
        method="monte-carlo",
        model_version="v1.0",
        validation_status=AgeValidationStatus.VALIDATED,
    )
    session.add(age1)

    # Scan file (report PDF)
    scan_file_pdf = ScanFile(
        scan_id=scan1.id,
        role="report_pdf",
        storage_key=f"scans/{scan1.id}/report.pdf",
        original_filename="scan-001-report.pdf",
        mime_type="application/pdf",
        size_bytes=102400,
        sha256="def456",
        upload_status=UploadStatus.VERIFIED,
        verified_at=now,
    )
    session.add(scan_file_pdf)

    # Notification for scan completion
    notif1 = Notification(
        department_id=dept_a.id,
        scan_id=scan1.id,
        event_type="scan_completed",
        severity="info",
        title=f"Scan completed for {scan1.sample_id}",
        body="A device analysis submission finished processing and is available.",
    )
    session.add(notif1)

    # Scan 2: completed, no age result, physical_mass_percent measurements
    scan2 = Scan(
        device_id=device_2.id,
        department_id=dept_b.id,
        client_scan_id="SCAN-002",
        schema_version="1.0",
        sample_id="SAMPLE-002",
        batch_code="BATCH-002",
        lot_code="LOT-002",
        variety="Medium-grain",
        analyzed_at=now - timedelta(hours=1),
        received_at=now - timedelta(days=1),
        processing_status=ScanProcessingStatus.COMPLETED,
        quality_verdict=QualityVerdict.FLAGGED,
        raw_payload={"analysis": {"grain_count": 1800}, "variety": "Medium-grain"},
        payload_sha256="ghi789",
    )
    session.add(scan2)
    session.flush()

    meas2_a = Measurement(
        scan_id=scan2.id,
        metric_code="physical_mass_percent",
        metric_label="Physical Mass %",
        value=13.2,
        unit="percent",
        basis=MeasurementBasis.PHYSICAL_MASS_PERCENT,
        is_estimated=False,
    )
    meas2_b = Measurement(
        scan_id=scan2.id,
        metric_code="moisture_content",
        metric_label="Moisture Content",
        value=12.8,
        unit="percent",
        basis=MeasurementBasis.PHYSICAL_MASS_PERCENT,
        is_estimated=False,
    )
    session.add_all([meas2_a, meas2_b])

    # Scan 3: verifying, no quality verdict yet
    scan3 = Scan(
        device_id=device_1.id,
        department_id=dept_a.id,
        client_scan_id="SCAN-003",
        schema_version="1.0",
        sample_id="SAMPLE-003",
        variety="Short-grain",
        analyzed_at=month_ago + timedelta(days=3),
        received_at=month_ago + timedelta(days=2),
        processing_status=ScanProcessingStatus.VERIFYING,
        raw_payload={"analysis": {"grain_count": 3200}, "variety": "Short-grain"},
        payload_sha256="jkl012",
    )
    session.add(scan3)
    session.flush()

    # Scan 4: received, oldest
    scan4 = Scan(
        device_id=device_2.id,
        department_id=dept_b.id,
        client_scan_id="SCAN-004",
        schema_version="1.0",
        sample_id="SAMPLE-004",
        variety="Long-grain",
        analyzed_at=month_ago - timedelta(days=5),
        received_at=month_ago - timedelta(days=6),
        processing_status=ScanProcessingStatus.RECEIVED,
        raw_payload={"analysis": {"grain_count": 2100}, "variety": "Long-grain"},
        payload_sha256="mno345",
    )
    session.add(scan4)
    session.flush()

    session.commit()
    return scan1, scan2, scan3, scan4


def create_demo_data():
    """Full seed: departments, users, devices, scans."""
    session = db_session()

    try:
        print("Creating departments...")
        dept_a, dept_b = create_departments(session)

        print("Creating users...")
        super_admin, admin_user, regular_user = create_users(session, dept_a, dept_b)

        print("Creating devices...")
        device_1, device_2 = create_devices(session, dept_a, dept_b)

        print("Creating scans...")
        scan1, scan2, scan3, scan4 = create_scans(session, device_1, device_2, dept_a, dept_b)

        # Create additional demo records (quality evaluations, upload attempts, etc.)
        print("Creating quality evaluations...")
        eval1 = QualityEvaluation(
            scan_id=scan1.id,
            verdict=QualityVerdict.PASS,
            evaluated_at=datetime.now(UTC),
            evaluated_by_user_id=super_admin.id,
            notes="Initial pass",
        )
        session.add(eval1)
        session.commit()

        # Set storage
        settings = get_settings()
        storage: StoragePort = build_storage(settings)

        # Store the report PDF
        pdf_content = b"%PDF-1.4 fake pdf content for scan 001"
        try:
            storage.save(f"scans/{scan1.id}/report.pdf", pdf_content, content_type="application/pdf")
            print(f"Stored report PDF for scan {scan1.id}")
        except StorageError:
            print(f"Note: could not store PDF (storage may not be available)")

        print("\n=== Demo data created successfully ===")
        print(f"Departments: DEPT-A (Department A), DEPT-B (Department B)")
        print(f"Users: super-admin@test.local, admin@test.local, user@test.local")
        print(f"Devices: GRAIN-001 (Dept A), GRAIN-002 (Dept B)")
        print(f"Scans: {scan1.sample_id} (completed, with age), {scan2.sample_id} (completed, flagged),")
        print(f"       {scan3.sample_id} (verifying), {scan4.sample_id} (received)")
        print("\nLogin credentials (development-only):")
        print("  super-admin: SuperAdmin123!")
        print("  admin: Admin123!")
        print("  user: User123!")

    except Exception as e:
        session.rollback()
        print(f"Error creating demo data: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    # Development-only guard
    if os.getenv("RICE_AGE_ENV") == "production":
        print("ERROR: Refusing to seed production environment.")
        exit(1)
    create_demo_data()