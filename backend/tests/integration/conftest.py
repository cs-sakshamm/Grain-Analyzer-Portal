"""PostgreSQL integration fixtures.

These tests are skipped unless ``RICE_AGE_TEST_DATABASE_URL`` points at a disposable
PostgreSQL database. CI provides one as a service container. SQLite is deliberately
not used: partial unique indexes, native enums, JSONB and INET are load-bearing here.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.ratelimit import device_token_limiter, login_limiter, scan_limiter
from app.core.security import hash_password
from app.db.session import get_db
from app.main import create_app
from app.models import Base, Department, Membership, User
from app.models.enums import MembershipRole
from app.storage.local import LocalStorage

TEST_DATABASE_URL = os.getenv("RICE_AGE_TEST_DATABASE_URL")
PASSWORD = "Password123!"


@pytest.fixture(autouse=True)
def reset_rate_limiters() -> Iterator[None]:
    login_limiter.reset()
    device_token_limiter.reset()
    scan_limiter.reset()
    yield


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    if not TEST_DATABASE_URL:
        pytest.skip("database integration tests need RICE_AGE_TEST_DATABASE_URL (PostgreSQL)")
    test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """Fresh schema per test: reliable isolation without cross-test ordering."""

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def app(engine: Engine, tmp_path) -> Iterator[FastAPI]:
    settings = Settings(
        environment="test",
        app_secret_key="integration-secret-" + "a" * 40,
        database_url=str(engine.url),
        storage_local_root=str(tmp_path / "storage"),
    )
    application = create_app(settings)
    application.state.storage = LocalStorage(tmp_path / "storage")

    def override_db() -> Iterator[Session]:
        session = Session(engine)
        try:
            yield session
        finally:
            session.close()

    application.dependency_overrides[get_db] = override_db
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def make_department(db: Session, code: str = "DEPT-A", **kwargs) -> Department:
    department = Department(code=code, name=kwargs.pop("name", f"Department {code}"), **kwargs)
    db.add(department)
    db.commit()
    db.refresh(department)
    return department


def make_user(
    db: Session,
    email: str = "user@example.test",
    *,
    is_super_admin: bool = False,
    is_active: bool = True,
    password: str = PASSWORD,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=email.split("@")[0],
        is_super_admin=is_super_admin,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def add_membership(
    db: Session,
    user: User,
    department: Department,
    role: MembershipRole = MembershipRole.DEPARTMENT_USER,
) -> Membership:
    membership = Membership(user_id=user.id, department_id=department.id, role=role)
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def seeded(db: Session) -> dict[str, object]:
    """Two departments with an admin and a user each, plus a super admin."""

    department_a = make_department(db, "DEPT-A", name="Department A")
    department_b = make_department(db, "DEPT-B", name="Department B")
    super_admin = make_user(db, "super@example.test", is_super_admin=True)
    admin_a = make_user(db, "admin-a@example.test")
    user_a = make_user(db, "user-a@example.test")
    admin_b = make_user(db, "admin-b@example.test")
    user_b = make_user(db, "user-b@example.test")
    add_membership(db, admin_a, department_a, MembershipRole.DEPARTMENT_ADMIN)
    add_membership(db, user_a, department_a)
    add_membership(db, admin_b, department_b, MembershipRole.DEPARTMENT_ADMIN)
    add_membership(db, user_b, department_b)
    return {
        "department_a": department_a.id,
        "department_b": department_b.id,
        "super_admin": super_admin.email,
        "admin_a": admin_a.email,
        "user_a": user_a.email,
        "admin_b": admin_b.email,
        "user_b": user_b.email,
    }


def post_department(client: TestClient, headers: dict[str, str], code: str) -> dict:
    response = client.post(
        "/api/v1/admin/departments",
        json={"code": code, "name": f"Department {code}"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def register_device(
    client: TestClient,
    headers: dict[str, str],
    department_id: uuid.UUID,
    uid: str = "RICE-DEVICE-001",
) -> dict:
    response = client.post(
        "/api/v1/admin/devices",
        json={
            "device_uid": uid,
            "serial_number": f"SN-{uid}",
            "department_id": str(department_id),
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def sample_payload(
    client_scan_id: str = "SCAN-0038",
    *,
    verdict: str | None = "flagged",
    with_age: bool = True,
    extra: dict | None = None,
) -> dict:
    payload: dict = {
        "schema_version": "1.0",
        "client_scan_id": client_scan_id,
        "sample": {
            "sample_id": "Sample-0038",
            "batch_id": "BATCH-2026-001",
            "lot_id": "LOT-A",
        },
        "analyzed_at": datetime.now(UTC).isoformat(),
        "analysis": {
            "grain_count": 363,
            "measurements": [
                {
                    "code": "head_rice",
                    "value": 50.68,
                    "unit": "percent",
                    "basis": "estimated_mass_percent",
                    "is_estimated": True,
                },
                {
                    "code": "head_rice",
                    "value": 49.10,
                    "unit": "percent",
                    "basis": "count_percent",
                    "is_estimated": False,
                },
                {
                    "code": "avg_length_mm",
                    "value": 5.25,
                    "unit": "mm",
                    "basis": "dimension",
                    "is_estimated": False,
                },
            ],
        },
        "evaluation": {
            "overall": verdict,
            "ruleset_version": "demo-v1",
            "certification_status": "advisory_only",
        },
    }
    if with_age:
        payload["rice_age"] = {
            "age_min_months": 8,
            "age_max_months": 10,
            "age_category": "8-10 Months",
            "proportion_percent": 100,
            "unit": "months",
            "method": "biochemical_colour",
            "validation_status": "unvalidated",
            "raw_value": "8-10 Months (100%)",
        }
    if extra:
        payload.update(extra)
    return payload


PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def upload_attachment(
    client: TestClient,
    token: str,
    scan_id: str,
    role: str,
    content: bytes,
    content_type: str,
    filename: str,
) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    prepare = client.post(
        f"/api/v1/device/scans/{scan_id}/attachments/prepare",
        headers=headers,
        json={
            "role": role,
            "content_type": content_type,
            "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "filename": filename,
        },
    )
    assert prepare.status_code == 200, prepare.text
    target = prepare.json()
    put = client.put(
        target["url"],
        content=content,
        headers={"Authorization": f"Bearer {token}", "Content-Type": content_type},
    )
    assert put.status_code == 201, put.text
    return put.json()


def issue_device_token(client: TestClient, headers: dict[str, str], device_id: str) -> str:
    issued = client.post(f"/api/v1/admin/devices/{device_id}/credentials", headers=headers)
    assert issued.status_code == 201, issued.text
    credential = issued.json()
    token = client.post(
        "/api/v1/device-auth/token",
        json={
            "grant_type": "client_credentials",
            "client_id": credential["client_id"],
            "client_secret": credential["client_secret"],
        },
    )
    assert token.status_code == 200, token.text
    return token.json()["access_token"]
