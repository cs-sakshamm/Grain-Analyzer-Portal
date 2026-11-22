# Rice Age Portal — Postman & API integration guide

This guide lets another developer import a working Postman collection, authenticate as a
human portal user or as an IoT device, exercise every implemented API and understand the
rules behind the responses — without rediscovering the backend.

Everything here was taken from the running backend (`backend/app/api/v1/`), its OpenAPI
document (`create_app().openapi()`) and the service layer that enforces the rules. No
endpoint, field or permission in this guide is aspirational.

## 1. Files

| File | Purpose |
| --- | --- |
| `postman/Rice_Age_Portal.postman_collection.json` | Importable collection: 15 folders, 56 requests covering all 42 implemented operations |
| `postman/Rice_Age_Local.postman_environment.json` | Local environment template (no production secrets) |
| `postman/samples/report.pdf` | 148-byte sample report whose SHA-256 the collection already knows |
| `postman/samples/platen-bottom.png` | 70-byte sample platen image |
| `postman/build_collection.py` | Regenerates the collection after a contract change |
| `postman/validate_collection.py` | Cross-checks the collection against the app's OpenAPI document and the sample hashes |

> **Advisory positioning.** Device output is experimental pre-inspection data. Optical
> percentages are not statutory procurement measurements and the portal is not a
> certification authority. Nothing in this collection produces a statutory grade.

## 2. Install Postman

Download the desktop app from <https://www.postman.com/downloads/> and sign in (a free
account is enough) or choose "Skip and go to the app". The collection was authored for
the Postman v2.1 collection format.

## 3. Import the collection

1. Postman → **Import** → **Files**.
2. Select `postman/Rice_Age_Portal.postman_collection.json`.
3. Confirm. You should see `Rice Age Portal API` with folders 1–15.

## 4. Import the environment

1. **Import** → **Files** → `postman/Rice_Age_Local.postman_environment.json`.
2. Select **Rice Age Local** in the environment drop-down (top-right).
3. **Every request writes captured tokens back with `pm.environment.set`, so an active
   environment is required.** Without it, values are not stored between requests.

## 5. Configure the backend base URL

`base_url` defaults to `http://localhost:8001`, which matches the documented local
backend command:

```bash
cd backend
uvicorn app.main:app --reload --port 8001
```

Port 8000 is what `docker compose` exposes; if you use Compose, change `base_url` to
`http://localhost:8000`. Paths in the collection already include `/api/v1`, so do not
append it to `base_url`.

Enable **Settings → General → SSL certificate verification** only when you are on HTTPS;
locally it can stay on, since `http://localhost` is exempt.

## 6. Test credentials

The repository ships a development seed (`backend/dev_seed.py`) that creates two
departments (`DEPT-A`, `DEPT-B`), one device per department and three users:

| Role | Email | Password |
| --- | --- | --- |
| Super Admin | `super-admin@test.local` | `SuperAdmin123!` |
| Department Admin (DEPT-A) | `admin@test.local` | `Admin123!` |
| Department User (DEPT-A) | `user@test.local` | `User123!` |

These are **development fixtures, not product credentials**. Create your own account when
the database is not seeded:

- as Super Admin: `POST /api/v1/admin/departments` then `POST /api/v1/admin/users`, or
- directly with the supported CLI utilities, or
- by editing the seeded values in `backend/dev_seed.py` before running it.

Then update `admin_email` / `admin_password`, `user_email` / `user_password` and
`super_admin_email` / `super_admin_password` in your environment. Never commit a
production password, API key or device secret into the collection or environment file.

## 7. Run the login request

Open **2. Authentication → Login - Department Admin** and click **Send**.

The test script asserts `200`, `token_type = bearer`, and that the membership role is
`department_admin`; it then stores:

- `access_token` — a 15-minute bearer JWT used by every portal request,
- `user_id`, `department_id`.

The refresh token is **not** in the response body. It is an HttpOnly cookie named
`ra_refresh`, scoped to `/api/v1/auth`, `SameSite=Strict`. Postman stores it in its
cookie jar, so **do not disable cookies** or request 5 (refresh) will fail with `401
invalid_refresh`.

## 8. Test authenticated human-user APIs

With `access_token` set, send any request outside folder 7. Portal reads resolve the
department server-side:

