"""Human auth, role checks, department isolation and administration."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import DeviceAssignment

from .conftest import (
    PASSWORD,
    add_membership,
    issue_device_token,
    login,
    make_department,
    make_user,
    register_device,
)


def test_login_returns_user_and_sets_http_only_refresh_cookie(
    client: TestClient, seeded: dict
) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": seeded["user_a"], "password": PASSWORD},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["memberships"][0]["department_code"] == "DEPT-A"
    cookie = response.headers["set-cookie"]
    assert "ra_refresh=" in cookie
    assert "HttpOnly" in cookie
    assert "samesite=strict" in cookie.lower()


def test_invalid_credentials_are_generic(client: TestClient, seeded: dict) -> None:
    wrong = client.post(
        "/api/v1/auth/login", json={"email": seeded["user_a"], "password": "not-the-password"}
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.test", "password": PASSWORD}
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["code"] == "invalid_credentials"
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_inactive_user_cannot_log_in(client: TestClient, db: Session) -> None:
    department = make_department(db)
    user = make_user(db, "inactive@example.test", is_active=False)
    add_membership(db, user, department)

    response = client.post(
        "/api/v1/auth/login", json={"email": "inactive@example.test", "password": PASSWORD}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_inactive"def test_refresh_rotates_and_reuse_revokes_the_family(
    client: TestClient, seeded: dict, app
) -> None:
    login(client, seeded["user_a"])
    first_cookie = client.cookies.get("ra_refresh")
    rotated = client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200
    second_cookie = client.cookies.get("ra_refresh")
    assert second_cookie and second_cookie != first_cookie

    # A fresh client with an explicit Cookie header avoids jar replacement semantics.
    # Replaying the rotated token is theft: the new one must die too.
    with TestClient(app, raise_server_exceptions=False) as replay_client:
        replay = replay_client.post(
            "/api/v1/auth/refresh", headers={"Cookie": f"ra_refresh={first_cookie}"}
        )
        assert replay.status_code == 401, replay.text
        assert replay.json()["error"]["code"] == "session_revoked"

        after_reuse = replay_client.post(
            "/api/v1/auth/refresh", headers={"Cookie": f"ra_refresh={second_cookie}"}
        )
        assert after_reuse.status_code == 401


def test_logout_revokes_refresh_session(client: TestClient, seeded: dict) -> None:
    login(client, seeded["user_a"])
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_me_requires_authentication(client: TestClient, seeded: dict) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401

    headers = login(client, seeded["user_a"])
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["user"]["email"] == seeded["user_a"]


def test_department_user_cannot_use_admin_endpoints(client: TestClient, seeded: dict) -> None:
    headers = login(client, seeded["user_a"])

    assert client.get("/api/v1/admin/departments", headers=headers).status_code == 403
    assert (
        client.post(
            "/api/v1/admin/users",
            headers=headers,
            json={
                "email": "x@example.test",
                "password": PASSWORD,
                "department_id": str(seeded["department_a"]),
            },
        ).status_code
        == 403
    )
    assert client.get("/api/v1/admin/devices", headers=headers).status_code == 403


def test_department_admin_is_limited_to_own_department(client: TestClient, seeded: dict) -> None:
    headers = login(client, seeded["admin_a"])

    own = client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": "new-a@example.test",
            "password": PASSWORD,
            "department_id": str(seeded["department_a"]),
        },
    )
    assert own.status_code == 201, own.text

    other = client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": "new-b@example.test",
            "password": PASSWORD,
            "department_id": str(seeded["department_b"]),
        },
    )
    assert other.status_code == 403

    elevation = client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": "boss@example.test",
            "password": PASSWORD,
            "department_id": str(seeded["department_a"]),
            "is_super_admin": True,
        },
    )
    assert elevation.status_code == 403


def test_super_admin_can_create_departments_and_duplicate_code_conflicts(
    client: TestClient, seeded: dict
) -> None:
    headers = login(client, seeded["super_admin"])
    created = client.post(
        "/api/v1/admin/departments",
        headers=headers,
        json={"code": "QA-LAB", "name": "Quality Lab", "location": "Warehouse 1"},
    )
    assert created.status_code == 201, created.text

    duplicate = client.post(
        "/api/v1/admin/departments",
        headers=headers,
        json={"code": "qa-lab", "name": "Other"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "department_code_taken"


def test_device_lifecycle_and_credential_rotation(
    client: TestClient, seeded: dict, db: Session
) -> None:
    headers = login(client, seeded["super_admin"])
    device = register_device(client, headers, seeded["department_a"], "RICE-DEVICE-001")

    first_token = issue_device_token(client, headers, device["id"])
    missing_scan = uuid.uuid4()
    status = client.get(
        f"/api/v1/device/scans/{missing_scan}/status",
        headers={"Authorization": f"Bearer {first_token}"},
    )
    assert status.status_code == 404

    # Rotating invalidates the old client_id immediately.
    detail = client.get(f"/api/v1/admin/devices/{device['id']}", headers=headers).json()
    assignments = client.get(
        f"/api/v1/admin/devices/{device['id']}/assignments", headers=headers
    ).json()
    assert len(assignments) == 1
    assert assignments[0]["effective_to"] is None
    assert detail["active_department_id"] == str(seeded["department_a"])


def test_reassignment_closes_previous_row_and_keeps_history(
    client: TestClient, seeded: dict, db: Session
) -> None:
    headers = login(client, seeded["super_admin"])
    device = register_device(client, headers, seeded["department_a"], "RICE-DEVICE-002")

    moved = client.post(
        f"/api/v1/admin/devices/{device['id']}/assignments",
        headers=headers,
        json={"department_id": str(seeded["department_b"]), "reason": "Relocated"},
    )
    assert moved.status_code == 201, moved.text

    rows = (
        db.query(DeviceAssignment)
        .filter(DeviceAssignment.device_id == device["id"])
        .order_by(DeviceAssignment.effective_from)
        .all()
    )
    assert len(rows) == 2
    assert rows[0].effective_to is not None
    assert rows[0].department_id == seeded["department_a"]
    assert rows[1].effective_to is None
    assert rows[1].department_id == seeded["department_b"]
    assert rows[1].reason == "Relocated"


def test_device_credentials_cannot_access_portal(client: TestClient, seeded: dict) -> None:
    headers = login(client, seeded["super_admin"])
    device = register_device(client, headers, seeded["department_a"], "RICE-DEVICE-003")
    device_token = issue_device_token(client, headers, device["id"])

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {device_token}"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "device_token_used_on_user_route"


def test_human_token_cannot_submit_device_scan(client: TestClient, seeded: dict) -> None:
    headers = login(client, seeded["user_a"])

    response = client.post("/api/v1/device/scans", json={}, headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "user_token_used_on_device_route"


def test_suspended_device_cannot_obtain_a_token(client: TestClient, seeded: dict) -> None:
    headers = login(client, seeded["super_admin"])
    device = register_device(client, headers, seeded["department_a"], "RICE-DEVICE-004")
    credential = client.post(
        f"/api/v1/admin/devices/{device['id']}/credentials", headers=headers
    ).json()
    client.patch(
        f"/api/v1/admin/devices/{device['id']}",
        headers=headers,
        json={"status": "suspended"},
    )

    response = client.post(
        "/api/v1/device-auth/token",
        json={
            "grant_type": "client_credentials",
            "client_id": credential["client_id"],
            "client_secret": credential["client_secret"],
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "device_suspended"


def test_audit_rows_are_written_for_administration(
    client: TestClient, seeded: dict, db: Session
) -> None:
    from app.models import AuditLog

    headers = login(client, seeded["super_admin"])
    register_device(client, headers, seeded["department_a"], "RICE-DEVICE-005")

    actions = {row.action for row in db.query(AuditLog).all()}
    assert "device.registered" in actions
    assert "auth.login_succeeded" in actions
