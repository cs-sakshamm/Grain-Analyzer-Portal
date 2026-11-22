"""Generates the Rice Age Portal Postman collection.

Every request here corresponds to an operation that exists in the running FastAPI
application. The set was cross-checked against ``GET /openapi.json`` (import the app and
call ``create_app().openapi()``) so the collection can be regenerated when the contract
changes.

Run from the repository root:

    python postman/build_collection.py

Output: ``postman/Rice_Age_Portal.postman_collection.json``
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "Rice_Age_Portal.postman_collection.json"

# Byte-identical to postman/samples/report.pdf; the upload endpoint verifies the hash.
PDF_RAW = (
    "%PDF-1.4\n"
    "% Rice Age Portal - Postman sample report (not a real analysis report)\n"
    "1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    "trailer\n<< /Root 1 0 R >>\n"
    "%%EOF\n"
)

NOAUTH = {"type": "noauth"}


def bearer(value: str) -> dict:
    return {"type": "bearer", "bearer": [{"key": "token", "value": value, "type": "string"}]}


def url(path: str, query: list[tuple[str, str, bool]] | None = None) -> dict:
    enabled = [(key, value) for key, value, on in (query or []) if on]
    raw = "{{base_url}}" + path
    if enabled:
        raw += "?" + "&".join(f"{key}={value}" for key, value in enabled)
    entry = {
        "raw": raw,
        "host": ["{{base_url}}"],
        "path": [segment for segment in path.strip("/").split("/")],
    }
    if query:
        entry["query"] = [
            {"key": key, "value": value, "disabled": not on} for key, value, on in query
        ]
    return entry


def req(
    name: str,
    method: str,
    path: str,
    *,
    auth: str | None = None,
    description: str = "",
    body: dict | None = None,
    raw_body: str | None = None,
    binary: str | None = None,
    headers: list[tuple[str, str]] | None = None,
    query: list[tuple[str, str, bool]] | None = None,
    tests: list[str] | None = None,
    prerequest: list[str] | None = None,
) -> dict:
    """Builds one Postman request.

    ``auth``: ``None`` inherits the collection bearer token; ``"none"`` sends no
    Authorization header; ``"device"``/``"super"`` select those environment tokens.
    """

    request: dict = {
        "method": method,
        "header": [{"key": key, "value": value, "type": "text"} for key, value in (headers or [])],
        "url": url(path, query),
        "description": description,
    }
    if auth == "none":
        request["auth"] = NOAUTH
    elif auth == "device":
        request["auth"] = bearer("{{device_access_token}}")
    elif auth == "super":
        request["auth"] = bearer("{{super_admin_access_token}}")
    if body is not None:
        request["body"] = {
            "mode": "raw",
            "raw": json.dumps(body, indent=2),
            "options": {"raw": {"language": "json"}},
        }
    elif raw_body is not None:
        request["body"] = {
            "mode": "raw",
            "raw": raw_body,
            "options": {"raw": {"language": "text"}},
        }
    elif binary is not None:
        request["body"] = {"mode": "binary", "binary": {"src": binary}}

    events = []
    if prerequest:
        events.append(
            {"listen": "prerequest", "script": {"type": "text/javascript", "exec": prerequest}}
        )
    if tests:
        events.append({"listen": "test", "script": {"type": "text/javascript", "exec": tests}})
    item = {"name": name, "request": request, "response": []}
    if events:
        item["event"] = events
    return item


def folder(name: str, description: str, items: list[dict], auth: dict | None = None) -> dict:
    entry = {"name": name, "description": description, "item": items}
    if auth is not None:
        entry["auth"] = auth
    return entry


# --------------------------------------------------------------------------- payloads

SCAN_PAYLOAD = {
    "schema_version": "1.0",
    "client_scan_id": "{{client_scan_id}}",
    "device_id": "{{device_uid}}",
    "sample": {
        "sample_id": "SAMPLE-POSTMAN-001",
        "batch_id": "{{batch_code}}",
        "lot_id": "LOT-POSTMAN-001",
        "variety": "Long-grain",
    },
    "analyzed_at": "{{$isoTimestamp}}",
    "analysis": {
        "grain_count": 2500,
        "measurements": [
            {
                "code": "broken_kernels",
                "label": "Broken kernels",
                "value": 2.5,
                "unit": "percent",
                "basis": "count_percent",
                "is_estimated": False,
                "source_path": "analysis.kernels.broken",
            },
            {
                "code": "estimated_mass_broken",
                "label": "Broken kernels (estimated mass)",
                "value": 2.1,
                "unit": "percent",
                "basis": "estimated_mass_percent",
                "is_estimated": True,
            },
        ],
    },
    "rice_age": {
        "age_value_months": 12,
        "age_min_months": 10,
        "age_max_months": 14,
        "age_category": "mature",
        "proportion_percent": 85.5,
        "unit": "months",
        "method": "device-model",
        "model_version": "v1.0",
        "confidence": 88,
        "validation_status": "provisional",
    },
    "evaluation": {
        "overall": "pass",
        "ruleset_version": "postman-dev-1",
        "certification_status": "device_reported",
        "parameters": [
            {
                "code": "broken_kernels",
                "basis": "count_percent",
                "measured_value": 2.5,
                "threshold_value": 5,
                "comparison_operator": "lte",
                "source_limit_text": "development fixture only",
                "status": "pass",
            }
        ],
    },
    "attachments": [
        {"role": "report_pdf", "content_type": "application/pdf", "filename": "postman-report.pdf"},
        {"role": "bottom_image", "content_type": "image/png", "filename": "platen-bottom.png"},
    ],
}

CONFLICT_PAYLOAD = json.loads(json.dumps(SCAN_PAYLOAD))
CONFLICT_PAYLOAD["analysis"]["grain_count"] = 2501

INVALID_PAYLOAD = json.loads(json.dumps(SCAN_PAYLOAD))
INVALID_PAYLOAD.pop("attachments", None)
INVALID_PAYLOAD["analysis"]["measurements"][0]["unit"] = "mm"  # invalid for count_percent

NEW_SCAN_ID = [
    "// Each run submits a fresh client_scan_id unless reuse_scan is set to 'true',",
    "// so the full submit -> upload -> finalize lifecycle stays repeatable.",
    "if (pm.environment.get('reuse_scan') !== 'true') {",
    "  pm.environment.set('client_scan_id', 'POSTMAN-' + Date.now());",
    "}",
]

SKIP_UNLESS = "if (pm.environment.get('{flag}') !== 'true') {{ pm.execution.skipRequest(); }}"


def guarded(flag: str) -> list[str]:
    return [
        "// Destructive on a shared database: enable the environment flag to run it.",
        SKIP_UNLESS.format(flag=flag),
    ]


# --------------------------------------------------------------------------- folders

health = folder(
    "1. Health & Readiness",
    "Unauthenticated probes. Readiness performs a real database round-trip.",
    [
        req(
            "Liveness",
            "GET",
            "/api/v1/health",
            auth="none",
            description="Returns the service identity. Version and environment are omitted in production.",
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('status is ok', () => pm.expect(body.status).to.eql('ok'));",
                "pm.test('service name is present', () => pm.expect(body.service).to.be.a('string'));",
            ],
        ),
        req(
            "Readiness",
            "GET",
            "/api/v1/health/ready",
            auth="none",
            description="200 when PostgreSQL answers SELECT 1; 503 dependency_unavailable otherwise.",
            tests=[
                "pm.test('200 ready', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('status is ready', () => pm.expect(body.status).to.eql('ready'));",
                "pm.test('database is ok', () => pm.expect(body.database).to.eql('ok'));",
            ],
        ),
    ],
)

auth_folder = folder(
    "2. Authentication",
    "Human authentication. The access token is a bearer JWT (15 min default); the refresh "
    "token is an HttpOnly cookie (`ra_refresh`, path /api/v1/auth) and is never returned in "
    "the body, so Postman must keep cookies enabled. Devices use a different flow (folder 7).",
    [
        req(
            "Login - Department Admin",
            "POST",
            "/api/v1/auth/login",
            auth="none",
            description="Seeded development account (dev_seed.py). Replace with your own account.",
            body={"email": "{{admin_email}}", "password": "{{admin_password}}"},
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('bearer token returned', () => pm.expect(body.token_type).to.eql('bearer'));",
                "pm.environment.set('access_token', body.access_token);",
                "pm.environment.set('user_id', body.user.id);",
                "pm.test('department admin membership', () => {",
                "  const membership = body.user.memberships[0];",
                "  pm.expect(membership.role).to.eql('department_admin');",
                "  pm.environment.set('department_id', membership.department_id);",
                "});",
            ],
        ),
        req(
            "Login - Department User",
            "POST",
            "/api/v1/auth/login",
            auth="none",
            description="Stores the token in user_access_token; the collection default stays on the admin.",
            body={"email": "{{user_email}}", "password": "{{user_password}}"},
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.environment.set('user_access_token', body.access_token);",
                "pm.test('department user membership', () =>",
                "  pm.expect(body.user.memberships[0].role).to.eql('department_user'));",
            ],
        ),
        req(
            "Login - Super Admin",
            "POST",
            "/api/v1/auth/login",
            auth="none",
            description="Super-admin cookies overwrite the admin refresh cookie, so sign in as super last "
            "or use a separate Postman tab when you need to switch back.",
            body={"email": "{{super_admin_email}}", "password": "{{super_admin_password}}"},
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('is super admin', () => pm.expect(body.user.is_super_admin).to.eql(true));",
                "pm.environment.set('super_admin_access_token', body.access_token);",
            ],
        ),
        req(
            "Refresh session (rotates)",
            "POST",
            "/api/v1/auth/refresh",
            auth="none",
            description="Requires the ra_refresh cookie. Rotation is single-use: replaying an old cookie "
            "returns 401 invalid_refresh.",
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('new access token', () => pm.expect(body.access_token).to.be.a('string'));",
                "pm.environment.set('access_token', body.access_token);",
            ],
        ),
        req(
            "Current user",
            "GET",
            "/api/v1/auth/me",
            description="Re-reads the principal from the database, so deactivation is immediate.",
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('user matches the token', () =>",
                "  pm.expect(body.user.id).to.eql(pm.environment.get('user_id')));",
            ],
        ),
        req(
            "Change password (guarded)",
            "POST",
            "/api/v1/auth/password/change",
            description="Ends every other session for the account and clears the refresh cookie. "
            "Disabled by default; set enable_password_change=true against a disposable database.",
            body={"current_password": "{{admin_password}}", "new_password": "{{rotated_password}}"},
            prerequest=guarded("enable_password_change"),
            tests=["pm.test('204 No Content', () => pm.response.to.have.status(204));"],
        ),
        req(
            "Logout",
            "POST",
            "/api/v1/auth/logout",
            auth="none",
            description="Revokes the refresh session and clears the cookie. Access tokens remain valid "
            "until they expire.",
            tests=["pm.test('204 No Content', () => pm.response.to.have.status(204));"],
        ),
    ],
)

departments = folder(
    "3. Department Administration",
    "Department creation and edits are super-admin only; department admins may read their own.",
    [
        req(
            "Create department (super admin)",
            "POST",
            "/api/v1/admin/departments",
            auth="super",
            body={
                "code": "{{new_department_code}}",
                "name": "Postman Department",
                "location": "Test bench",
            },
            tests=[
                "pm.test('201 created or 409 already exists', () =>",
                "  pm.expect([201, 409]).to.include(pm.response.code));",
                "if (pm.response.code === 201) {",
                "  const body = pm.response.json();",
                "  pm.environment.set('new_department_id', body.id);",
                "  pm.test('response echoes the code', () =>",
                "    pm.expect(body.code).to.eql(pm.environment.get('new_department_code')));",
                "}",
            ],
        ),
        req(
            "List departments (super admin)",
            "GET",
            "/api/v1/admin/departments",
            auth="super",
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('array of departments', () => pm.expect(body).to.be.an('array'));",
                "// Remember a second department for the isolation checks.",
                "const own = pm.environment.get('department_id');",
                "const other = body.find((department) => department.id !== own);",
                "if (other) pm.environment.set('other_department_id', other.id);",
            ],
        ),
        req(
            "Get own department (department admin)",
            "GET",
            "/api/v1/admin/departments/{{department_id}}",
            description="A department admin may read their own department; any other returns 404.",
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('own department', () =>",
                "  pm.expect(body.id).to.eql(pm.environment.get('department_id')));",
            ],
        ),
        req(
            "Update department location (super admin)",
            "PATCH",
            "/api/v1/admin/departments/{{department_id}}",
            auth="super",
            description="Only mutable with an active-device check when deactivating; this example edits location.",
            body={"location": "Updated by Postman"},
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "pm.test('location updated', () =>",
                "  pm.expect(pm.response.json().location).to.eql('Updated by Postman'));",
            ],
        ),
    ],
)

users = folder(
    "4. User Administration",
    "Interim DR-019 policy: a department admin manages users inside their own department and "
    "can never grant super-admin status.",
    [
        req(
            "Create user (super admin)",
            "POST",
            "/api/v1/admin/users",
            auth="super",
            body={
                "email": "postman.user.{{$timestamp}}@test.local",
                "password": "PostmanPass123!",
                "full_name": "Postman User",
                "department_id": "{{department_id}}",
                "role": "department_user",
                "is_super_admin": False,
            },
            tests=[
                "pm.test('201 created', () => pm.response.to.have.status(201));",
                "const body = pm.response.json();",
                "pm.environment.set('created_user_id', body.id);",
                "pm.test('membership created', () => {",
                "  pm.expect(body.memberships).to.have.lengthOf(1);",
                "  pm.environment.set('membership_id', body.memberships[0].id);",
                "});",
            ],
        ),
        req(
            "List users (department admin)",
            "GET",
            "/api/v1/admin/users",
            query=[("page", "1", True), ("page_size", "25", True)],
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('paginated envelope', () => {",
                "  pm.expect(body.items).to.be.an('array');",
                "  pm.expect(body.total).to.be.a('number');",
                "});",
            ],
        ),
        req(
            "Get user (department admin)",
            "GET",
            "/api/v1/admin/users/{{created_user_id}}",
            tests=["pm.test('200 OK', () => pm.response.to.have.status(200));"],
        ),
        req(
            "Update user (super admin)",
            "PATCH",
            "/api/v1/admin/users/{{created_user_id}}",
            auth="super",
            description="Deactivating a user revokes all of their sessions.",
            body={"full_name": "Postman User (updated)"},
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "pm.test('name updated', () =>",
                "  pm.expect(pm.response.json().full_name).to.eql('Postman User (updated)'));",
            ],
        ),
        req(
            "Add membership (super admin)",
            "POST",
            "/api/v1/admin/users/{{created_user_id}}/memberships",
            auth="super",
            body={"department_id": "{{other_department_id}}", "role": "department_user"},
            tests=[
                "pm.test('201 created or 409 exists', () =>",
                "  pm.expect([201, 409]).to.include(pm.response.code));",
            ],
        ),
        req(
            "Update membership (super admin)",
            "PATCH",
            "/api/v1/admin/memberships/{{membership_id}}",
            auth="super",
            body={"role": "department_user", "is_active": True},
            tests=["pm.test('200 OK', () => pm.response.to.have.status(200));"],
        ),
    ],
)

devices = folder(
    "5. Device Administration",
    "Registration, edits and credential lifecycle are super-admin only. A device secret is "
    "returned exactly once, at issue or rotate time.",
    [
        req(
            "Register device (super admin)",
            "POST",
            "/api/v1/admin/devices",
            auth="super",
            description="Registration also creates the first active assignment.",
            body={
                "device_uid": "POSTMAN-{{$timestamp}}",
                "serial_number": "SN-POSTMAN-{{$timestamp}}",
                "friendly_name": "Postman Bench Device",
                "model": "Model 4000",
                "firmware_version": "2.1.0",
                "installation_location": "Test bench",
                "department_id": "{{department_id}}",
                "activate": True,
            },
            tests=[
                "pm.test('201 created', () => pm.response.to.have.status(201));",
                "const body = pm.response.json();",
                "pm.environment.set('device_id', body.id);",
                "pm.environment.set('device_uid', body.device_uid);",
                "pm.test('active and assigned', () => {",
                "  pm.expect(body.status).to.eql('active');",
                "  pm.expect(body.active_department_id).to.eql(pm.environment.get('department_id'));",
                "});",
            ],
        ),
        req(
            "List devices (department admin)",
            "GET",
            "/api/v1/admin/devices",
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('array of devices', () => pm.expect(body).to.be.an('array'));",
            ],
        ),
        req(
            "Get device (department admin)",
            "GET",
            "/api/v1/admin/devices/{{device_id}}",
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "pm.test('same device', () =>",
                "  pm.expect(pm.response.json().id).to.eql(pm.environment.get('device_id')));",
            ],
        ),
        req(
            "Update device (super admin)",
            "PATCH",
            "/api/v1/admin/devices/{{device_id}}",
            auth="super",
            body={"friendly_name": "Postman Bench Device (renamed)"},
            tests=["pm.test('200 OK', () => pm.response.to.have.status(200));"],
        ),
        req(
            "Issue device credential (super admin)",
            "POST",
            "/api/v1/admin/devices/{{device_id}}/credentials",
            auth="super",
            description="Returns client_id and client_secret once. 409 credential_exists when one is active.",
            tests=[
                "pm.test('201 issued or 409 active credential exists', () =>",
                "  pm.expect([201, 409]).to.include(pm.response.code));",
                "if (pm.response.code === 201) {",
                "  const body = pm.response.json();",
                "  pm.environment.set('client_id', body.client_id);",
                "  pm.environment.set('client_secret', body.client_secret);",
                "  pm.environment.set('credential_id', body.id);",
                "}",
            ],
        ),
        req(
            "Rotate device credential (super admin)",
            "POST",
            "/api/v1/admin/devices/{{device_id}}/credentials/rotate",
            auth="super",
            description="Revokes the active credential and issues a replacement. Tokens already issued stay "
            "valid until they expire.",
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.environment.set('client_id', body.client_id);",
                "pm.environment.set('client_secret', body.client_secret);",
                "pm.environment.set('credential_id', body.id);",
            ],
        ),
        req(
            "Revoke device credential (guarded)",
            "POST",
            "/api/v1/admin/devices/{{device_id}}/credentials/{{credential_id}}/revoke",
            auth="super",
            description="Runs last in a session: device token requests fail afterwards. "
            "Set enable_credential_revoke=true to run it.",
            body={"reason": "postman teardown"},
            prerequest=guarded("enable_credential_revoke"),
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "pm.test('credential revoked', () =>",
                "  pm.expect(pm.response.json().revoked_at).to.not.eql(null));",
            ],
        ),
    ],
)

assignments = folder(
    "6. Device Assignment",
    "Ownership history is append-only: reassignment closes the previous row and never moves "
    "scans that were already accepted.",
    [
        req(
            "List assignments",
            "GET",
            "/api/v1/admin/devices/{{device_id}}/assignments",
            auth="super",
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('has at least one assignment', () => pm.expect(body.length).to.be.above(0));",
                "pm.test('one assignment is active', () =>",
                "  pm.expect(body.filter((row) => row.effective_to === null).length).to.eql(1));",
            ],
        ),
        req(
            "Reassign device (guarded)",
            "POST",
            "/api/v1/admin/devices/{{device_id}}/assignments",
            auth="super",
            description="Moves the device to other_department_id. This changes where later scans are filed, "
            "so it is disabled by default: set enable_reassignment=true against a disposable database.",
            body={"department_id": "{{other_department_id}}", "reason": "Postman reassignment check"},
            prerequest=guarded("enable_reassignment"),
            tests=[
                "pm.test('201 created', () => pm.response.to.have.status(201));",
                "const body = pm.response.json();",
                "pm.test('assigned to the requested department', () =>",
                "  pm.expect(body.department_id).to.eql(pm.environment.get('other_department_id')));",
            ],
        ),
    ],
)

iot = folder(
    "7. IoT Device APIs",
    "Machine identity only. Obtain a token with client_credentials, then use it as a bearer "
    "token. A human token on these routes returns 403 user_token_used_on_device_route.",
    [
        req(
            "Device token (client credentials)",
            "POST",
            "/api/v1/device-auth/token",
            auth="none",
            body={
                "grant_type": "client_credentials",
                "client_id": "{{client_id}}",
                "client_secret": "{{client_secret}}",
            },
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('device scope', () => pm.expect(body.scope).to.eql('device:scan'));",
                "pm.environment.set('device_access_token', body.access_token);",
                "pm.environment.set('device_uid', body.device_id);",
            ],
        ),
        req(
            "Device token - invalid secret (expect 401)",
            "POST",
            "/api/v1/device-auth/token",
            auth="none",
            body={
                "grant_type": "client_credentials",
                "client_id": "{{client_id}}",
                "client_secret": "definitely-not-the-secret",
            },
            tests=[
                "pm.test('401 Unauthorized', () => pm.response.to.have.status(401));",
                "pm.test('invalid_client', () =>",
                "  pm.expect(pm.response.json().error.code).to.eql('invalid_client'));",
            ],
        ),
        req(
            "Submit scan (schema 1.0)",
            "POST",
            "/api/v1/device/scans",
            auth="device",
            description="Idempotency key is (device_id, client_scan_id). Department is taken from the "
            "authenticated device's active assignment; a payload department_id is rejected.",
            body=SCAN_PAYLOAD,
            prerequest=NEW_SCAN_ID,
            tests=[
                "pm.test('201 Created', () => pm.response.to.have.status(201));",
                "const body = pm.response.json();",
                "pm.environment.set('scan_id', body.scan_id);",
                "pm.test('awaiting files', () =>",
                "  pm.expect(body.processing_status).to.eql('awaiting_files'));",
                "pm.test('first submission is not a replay', () => pm.expect(body.replayed).to.eql(false));",
                "pm.test('attachment policy is reported', () => {",
                "  pm.expect(body.required_attachments).to.include('report_pdf');",
                "  pm.expect(body.optional_attachments).to.include('top_image');",
                "});",
            ],
        ),
        req(
            "Submit scan - identical replay (expect 200)",
            "POST",
            "/api/v1/device/scans",
            auth="device",
            description="Same bytes, same client_scan_id: safe replay, no duplicate scan or notification.",
            body=SCAN_PAYLOAD,
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('replayed flag', () => pm.expect(body.replayed).to.eql(true));",
                "pm.test('same scan id', () =>",
                "  pm.expect(body.scan_id).to.eql(pm.environment.get('scan_id')));",
            ],
        ),
        req(
            "Submit scan - conflicting payload (expect 409)",
            "POST",
            "/api/v1/device/scans",
            auth="device",
            description="Same client_scan_id, different bytes: rejected instead of silently overwriting.",
            body=CONFLICT_PAYLOAD,
            tests=[
                "pm.test('409 Conflict', () => pm.response.to.have.status(409));",
                "pm.test('scan_conflict', () =>",
                "  pm.expect(pm.response.json().error.code).to.eql('scan_conflict'));",
            ],
        ),
        req(
            "Submit scan - invalid payload (expect 422)",
            "POST",
            "/api/v1/device/scans",
            auth="device",
            description="A unit that does not match its measurement basis fails schema validation.",
            body=INVALID_PAYLOAD,
            prerequest=[
                "pm.environment.set('client_scan_id', 'POSTMAN-INVALID-' + Date.now());"
            ],
            tests=[
                "pm.test('422 Unprocessable Entity', () => pm.response.to.have.status(422));",
                "pm.test('validation_error', () =>",
                "  pm.expect(pm.response.json().error.code).to.eql('validation_error'));",
            ],
        ),
        req(
            "Prepare report attachment",
            "POST",
            "/api/v1/device/scans/{{scan_id}}/attachments/prepare",
            auth="device",
            description="Declares role, size and SHA-256 before upload. Local storage returns the API upload "
            "path; S3 returns a presigned PUT URL.",
            body={
                "role": "report_pdf",
                "content_type": "application/pdf",
                "size_bytes": "{{report_size_bytes}}",
                "sha256": "{{report_sha256}}",
                "filename": "postman-report.pdf",
            },
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.environment.set('upload_id', body.upload_id);",
                "pm.test('upload target offered', () => pm.expect(body.url).to.be.a('string'));",
            ],
        ),
        req(
            "Upload report attachment",
            "PUT",
            "/api/v1/device/scans/{{scan_id}}/files/{{upload_id}}",
            auth="device",
            description="Raw body must be byte-identical to the prepared sample; the hash and the %PDF- magic "
            "bytes are both verified.",
            headers=[("Content-Type", "application/pdf")],
            raw_body=PDF_RAW,
            tests=[
                "pm.test('201 Created', () => pm.response.to.have.status(201));",
                "const body = pm.response.json();",
                "pm.test('verified', () => pm.expect(body.upload_status).to.eql('verified'));",
                "pm.test('checksum matches', () =>",
                "  pm.expect(body.sha256).to.eql(pm.environment.get('report_sha256')));",
            ],
        ),
        req(
            "Prepare bottom platen image",
            "POST",
            "/api/v1/device/scans/{{scan_id}}/attachments/prepare",
            auth="device",
            body={
                "role": "bottom_image",
                "content_type": "image/png",
                "size_bytes": "{{bottom_image_size_bytes}}",
                "sha256": "{{bottom_image_sha256}}",
                "filename": "platen-bottom.png",
            },
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "pm.environment.set('image_upload_id', pm.response.json().upload_id);",
            ],
        ),
        req(
            "Upload bottom platen image",
            "PUT",
            "/api/v1/device/scans/{{scan_id}}/files/{{image_upload_id}}",
            auth="device",
            description="Binary body: select postman/samples/platen-bottom.png in the Postman UI (its hash is "
            "in the environment). This file cannot be sent as text.",
            headers=[("Content-Type", "image/png")],
            binary="samples/platen-bottom.png",
            tests=[
                "pm.test('201 Created', () => pm.response.to.have.status(201));",
                "pm.test('verified', () =>",
                "  pm.expect(pm.response.json().upload_status).to.eql('verified'));",
            ],
        ),
        req(
            "Prepare optional top image",
            "POST",
            "/api/v1/device/scans/{{scan_id}}/attachments/prepare",
            auth="device",
            description="top_image is optional under the provisional attachment policy (DR-007) and is not "
            "required by finalize. Preparing it without uploading leaves an unverified row, which is fine.",
            body={
                "role": "top_image",
                "content_type": "image/png",
                "size_bytes": "{{bottom_image_size_bytes}}",
                "sha256": "{{bottom_image_sha256}}",
                "filename": "platen-top.png",
            },
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "pm.test('upload target offered', () =>",
                "  pm.expect(pm.response.json().url).to.be.a('string'));",
            ],
        ),
        req(
            "Finalize scan",
            "POST",
            "/api/v1/device/scans/{{scan_id}}/finalize",
            auth="device",
            description="Verifies required attachments, applies the device-supplied verdict and creates "
            "deduplicated notifications. Required roles are configuration (default report_pdf,bottom_image).",
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('completed', () => pm.expect(body.processing_status).to.eql('completed'));",
                "pm.test('verdict preserved', () => pm.expect(body.quality_verdict).to.eql('pass'));",
                "pm.test('notification created', () => pm.expect(body.notifications_created).to.be.above(0));",
            ],
        ),
        req(
            "Finalize again - idempotent",
            "POST",
            "/api/v1/device/scans/{{scan_id}}/finalize",
            auth="device",
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "pm.test('still completed', () =>",
                "  pm.expect(pm.response.json().processing_status).to.eql('completed'));",
                "pm.test('no duplicate notification', () =>",
                "  pm.expect(pm.response.json().notifications_created).to.eql(0));",
            ],
        ),
        req(
            "Scan status",
            "GET",
            "/api/v1/device/scans/{{scan_id}}/status",
            auth="device",
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('completed', () => pm.expect(body.processing_status).to.eql('completed'));",
                "pm.test('attachments reported', () =>",
                "  pm.expect(body.attachments.length).to.be.above(0));",
            ],
        ),
    ],
)

scan_management = folder(
    "8. Scan Management",
    "Portal reads of one scan and its report. Department scope is resolved server-side; a super "
    "admin must pass ?department_id=.",
    [
        req(
            "Latest completed scan",
            "GET",
            "/api/v1/scans/latest",
            description="204 means the department has no completed scan yet. In-flight or failed scans are "
            "never returned here.",
            tests=[
                "pm.test('200 with a scan or 204 when empty', () =>",
                "  pm.expect([200, 204]).to.include(pm.response.code));",
                "if (pm.response.code === 200) {",
                "  const body = pm.response.json();",
                "  pm.test('latest is completed', () =>",
                "    pm.expect(body.scan.processing_status).to.eql('completed'));",
                "  pm.test('advisory notice present', () =>",
                "    pm.expect(body.scan.advisory).to.be.a('string'));",
                "}",
            ],
        ),
        req(
            "Scan detail",
            "GET",
            "/api/v1/scans/{{scan_id}}",
            query=[("department_id", "{{department_id}}", False)],
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('same scan', () => pm.expect(body.scan.id).to.eql(pm.environment.get('scan_id')));",
                "pm.test('measurement basis preserved', () => {",
                "  const basis = body.scan.measurements.map((row) => row.basis);",
                "  pm.expect(basis).to.include('count_percent');",
                "  pm.expect(basis).to.include('estimated_mass_percent');",
                "});",
            ],
        ),
        req(
            "Report metadata",
            "GET",
            "/api/v1/scans/{{scan_id}}/report",
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('download path and expiry issued', () => {",
                "  pm.expect(body.url).to.be.a('string');",
                "  pm.expect(body.expires_at).to.be.a('string');",
                "});",
            ],
        ),
        req(
            "Download report PDF",
            "GET",
            "/api/v1/scans/{{scan_id}}/report/download",
            query=[("disposition", "attachment", True), ("department_id", "{{department_id}}", False)],
            description="Binary stream of the original device PDF. The access token travels in the header; "
            "no public URL is issued.",
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "pm.test('PDF content type', () =>",
                "  pm.expect(pm.response.headers.get('Content-Type')).to.include('application/pdf'));",
                "pm.test('not cacheable', () =>",
                "  pm.expect(pm.response.headers.get('Cache-Control')).to.include('no-store'));",
            ],
        ),
    ],
)

scan_history = folder(
    "9. Scan History",
    "Paginated, department-scoped history. Supported filters: batch_code, device_id, "
    "processing_status, quality_verdict, start_date, end_date, page, per_page.",
    [
        req(
            "Scan history (first page)",
            "GET",
            "/api/v1/scans/history",
            query=[
                ("page", "1", True),
                ("per_page", "20", True),
                ("batch_code", "{{batch_code}}", False),
                ("processing_status", "completed", False),
            ],
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('paginated envelope', () => {",
                "  pm.expect(body.items).to.be.an('array');",
                "  pm.expect(body.total).to.be.a('number');",
                "  pm.expect(body.pages).to.be.a('number');",
                "});",
            ],
        )
    ],
)

quality = folder(
    "10. Quality Analytics",
    "Counts and per-basis parameter statistics. Values are grouped by basis + unit and are never "
    "blended across incompatible bases.",
    [
        req(
            "Quality analytics",
            "GET",
            "/api/v1/scans/analytics/quality",
            query=[("start_date", "2026-01-01", False), ("end_date", "2026-12-31", False)],
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('expected sections', () => {",
                "  pm.expect(body.total_scans).to.be.a('number');",
                "  pm.expect(body.quality_distribution).to.be.an('object');",
                "  pm.expect(body.parameter_summary).to.be.an('object');",
                "});",
            ],
        )
    ],
)

rice_age = folder(
    "11. Rice Age Analytics",
    "Device-supplied age only. Missing age is null, never zero; a scan with no age row is simply "
    "absent from the list.",
    [
        req(
            "Rice age results",
            "GET",
            "/api/v1/scans/analytics/rice-age",
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('age envelope', () => {",
                "  pm.expect(body.total_scans_with_age).to.be.a('number');",
                "  pm.expect(body.age_results).to.be.an('array');",
                "});",
            ],
        )
    ],
)

reports = folder(
    "12. Reports",
    "Listing of scans with report/age availability. Download uses folder 8's report endpoints.",
    [
        req(
            "Report listing",
            "GET",
            "/api/v1/scans/analytics/reports",
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('items array', () => pm.expect(body.items).to.be.an('array'));",
            ],
        )
    ],
)

batches = folder(
    "13. Batch Comparison",
    "Scans grouped by batch_code with measurements grouped by basis; count and estimated-mass "
    "percentages stay separate.",
    [
        req(
            "Batch comparison",
            "GET",
            "/api/v1/scans/analytics/batch-comparison",
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "pm.test('batches object', () =>",
                "  pm.expect(pm.response.json().batches).to.be.an('object'));",
            ],
        )
    ],
)

notifications = folder(
    "14. Notifications",
    "In-portal notifications for the signed-in user, scoped to their department. There is no "
    "mark-as-read endpoint yet; read_at is reported but cannot be changed through the API.",
    [
        req(
            "Notifications",
            "GET",
            "/api/v1/scans/notifications",
            query=[("unread_only", "false", True)],
            tests=[
                "pm.test('200 OK', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('items array', () => pm.expect(body.items).to.be.an('array'));",
                "if (body.items.length > 0) {",
                "  pm.test('severity is a known value', () =>",
                "    pm.expect(['info', 'warning', 'critical']).to.include(body.items[0].severity));",
                "}",
            ],
        )
    ],
)

security = folder(
    "15. Department Isolation & Security Checks",
    "Negative paths that prove the server, not the UI, is the access boundary. Audit has no HTTP "
    "read endpoint yet, so there is no audit folder.",
    [
        req(
            "Latest scan - foreign department (expect 404)",
            "GET",
            "/api/v1/scans/latest",
            query=[("department_id", "{{other_department_id}}", True)],
            description="A department admin asking for another department gets 404, never a 403 that would "
            "confirm the department exists.",
            tests=[
                "pm.test('404 Not Found', () => pm.response.to.have.status(404));",
                "pm.test('not_found', () =>",
                "  pm.expect(pm.response.json().error.code).to.eql('not_found'));",
            ],
        ),
        req(
            "Scan detail - foreign department (expect 404)",
            "GET",
            "/api/v1/scans/{{scan_id}}",
            query=[("department_id", "{{other_department_id}}", True)],
            tests=["pm.test('404 Not Found', () => pm.response.to.have.status(404));"],
        ),
        req(
            "Device token on a portal route (expect 403)",
            "GET",
            "/api/v1/scans/latest",
            auth="device",
            tests=[
                "pm.test('403 Forbidden', () => pm.response.to.have.status(403));",
                "pm.test('device_token_used_on_user_route', () =>",
                "  pm.expect(pm.response.json().error.code).to.eql('device_token_used_on_user_route'));",
            ],
        ),
        req(
            "Portal token on a device route (expect 403)",
            "GET",
            "/api/v1/device/scans/{{scan_id}}/status",
            tests=[
                "pm.test('403 Forbidden', () => pm.response.to.have.status(403));",
                "pm.test('user_token_used_on_device_route', () =>",
                "  pm.expect(pm.response.json().error.code).to.eql('user_token_used_on_device_route'));",
            ],
        ),
    ],
)

collection = {
    "info": {
        "_postman_id": str(uuid.uuid4()),
        "name": "Rice Age Portal API",
        "description": (
            "Department-scoped portal API for the Rice Age IoT rice quality and age analyser.\n\n"
            "42 implemented operations across 15 folders, generated from the running FastAPI "
            "application's OpenAPI document. See postman/POSTMAN_API_GUIDE.md for setup, the "
            "human-vs-device authentication difference and the safe test-data workflow.\n\n"
            "All outputs are advisory: optical estimates are not statutory procurement "
            "measurements and the portal is not a certification authority."
        ),
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "auth": bearer("{{access_token}}"),
    "event": [
        {
            "listen": "prerequest",
            "script": {
                "type": "text/javascript",
                "exec": [
                    "// Fail fast with an actionable message instead of a wall of 401s.",
                    "if (!pm.environment.get('base_url')) {",
                    "  console.warn('Select the \"Rice Age Local\" environment first.');",
                    "}",
                ],
            },
        }
    ],
    "item": [
        health,
        auth_folder,
        departments,
        users,
        devices,
        assignments,
        iot,
        scan_management,
        scan_history,
        quality,
        rice_age,
        reports,
        batches,
        notifications,
        security,
    ],
}


def request_count(node: dict) -> int:
    if "request" in node:
        return 1
    return sum(request_count(child) for child in node.get("item", []))


if __name__ == "__main__":
    OUT.write_text(json.dumps(collection, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total = request_count(collection)
    print(f"wrote {OUT.name}: {len(collection['item'])} folders, {total} requests")