- a Department Admin/User with one membership may omit `department_id`,
- a Super Admin **must** pass `department_id` (otherwise `400 department_required`),
- a request for a department you do not belong to returns `404 not_found`, never `403`,
  so existence is not disclosed.

Useful first checks: `4. User Administration → List users`, `8. Scan Management → Latest
completed scan`, `9. Scan History`, `10. Quality Analytics`.

Role boundaries that actually exist:

| Action | Super Admin | Department Admin | Department User |
| --- | --- | --- | --- |
| Portal reads (seven modules) | yes, must name `department_id` | own department | own department |
| Create/update departments | yes | no (403) | no (403) |
| List users / devices | yes | own department | no (403 department_admin required) |
| Create user | yes | own department, cannot grant super admin | no |
| Register device, assign, credentials | yes | no | no |
| Change a user's `is_super_admin`/`is_active` | yes | no | no |

## 9. Test IoT device APIs

Devices are a separate machine identity. They never use a human password.

1. **5. Device Administration → Register device (super admin)** — needs
   `super_admin_access_token`, which folder 2 request 3 stores. `device_id` and
   `device_uid` are captured.
2. **Issue device credential** — returns `client_id` and `client_secret` **once**;
   both are captured. If a credential is already active the API answers `409
   credential_exists`; run **Rotate** instead.
3. **7. IoT Device APIs → Device token (client credentials)** — posts
   `{"grant_type":"client_credentials","client_id":…,"client_secret":…}` to
   `/api/v1/device-auth/token` and stores `device_access_token` (scope `device:scan`).

The device token cannot call portal routes (`403 device_token_used_on_user_route`) and a
portal token cannot call device routes (`403 user_token_used_on_device_route`). Folder 15
proves both.

## 10. Submit a scan and upload attachments

The scan lifecycle is four calls:

1. `POST /api/v1/device/scans` — the schema 1.0 payload. Response `201` with `scan_id`,
   `required_attachments`, `optional_attachments`, `processing_status = awaiting_files`.
2. `POST /api/v1/device/scans/{scan_id}/attachments/prepare` — declares
   `role`, `content_type`, `size_bytes`, `sha256`, `filename`. Returns `upload_id`, the
   upload `url` (API path with local storage, presigned PUT with S3) and an expiry.
3. `PUT <upload url>` — raw bytes. The server re-computes SHA-256, checks the declared
   content type and the file magic bytes (`%PDF-`, PNG or JPEG), and marks the file
   `verified`.
4. `POST /api/v1/device/scans/{scan_id}/finalize` — requires the roles listed in
   `REQUIRED_ATTACHMENT_ROLES` (default `report_pdf,bottom_image`; `top_image` is
   optional), applies the device-supplied verdict and creates deduplicated
   notifications.

**Attachment hashes.** `report_sha256` (`f082ea2f…`) and `bottom_image_sha256`
(`c414cd0e…`) in the environment are the hashes of the two sample files. The PDF is sent
as a raw text body that is byte-identical to `samples/report.pdf`, so the report upload is
fully scriptable.

The PNG is binary, so Postman cannot send it as text: open **Upload bottom platen image**,
choose **Body → binary**, and select `postman/samples/platen-bottom.png`. If you replace
either file, recompute both `size_bytes` and `sha256` (see `samples/make_samples.py`).

Hardware note: this exercises the API contract only. Physical device integration —
sensor calibration, firmware mapping to schema 1.0, retry/offline behaviour — is **not**
implemented and is tracked in `REMAINING_IMPLEMENTATION_GUIDE.md`.

## 11. Test idempotent submissions

Idempotency is `(device_id, client_scan_id)` plus the canonical payload hash:

| Case | Result |
| --- | --- |
| First submission | `201`, `replayed: false`, new scan |
| Identical replay | `200`, `replayed: true`, same `scan_id`, no new rows, no new notification |
| Same `client_scan_id`, different bytes | `409 scan_conflict` with `existing_scan_id` |
| Replay of a failed scan | `409 scan_already_failed` |

The **Submit scan** request runs a pre-request script that sets a new
`client_scan_id` (`POSTMAN-<timestamp>`) on every run, so the submit → upload → finalize
chain stays repeatable. Set `reuse_scan=true` to deliberately resubmit the same id, and
`Finalize again - idempotent` shows `notifications_created: 0` on the second call.

