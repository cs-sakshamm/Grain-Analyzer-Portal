"""Development-only deterministic seed data for Rice Age Portal.

This utility creates demo departments, users, devices, scans and related records
using the existing SQLAlchemy models and API contracts. It is intentionally
idempotent and guarded against production use.

Run: python dev_seed.py

DO NOT run against production databases.
"""

import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import func

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.analysis import AgeResult, Measurement, QualityEvaluation
from app.models.device import Device, DeviceAssignment
from app.models.enums import (
    AgeValidationStatus,
    MeasurementBasis,
    QualityVerdict,
    ScanProcessingStatus,
    UploadStatus,
)
from app.models.files import ScanFile
from app.models.identity import Membership, User
from app.models.notifications import Notification
from app.models.organization import Department
from app.services.auth_service import hash_password
from app.storage import StorageError, StoragePort, build_storage

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def db_session():
    """Return a new SQLAlchemy session bound to the engine."""
    factory = get_session_factory()
    return factory()


def add_if_not_exists(session, model_class, **filters):
    """Add an instance only if its stable natural key is not already present."""
    # Do not include mutable/defaulted fields (password hashes, locations) in
    # idempotency lookups. Those fields otherwise turn a repeat seed into a
    # unique-key violation.
    if model_class == User:
        email = filters.get("email")
        instance = (
            session.query(model_class).filter(func.lower(User.email) == email.lower()).first()
            if email
            else None
        )
    elif model_class == Department:
        code = filters.get("code")
        instance = (
            session.query(model_class).filter(func.lower(Department.code) == code.lower()).first()
            if code
            else None
        )
    elif model_class == Device:
        instance = session.query(model_class).filter_by(device_uid=filters["device_uid"]).first()
    else:
        instance = session.query(model_class).filter_by(**filters).first()
    if instance:
        return instance
    new_instance = model_class(**filters)
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
        password_hash=hash_password("SuperAdmin123!"),
        full_name="Super Admin",
        is_super_admin=True,
    )

    admin_user = add_if_not_exists(
        session,
        User,
        email="admin@test.local",
        password_hash=hash_password("Admin123!"),
        full_name="Department Admin",
    )

    regular_user = add_if_not_exists(
        session,
        User,
        email="user@test.local",
        password_hash=hash_password("User123!"),
        full_name="Department User",
    )

    # Membership: super admin has no department limitation (idempotent via add_if_not_exists)
    add_if_not_exists(
        session,
        Membership,
        user_id=admin_user.id,
        department_id=dept_a.id,
        role="department_admin",
    )
    add_if_not_exists(
        session,
        Membership,
        user_id=regular_user.id,
        department_id=dept_a.id,
        role="department_user",
    )
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

    # Assignment: device 1 -> dept A, device 2 -> dept B (idempotent via add_if_not_exists)
    add_if_not_exists(
        session,
        DeviceAssignment,
        device_id=device_1.id,
        department_id=dept_a.id,
    )
    add_if_not_exists(
        session,
        DeviceAssignment,
        device_id=device_2.id,
        department_id=dept_b.id,
    )
    return device_1, device_2


