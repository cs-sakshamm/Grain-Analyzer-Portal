"""Device ingestion, idempotency, attachment verification and portal access."""

from __future__ import annotations

import hashlib
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Device, Scan
from app.models.enums import DeviceStatus, ScanProcessingStatus

from .conftest import (
    PDF_BYTES,
    PNG_BYTES,
    issue_device_token,
    login,
    make_department,
    register_device,
    sample_payload,
    upload_attachment,
)


def _device_token(
    client: TestClient, seeded: dict, uid: str = "RICE-DEVICE-010"
) -> tuple[str, str]:
    headers = login(client, seeded["super_admin"])
    device = register_device(client, headers, seeded["department_a"], uid)
    return device["id"], issue_device_token(client, headers, device["id"])


def _submit(client: TestClient, token: str, payload: dict) -> dict:
    response = client.post(
        "/api/v1/device/scans",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def test_scan_submission_uses_assignment_department_and_stores_basis(
    client: TestClient, seeded: dict, db: Session
) -> None:
    _, token = _device_token(client, seeded)
    accepted = _submit(client, token, sample_payload())

    assert accepted["processing_status"] == "awaiting_files"
    assert accepted["required_attachments"] == ["report_pdf", "bottom_image"]
    scan = db.get(Scan, uuid.UUID(accepted["scan_id"]))
    assert scan is not None
    assert scan.department_id == seeded["department_a"]
    bases = {measurement.basis.value for measurement in scan.measurements}
    assert bases == {"estimated_mass_percent", "count_percent", "dimension"}
    assert scan.age_result is not None
    assert scan.age_result.age_min_months == 8


def test_identical_replay_returns_the_same_scan(client: TestClient, seeded: dict) -> None:
    _, token = _device_token(client, seeded)
    payload = sample_payload()

    first = _submit(client, token, payload)
    replay = client.post(
        "/api/v1/device/scans",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert replay.status_code == 200
    assert replay.json()["scan_id"] == first["scan_id"]
    assert replay.json()["replayed"] is True


def test_conflicting_replay_returns_409(client: TestClient, seeded: dict) -> None:
    _, token = _device_token(client, seeded)
    _submit(client, token, sample_payload())

    payload = sample_payload()
    payload["analysis"]["grain_count"] = 999
    conflict = client.post(
        "/api/v1/device/scans",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "scan_conflict"


def test_payload_department_is_rejected_not_trusted(client: TestClient, seeded: dict) -> None:
    _, token = _device_token(client, seeded)
    payload = sample_payload()
    payload["department_id"] = str(seeded["department_b"])

    response = client.post(
        "/api/v1/device/scans",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_device_without_assignment_is_rejected(client: TestClient, db: Session) -> None:
    department = make_department(db)
    device = Device(
        device_uid="UNASSIGNED-1",
        serial_number="SN-UNASSIGNED-1",
        status=DeviceStatus.ACTIVE,
    )
    db.add(device)
    db.commit()

    from app.core.security import hash_password
    from app.models import DeviceCredential

    credential_id = "dev_unassigned"
    secret = "unassigned-secret-value"
    db.add(
        DeviceCredential(
            device_id=device.id,
            client_id=credential_id,
            secret_hash=hash_password(secret),
            version=1,
        )
    )
    db.commit()

    token = client.post(
        "/api/v1/device-auth/token",
        json={
            "grant_type": "client_credentials",
            "client_id": credential_id,
            "client_secret": secret,
        },
    )
    assert token.status_code == 403
    assert token.json()["error"]["code"] == "device_unassigned"


def test_finalize_requires_configured_attachments_and_is_idempotent(
    client: TestClient, seeded: dict, db: Session
) -> None:
    _, token = _device_token(client, seeded)
    accepted = _submit(client, token, sample_payload())
    scan_id = accepted["scan_id"]
    device_headers = {"Authorization": f"Bearer {token}"}

    premature = client.post(f"/api/v1/device/scans/{scan_id}/finalize", headers=device_headers)
    assert premature.status_code == 409
    assert premature.json()["error"]["code"] == "missing_attachments"
    assert set(premature.json()["error"]["details"]["roles"]) == {"report_pdf", "bottom_image"}

    upload_attachment(client, token, scan_id, "report_pdf", PDF_BYTES, "application/pdf", "s.pdf")
    upload_attachment(client, token, scan_id, "bottom_image", PNG_BYTES, "image/png", "bottom.png")

    finalized = client.post(f"/api/v1/device/scans/{scan_id}/finalize", headers=device_headers)
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["processing_status"] == "completed"
    assert finalized.json()["quality_verdict"] == "flagged"
    assert finalized.json()["notifications_created"] == 2

    again = client.post(f"/api/v1/device/scans/{scan_id}/finalize", headers=device_headers)
    assert again.status_code == 200
    assert again.json()["notifications_created"] == 0

    status = client.get(f"/api/v1/device/scans/{scan_id}/status", headers=device_headers)
    assert status.status_code == 200
    assert status.json()["processing_status"] == "completed"
    assert {item["role"] for item in status.json()["attachments"]} == {
        "report_pdf",
        "bottom_image",
    }

    scan = db.get(Scan, uuid.UUID(scan_id))
    assert scan is not None
    assert scan.processing_status is ScanProcessingStatus.COMPLETED
    assert scan.finalized_at is not None


def test_checksum_mismatch_is_rejected(client: TestClient, seeded: dict) -> None:
    _, token = _device_token(client, seeded)
    scan_id = _submit(client, token, sample_payload())["scan_id"]
    headers = {"Authorization": f"Bearer {token}"}

    prepare = client.post(
        f"/api/v1/device/scans/{scan_id}/attachments/prepare",
        headers=headers,
        json={
            "role": "report_pdf",
            "content_type": "application/pdf",
            "size_bytes": len(PDF_BYTES),
            "sha256": hashlib.sha256(b"different").hexdigest(),
            "filename": "report.pdf",
        },
    )
    assert prepare.status_code == 200
    target = prepare.json()
    upload = client.put(
        target["url"],
        content=PDF_BYTES,
        headers={**headers, "Content-Type": "application/pdf"},
    )

    assert upload.status_code == 422
    assert upload.json()["error"]["code"] == "checksum_mismatch"


def test_portal_latest_returns_completed_scan_and_hides_incomplete(
    client: TestClient, seeded: dict
) -> None:
    _, token = _device_token(client, seeded)
    completed_id = _submit(client, token, sample_payload("SCAN-COMPLETE"))["scan_id"]
    upload_attachment(
        client, token, completed_id, "report_pdf", PDF_BYTES, "application/pdf", "s.pdf"
    )
    upload_attachment(client, token, completed_id, "bottom_image", PNG_BYTES, "image/png", "b.png")
    client.post(
        f"/api/v1/device/scans/{completed_id}/finalize",
        headers={"Authorization": f"Bearer {token}"},
    )

    # A newer incomplete submission must not displace the completed one.
    _submit(client, token, sample_payload("SCAN-NEWER"))

    headers = login(client, seeded["user_a"])
    latest = client.get("/api/v1/scans/latest", headers=headers)
    assert latest.status_code == 200, latest.text
    body = latest.json()["scan"]
    assert body["id"] == completed_id
    assert body["processing_status"] == "completed"
    bases = {(row["metric_code"], row["basis"]) for row in body["measurements"]}
    assert ("head_rice", "estimated_mass_percent") in bases
    assert ("head_rice", "count_percent") in bases
    assert body["age"]["age_category"] == "8-10 Months"


def test_cross_department_scan_and_report_are_not_visible(client: TestClient, seeded: dict) -> None:
    _, token = _device_token(client, seeded)
    scan_id = _submit(client, token, sample_payload())["scan_id"]
    upload_attachment(client, token, scan_id, "report_pdf", PDF_BYTES, "application/pdf", "s.pdf")
    upload_attachment(client, token, scan_id, "bottom_image", PNG_BYTES, "image/png", "b.png")
    client.post(
        f"/api/v1/device/scans/{scan_id}/finalize",
        headers={"Authorization": f"Bearer {token}"},
    )

    headers_b = login(client, seeded["user_b"])
    assert client.get(f"/api/v1/scans/{scan_id}", headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/scans/{scan_id}/report", headers=headers_b).status_code == 404
    assert client.get("/api/v1/scans/latest", headers=headers_b).status_code == 204

    headers_a = login(client, seeded["user_a"])
    report = client.get(f"/api/v1/scans/{scan_id}/report", headers=headers_a)
    assert report.status_code == 200
    download = client.get(report.json()["url"], headers=headers_a)
    assert download.status_code == 200
    assert download.content == PDF_BYTES
    assert download.headers["content-type"] == "application/pdf"


def test_no_age_result_is_reported_as_null(client: TestClient, seeded: dict) -> None:
    _, token = _device_token(client, seeded)
    scan_id = _submit(client, token, sample_payload("SCAN-NO-AGE", with_age=False))["scan_id"]
    upload_attachment(client, token, scan_id, "report_pdf", PDF_BYTES, "application/pdf", "s.pdf")
    upload_attachment(client, token, scan_id, "bottom_image", PNG_BYTES, "image/png", "b.png")
    client.post(
        f"/api/v1/device/scans/{scan_id}/finalize",
        headers={"Authorization": f"Bearer {token}"},
    )

    detail = client.get(f"/api/v1/scans/{scan_id}", headers=login(client, seeded["user_a"]))
    assert detail.status_code == 200
    assert detail.json()["scan"]["age"] is None


def test_historical_department_snapshot_survives_reassignment(
    client: TestClient, seeded: dict, db: Session
) -> None:
    device_id, token = _device_token(client, seeded)
    old_scan_id = _submit(client, token, sample_payload("SCAN-BEFORE-MOVE"))["scan_id"]

    super_headers = login(client, seeded["super_admin"])
    moved = client.post(
        f"/api/v1/admin/devices/{device_id}/assignments",
        headers=super_headers,
        json={"department_id": str(seeded["department_b"])},
    )
    assert moved.status_code == 201

    old_scan = db.get(Scan, uuid.UUID(old_scan_id))
    assert old_scan is not None
    assert old_scan.department_id == seeded["department_a"]

    # The device now submits into department B.
    new_scan_id = _submit(client, token, sample_payload("SCAN-AFTER-MOVE"))["scan_id"]
    new_scan = db.get(Scan, uuid.UUID(new_scan_id))
    assert new_scan is not None
    assert new_scan.department_id == seeded["department_b"]

    # Department A cannot see the post-move scan, and B cannot see the pre-move one.
    headers_a = login(client, seeded["user_a"])
    headers_b = login(client, seeded["user_b"])
    assert client.get(f"/api/v1/scans/{new_scan_id}", headers=headers_a).status_code == 404
    assert client.get(f"/api/v1/scans/{old_scan_id}", headers=headers_b).status_code == 404