## 12. Test department isolation

Folder **15** documents the boundary the backend actually enforces:

- `GET /scans/latest?department_id=<other>` → `404 not_found`
- `GET /scans/{id}?department_id=<other>` → `404`
- device token on a portal route → `403`
- human token on a device route → `403`

Run **3. Department Administration → List departments (super admin)** first: its test
script fills `other_department_id` with a department that differs from your own.

## 13. Common HTTP errors

Every error uses one envelope:

```json
{"error": {"code": "scan_conflict", "message": "…", "details": {"existing_scan_id": "…"}, "request_id": "…"}}
```

| Status | Meaning in this API | Typical codes |
| --- | --- | --- |
| 400 | Malformed request | `validation_error`, `department_required` |
| 401 | Missing/invalid token, bad login, bad refresh | `invalid_token`, `invalid_credentials`, `invalid_refresh`, `invalid_client` |
| 403 | Authenticated but not allowed, or wrong token type | `forbidden`, `account_inactive`, `device_suspended`, `device_unassigned`, `device_token_used_on_user_route`, `user_token_used_on_device_route` |
| 404 | Not found **or not visible** | `not_found`, `report_unavailable` |
| 409 | Conflict / state problem | `scan_conflict`, `credential_exists`, `email_taken`, `department_code_taken`, `missing_attachments`, `scan_not_finalizable` |
| 413 / 415 | Payload or file limits, wrong media type | `file_too_large`, `unsupported_media_type` |
| 422 | Schema-invalid payload or checksum mismatch | `validation_error`, `checksum_mismatch`, `invalid_timestamp` |
| 429 | Throttled (login, device token, scan submission) | `rate_limited`, `too_many_attempts` |
| 503 | Dependency unavailable (database or storage) | `dependency_unavailable` |

Quote `request_id` (also returned as the `X-Request-ID` header) when reporting a failure.

## 14. Run the complete collection

1. Select **Rice Age Local**, start the backend, and run folder **3** once (its list
   request fills `other_department_id`).
2. Choose **Run** on the collection (or `newman run`).
3. Three requests are deliberately guarded and are skipped unless you opt in:
   `enable_password_change`, `enable_credential_revoke`, `enable_reassignment`. They end
   sessions, break device auth, or change device ownership, so leave them `false` on any
   database you care about.
4. Sign in as Super Admin (folder 2, request 3) **after** the department-admin login if
   you also need `access_token` to stay on the admin account; each login replaces the
   environment token it writes (the super admin writes its own
   `super_admin_access_token`).
5. Re-running is safe: every run creates a new `client_scan_id`, new device and new user,
   and the collection tolerates `409` for records that already exist.

`newman` example:

```bash
npx newman run postman/Rice_Age_Portal.postman_collection.json \
  -e postman/Rice_Age_Local.postman_environment.json \
  --folder "1. Health & Readiness"
```

## 15. Resetting development test data safely

Never point this at production. For a local database, the safest reset is a disposable
one:

```bash
# a throwaway PostgreSQL for API experiments
docker run --name rice-age-postman-pg -e POSTGRES_PASSWORD=localpw \
  -e POSTGRES_DB=rice_age_demo -p 55433:5432 -d postgres:16-alpine

cd backend
DATABASE_URL="postgresql+psycopg://postgres:localpw@localhost:55433/rice_age_demo" \
  alembic upgrade head
DATABASE_URL="postgresql+psycopg://postgres:localpw@localhost:55433/rice_age_demo" \
  python dev_seed.py
```

Cleanup artefacts this collection creates, without touching other rows:

- scans: filter by `client_scan_id LIKE 'POSTMAN-%'`
- devices: `device_uid LIKE 'POSTMAN-%'`
- users: `email LIKE 'postman.user.%@test.local'`
- departments: code `PM-DEPT`

Uploaded files live under `STORAGE_LOCAL_ROOT` (default `backend/storage`). Reset the
whole demo database by dropping the container and running the three commands again —
`dev_seed.py` is idempotent and refuses to run when `RICE_AGE_ENV=production`.