def create_scans(session, device_1, device_2, dept_a, dept_b):
    """Create demo scans with varied processing statuses and measurements."""
    from app.models.analysis import Scan  # local import

    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # Helper: get or create scan respecting unique constraint (device_id, client_scan_id)
    def get_or_create_scan(filters, new_instance):
        instance = (
            session.query(Scan)
            .filter_by(device_id=filters["device_id"], client_scan_id=filters["client_scan_id"])
            .first()
        )
        if instance:
            return instance
        session.add(new_instance)
        session.flush()
        return new_instance

    # Scan 1: completed, with age result, count_percent measurements
    scan1 = get_or_create_scan(
        {"device_id": device_1.id, "client_scan_id": "SCAN-001"},
        Scan(
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
            finalized_at=week_ago,
            raw_payload={"analysis": {"grain_count": 2500}, "variety": "Long-grain"},
            payload_sha256="abc123",
        ),
    )

    # Measurements for scan 1 (idempotent via add_if_not_exists)
    add_if_not_exists(
        session,
        Measurement,
        scan_id=scan1.id,
        metric_code="grain_count",
        metric_label="Grain Count",
        value=2485,
        unit="percent",
        basis=MeasurementBasis.COUNT_PERCENT,
        is_estimated=False,
    )
    add_if_not_exists(
        session,
        Measurement,
        scan_id=scan1.id,
        metric_code="broken_kernels",
        metric_label="Broken Kernels",
        value=2.5,
        unit="percent",
        basis=MeasurementBasis.COUNT_PERCENT,
        is_estimated=False,
    )

    # Age result for scan 1 (idempotent via add_if_not_exists)
    add_if_not_exists(
        session,
        AgeResult,
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

    # Scan file (report PDF) (idempotent via storage_key check)
    existing_file = (
        session.query(ScanFile).filter_by(storage_key=f"scans/{scan1.id}/report.pdf").first()
    )
    if existing_file:
        scan_file_pdf = existing_file
    else:
        scan_file_pdf = ScanFile(
            scan_id=scan1.id,
            role="report_pdf",
            storage_backend="local",
            storage_key=f"scans/{scan1.id}/report.pdf",
            original_filename="scan-001-report.pdf",
            mime_type="application/pdf",
            size_bytes=102400,
            sha256="def456",
            upload_status=UploadStatus.VERIFIED,
            verified_at=now,
        )
        session.add(scan_file_pdf)
        session.flush()
    session.add(scan_file_pdf)

    # Notification for scan completion (idempotent via event_key check)
    existing_notif = session.query(Notification).filter_by(event_key=str(scan1.id)).first()
    if not existing_notif:
        notif1 = Notification(
            department_id=dept_a.id,
            scan_id=scan1.id,
            event_type="scan_completed",
            event_key=str(scan1.id),
            severity="info",
            title=f"Scan completed for {scan1.sample_id}",
            body="A device analysis submission finished processing and is available.",
        )
        session.add(notif1)
    else:
        notif1 = existing_notif

    # Scan 2: completed, no age result, physical_mass_percent measurements
    scan2 = get_or_create_scan(
        {"device_id": device_2.id, "client_scan_id": "SCAN-002"},
        Scan(
            device_id=device_2.id,
            department_id=dept_b.id,
            client_scan_id="SCAN-002",
            schema_version="1.0",
            sample_id="SAMPLE-002",
            batch_code="BATCH-002",
            lot_code="LOT-002",
            variety="Medium-grain",
            analyzed_at=now - timedelta(hours=1),
            received_at=now - timedelta(hours=1),
            processing_status=ScanProcessingStatus.COMPLETED,
            quality_verdict=QualityVerdict.FLAGGED,
            finalized_at=now - timedelta(days=1),
            raw_payload={"analysis": {"grain_count": 1800}, "variety": "Medium-grain"},
            payload_sha256="ghi789",
        ),
    )
    session.add(scan2)
    session.flush()

    add_if_not_exists(
        session,
        Measurement,
        scan_id=scan2.id,
        metric_code="physical_mass_percent",
        metric_label="Physical Mass %",
        value=13.2,
        unit="percent",
        basis=MeasurementBasis.PHYSICAL_MASS_PERCENT,
        is_estimated=False,
    )
    add_if_not_exists(
        session,
        Measurement,
        scan_id=scan2.id,
        metric_code="moisture_content",
        metric_label="Moisture Content",
        value=12.8,
        unit="percent",
        basis=MeasurementBasis.PHYSICAL_MASS_PERCENT,
        is_estimated=False,
    )

    # Scan 3: verifying, no quality verdict yet
    scan3 = get_or_create_scan(
        {"device_id": device_1.id, "client_scan_id": "SCAN-003"},
        Scan(
            device_id=device_1.id,
            department_id=dept_a.id,
            client_scan_id="SCAN-003",
            schema_version="1.0",
            sample_id="SAMPLE-003",
            variety="Short-grain",
            analyzed_at=month_ago + timedelta(days=2),
            received_at=month_ago + timedelta(days=2),
            processing_status=ScanProcessingStatus.VERIFYING,
            raw_payload={"analysis": {"grain_count": 3200}, "variety": "Short-grain"},
            payload_sha256="jkl012",
        ),
    )
    session.add(scan3)
    session.flush()

    # Scan 4: received, oldest
    scan4 = get_or_create_scan(
        {"device_id": device_2.id, "client_scan_id": "SCAN-004"},
        Scan(
            device_id=device_2.id,
            department_id=dept_b.id,
            client_scan_id="SCAN-004",
            schema_version="1.0",
            sample_id="SAMPLE-004",
            variety="Long-grain",
            analyzed_at=month_ago - timedelta(days=6),
            received_at=month_ago - timedelta(days=6),
            processing_status=ScanProcessingStatus.RECEIVED,
            raw_payload={"analysis": {"grain_count": 2100}, "variety": "Long-grain"},
            payload_sha256="mno345",
        ),
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
        existing_eval = (
            session.query(QualityEvaluation)
            .filter(
                QualityEvaluation.scan_id == scan1.id,
                QualityEvaluation.parameter_code == "moisture_content",
                QualityEvaluation.basis == MeasurementBasis.PHYSICAL_MASS_PERCENT,
            )
            .first()
        )
        if not existing_eval:
            eval1 = QualityEvaluation(
                scan_id=scan1.id,
                parameter_code="moisture_content",
                basis=MeasurementBasis.PHYSICAL_MASS_PERCENT,
                status=QualityVerdict.PASS,
                measured_value=12.5,
            )
            session.add(eval1)
            session.commit()
        else:
            eval1 = existing_eval

        # Set storage
        settings = get_settings()
        storage: StoragePort = build_storage(settings)

        # Store the report PDF
        pdf_content = b"%PDF-1.4 fake pdf content for scan 001"
        try:
            storage.save(
                f"scans/{scan1.id}/report.pdf", pdf_content, content_type="application/pdf"
            )
            print(f"Stored report PDF for scan {scan1.id}")
        except StorageError:
            print("Note: could not store PDF (storage may not be available)")

        print("\n=== Demo data created successfully ===")
        print("Departments: DEPT-A (Department A), DEPT-B (Department B)")
        print("Users: super-admin@test.local, admin@test.local, user@test.local")
        print("Devices: GRAIN-001 (Dept A), GRAIN-002 (Dept B)")
        print(f"Scans: {scan1.sample_id} (completed, with age),")
        print(f"       {scan2.sample_id} (completed, flagged),")
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
