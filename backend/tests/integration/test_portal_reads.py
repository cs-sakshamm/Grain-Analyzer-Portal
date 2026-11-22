"""Portal read endpoints.

``/scans/history`` and ``/scans/notifications`` are single-segment paths, so they are
shadowed by ``/scans/{scan_id}`` unless the static routes are registered first. These
tests pin both the routing precedence and the ``{items: [...]}`` envelopes the frontend
consumes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Device, Measurement, Notification, NotificationRecipient, Scan
from app.models.enums import (
    MeasurementBasis,
    NotificationEventType,
    NotificationSeverity,
    QualityVerdict,
    ScanProcessingStatus,
)

from .conftest import PASSWORD, login, make_department, make_user


def _completed_scan(
    db: Session, department_id: uuid.UUID, user_id: uuid.UUID, *, uid: str = "PORTAL-001"
) -> Scan:
    device = Device(device_uid=uid, serial_number=f"SN-{uid}")
    db.add(device)
    db.flush()

    now = datetime.now(UTC)
    scan = Scan(
        device_id=device.id,
        department_id=department_id,
        client_scan_id=f"{uid}-1",
        schema_version="1.0",
        sample_id=f"SAMPLE-{uid}",
        batch_code="BATCH-PORTAL",
        analyzed_at=now,
        processing_status=ScanProcessingStatus.COMPLETED,
        quality_verdict=QualityVerdict.PASS,
        finalized_at=now,
        raw_payload={"analysis": {"grain_count": 10}},
        payload_sha256="0" * 64,
    )
    db.add(scan)
    db.flush()

    db.add(
        Measurement(
            scan_id=scan.id,
            metric_code="head_rice",
            metric_label="Head rice",
            value=Decimal("50.5"),
            unit="percent",
            basis=MeasurementBasis.COUNT_PERCENT,
            is_estimated=False,
        )
    )
    notification = Notification(
        department_id=department_id,
        scan_id=scan.id,
        event_type=NotificationEventType.SCAN_COMPLETED,
        event_key=f"scan_completed:{scan.id}",
        severity=NotificationSeverity.INFO,
        title="Scan completed",
    )
    db.add(notification)
    db.flush()
    db.add(NotificationRecipient(notification_id=notification.id, user_id=user_id))
    db.commit()
    db.refresh(scan)
    return scan


def _member(db: Session, email: str = "reader@example.test") -> tuple[uuid.UUID, uuid.UUID]:
    department = make_department(db, "READ-A")
    user = make_user(db, email)
    from .conftest import add_membership

    add_membership(db, user, department)
    return department.id, user.id


def test_scan_history_is_not_parsed_as_a_scan_id(client: TestClient, db: Session) -> None:
    department_id, user_id = _member(db)
    _completed_scan(db, department_id, user_id)
    headers = login(client, "reader@example.test", PASSWORD)

    response = client.get("/api/v1/scans/history", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["measurements"][0]["basis"] == "count_percent"
    assert body["items"][0]["processing_status"] == "completed"


def test_notifications_returns_the_current_users_inbox(client: TestClient, db: Session) -> None:
    department_id, user_id = _member(db)
    _completed_scan(db, department_id, user_id)
    headers = login(client, "reader@example.test", PASSWORD)

    response = client.get("/api/v1/scans/notifications", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["severity"] == "info"


def test_report_listing_returns_an_items_envelope(client: TestClient, db: Session) -> None:
    department_id, user_id = _member(db)
    _completed_scan(db, department_id, user_id)
    headers = login(client, "reader@example.test", PASSWORD)

    response = client.get("/api/v1/scans/analytics/reports", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["has_report"] is False


def test_history_stays_department_scoped(client: TestClient, db: Session) -> None:
    department_id, user_id = _member(db)
    _completed_scan(db, department_id, user_id)
    other = make_department(db, "READ-B")
    headers = login(client, "reader@example.test", PASSWORD)

    response = client.get(
        f"/api/v1/scans/history?department_id={other.id}",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