## 16. Human authentication vs IoT device authentication

| | Human user | IoT device |
| --- | --- | --- |
| Identity | email + password (Argon2id) | `client_id` + `client_secret`, one per device |
| Login | `POST /api/v1/auth/login` | `POST /api/v1/device-auth/token` (`grant_type=client_credentials`) |
| Credential | 15-minute JWT, type `human` | 15-minute JWT, type `device`, scope `device:scan` |
| Session | rotating refresh cookie (`ra_refresh`), logout revokes it | no refresh token; re-authenticate with the secret |
| Roles | super admin / department admin / department user | none — a device is only a device |
| Department | from the user's memberships | from the device's active assignment, never the payload |
| Revocation | deactivate the user or sign out | revoke/rotate the credential; unassigned or suspended devices are refused |
| Can call | portal reads + admin (by role) | `/api/v1/device/*` only |

A device token on a portal route returns `403 device_token_used_on_user_route`; a human
token on a device route returns `403 user_token_used_on_device_route`.

## 17. Implemented operations (42)

Grouped by the collection folders. `auth` = human bearer, `super` = super admin,
`device` = device bearer.

**Health (2, public):** `GET /health`, `GET /health/ready`

**Authentication (5):** `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`,
`GET /auth/me`, `POST /auth/password/change`

**Departments (4):** `POST /admin/departments` (super), `GET /admin/departments` (super),
`GET /admin/departments/{id}` (own or super), `PATCH /admin/departments/{id}` (super)

**Users (6):** `POST /admin/users` (super, or dept admin in own department),
`GET /admin/users`, `GET /admin/users/{id}`, `PATCH /admin/users/{id}` (super),
`POST /admin/users/{id}/memberships`, `PATCH /admin/memberships/{id}`

**Devices (7):** `POST /admin/devices` (super), `GET /admin/devices`,
`GET /admin/devices/{id}`, `PATCH /admin/devices/{id}` (super),
`POST /admin/devices/{id}/credentials` (super), `.../credentials/rotate` (super),
`.../credentials/{credential_id}/revoke` (super)

**Assignments (2):** `GET /admin/devices/{id}/assignments` (super),
`POST /admin/devices/{id}/assignments` (super)

**Device APIs (5):** `POST /device-auth/token`, `POST /device/scans`,
`POST /device/scans/{id}/attachments/prepare`,
`PUT /device/scans/{id}/files/{upload_id}`, `POST /device/scans/{id}/finalize`,
`GET /device/scans/{id}/status` — six calls, five paths under `/device`

**Scan management (4):** `GET /scans/latest`, `GET /scans/{id}`,
`GET /scans/{id}/report`, `GET /scans/{id}/report/download`

**History / analytics (6):** `GET /scans/history`, `GET /scans/analytics/quality`,
`GET /scans/analytics/rice-age`, `GET /scans/analytics/reports`,
`GET /scans/analytics/batch-comparison`, `GET /scans/notifications`

By method: **GET 21, POST 16, PATCH 4, PUT 1**.

### Not implemented (do not assume these exist)

| Gap | Impact |
| --- | --- |
| No audit read API | Audit rows are written (`audit_events`) but there is no HTTP read endpoint, so the collection has no audit folder |
| No notification write API | `read_at` is returned but there is no mark-as-read endpoint; the UI label is inert |
| No password reset / email | Only authenticated password change exists (`POST /auth/password/change`) |
| No admin console screens | Admin APIs exist; the frontend has no admin UI |
| No scan-history filter UI wiring | The API supports filters; the page renders the filter panel but only requests the default page |
| No PATCH/DELETE on scans or reports | Scans are immutable once ingested |
| No DELETE anywhere | Departments, users and devices are deactivated, never deleted |
| Image/platen delivery API | Files are stored privately; only the report PDF is served (platen images have no download endpoint yet) |
| No verdict correction endpoint | Verdict corrections are listed as audited future behaviour |

## 18. Regenerating and validating

```bash
python postman/build_collection.py          # rewrite the collection JSON
python postman/validate_collection.py       # compare with the app's OpenAPI document
```

The validator fails when a request has no matching backend operation, when an operation
is not covered, or when the sample hashes/sizes drift. Run it after any contract change
so the collection cannot silently rot.
