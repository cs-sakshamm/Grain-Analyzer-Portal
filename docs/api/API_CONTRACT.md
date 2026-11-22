# API Contract — Rice Age Portal

**Version:** v1 (design baseline)
**Status:** Phase 2. Endpoint paths follow SOR §5.2.

Implemented and tested: health/readiness; human login, refresh, logout, `me` and
password change; department/user/membership administration; device registration,
status, assignment history, reassignment, credential issue/rotate/revoke; device
token issuance; scan submission with idempotency; attachment prepare/upload/finalize;
device scan status; portal latest completed scan, scan detail and report
metadata/download.

Also implemented (see §4.9 for the delivered paths and shapes): scan history listing,
quality and rice-age analytics, report listing, batch comparison and the notifications
inbox. The paths in §4.2 and §4.5–4.8 are the original design baseline and were adjusted
when implemented; §4.9 is authoritative for what runs today.

**Documented only (not implemented):** the password-reset flow (§2.5, also awaits
DR-011), notification read state, an audit read API, platen-image delivery and verdict
corrections.

The device contract is provisional: authentication mechanism, payload fields, file
types and size limits await the firmware team (DR-004…DR-007). Changes to this
document and `device-payload.schema.json` ship together.

---

## 1. Conventions

| Concern | Rule |
| --- | --- |
| Base path | `/api/v1` |
| Content type | `application/json` unless stated; uploads use the declared media type |
| Field naming | `snake_case` |
| Identifiers | UUIDv4 strings for server entities; device-native strings for codes |
| Timestamps | RFC 3339 with offset, e.g. `2026-11-20T16:37:52+05:30`; server times are UTC |
| Numbers | Measurements are JSON numbers; the server persists `NUMERIC`, so clients must not assume binary-float precision |
| Request correlation | `X-Request-ID` accepted from clients (UUID-ish, ≤64 chars) and echoed; otherwise generated |
| Pagination | `page` (≥1, default 1) and `page_size` (1–100, default 25) |
| Auth | `Authorization: Bearer <access_token>` — human and device tokens are not interchangeable |
| Versioning | Path version; additive changes within v1; breaking changes require `/api/v2` and a deprecation window |

### 1.1 Error envelope

All errors use one shape:

```json
{
  "error": {
    "code": "scan_conflict",
    "message": "A different payload was already accepted for this client_scan_id.",
    "details": { "existing_scan_id": "3f1c…" },
    "request_id": "0b6f9c1e-7a4d-4a1c-9d55-2f0d1d0f7a11"
  }
}
```

Rules: `message` is safe for end users; `details` never contains stack traces, SQL,
secrets, storage keys, or another department's identifiers. Department-scoped
resource access by a non-member returns `404` where existence itself is sensitive and
`403` where the resource is already known to the caller.

### 1.2 Status code policy

| Code | When |
| --- | --- |
| 200 | Successful read, idempotent replay, finalize of an already-completed scan |
| 201 | Resource created (scan accepted, department/device/user created) |
| 202 | Accepted for asynchronous processing |
| 204 | Successful deletion/no-content actions (e.g. mark-read) |
| 400 | Malformed request (unparsable JSON, bad query type) |
| 401 | Missing/invalid/expired credentials |
| 403 | Authenticated but not permitted (role, department, device mismatch) |
| 404 | Not found **or** not visible to the caller |
| 409 | Idempotency conflict; illegal state transition; duplicate unique value |
| 422 | Schema validation failure with field-level `details.fields` |
| 429 | Rate limited; includes `Retry-After` |
| 500 | Unhandled server error |
| 503 | Dependency unavailable (database/storage) — readiness failure |

### 1.3 Role and scope model

| Symbol | Meaning |
| --- | --- |
| `public` | No authentication |
| `user` | Any active human account with at least one active membership, or super admin |
| `dept_admin` | `super_admin` + `department_admin` |
| `super_admin` | Global administrator only |
| `device` | Device token only |

Department scope is applied to every query:

- `department_user` / `department_admin` → only their own department(s).
- `super_admin` → must pass an explicit `department_id` for department-scoped reads and
  the access is audited. Omitting it returns `400 department_required` for endpoints
  that cannot be safely aggregated across departments.
- Cross-department access attempts return `403`/`404` with no data disclosure.

---

## 2. Human authentication

### 2.1 `POST /api/v1/auth/login`

| Field | Value |
| --- | --- |
| Auth | public |
| Purpose | Exchange email + password for an access token and a refresh session |

Request:

```json
{ "email": "user@department.gov.in", "password": "…" }
```

Response `200`:

```json
{
  "access_token": "eyJ…",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "6a1d…",
    "email": "user@department.gov.in",
    "full_name": "A. Officer",
    "is_super_admin": false,
    "memberships": [
      { "department_id": "1d2c…", "department_code": "QA-LAB", "role": "department_user" }
    ]
  }
}
```

Sets `ra_refresh` cookie: `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth`.

Errors: `401 invalid_credentials` (identical response and timing for unknown email and
wrong password), `403 account_inactive`, `429 too_many_attempts`.

### 2.2 `POST /api/v1/auth/refresh`

Auth: refresh cookie. Rotates the refresh token and returns a new access token +
`user` object (same shape as login). Reuse of a rotated token revokes the whole token
family and returns `401 session_revoked`.

### 2.3 `POST /api/v1/auth/logout`

Auth: `user`. Revokes the current session family and clears the cookie. `204`.

### 2.4 `GET /api/v1/auth/me`

Auth: `user`. Returns the current user, memberships and permitted capabilities. Used to
hydrate the frontend after refresh.

### 2.5 `POST /api/v1/auth/password/change`

Auth: `user`. Body `{ current_password, new_password }`. Revokes other sessions on
success. Password reset by email is **not** designed yet (DR-011).

---

## 3. Device API

Device tokens are short-lived bearer tokens obtained with per-device credentials. They
carry scope `device:scan` and a `device_id` claim. A device token can never call human
endpoints (`403 device_token_used_on_user_route`), and a human token can never call
device routes.

### 3.1 `POST /api/v1/device-auth/token`

| Field | Value |
| --- | --- |
| Auth | public (client credentials) |
| Rate limit | 10 requests/minute per `client_id`, 60/minute per IP |
| Purpose | Issue a short-lived device access token |

Request:

```json
{ "grant_type": "client_credentials", "client_id": "dev_7f3c…", "client_secret": "…" }
```

Response `200`:

```json
{ "access_token": "eyJ…", "token_type": "bearer", "expires_in": 900, "device_id": "RICE-DEVICE-001", "scope": "device:scan" }
```

Validation:

1. `client_id` exists and belongs to a device.
2. Secret verifies against the stored Argon2id hash.
3. Credential is not revoked/expired; device status is `active`.
4. Device has an active department assignment.
5. Failure returns `401 invalid_client` without revealing which check failed.

Errors: `400 unsupported_grant_type`, `401 invalid_client`, `403 device_suspended`,
`403 device_unassigned`, `429 too_many_attempts`.

### 3.2 `POST /api/v1/device/scans`

| Field | Value |
| --- | --- |
| Auth | `device` |
| Purpose | Submit structured analysis JSON; create or replay a scan |
| Idempotency | `(authenticated device, client_scan_id)` |
| Body | Validated against `docs/api/device-payload.schema.json` |

Request (abridged; full SOR example accepted):

```json
{
  "schema_version": "1.0",
  "client_scan_id": "SCAN-0038",
  "sample": { "sample_id": "Sample-0038", "batch_id": "BATCH-2026-001", "lot_id": "LOT-A" },
  "analyzed_at": "2026-11-20T16:37:52+05:30",
  "analysis": {
    "grain_count": 363,
    "avg_length_mm": 5.25,
    "avg_breadth_mm": 2.61,
    "measurements": [
      { "code": "head_rice", "value": 50.68, "unit": "percent", "basis": "estimated_mass_percent", "is_estimated": true },
      { "code": "big_broken", "value": 39.94, "unit": "percent", "basis": "count_percent" }
    ]
  },
  "rice_age": {
    "age_min_months": 8, "age_max_months": 10, "age_category": "8-10 Months",
    "proportion_percent": 100, "unit": "months", "method": "biochemical_colour",
    "validation_status": "unvalidated", "raw_value": "8-10 Months (100%)"
  },
  "evaluation": { "overall": "flagged", "ruleset_version": "demo-v1", "certification_status": "advisory_only" },
  "attachments": [{ "role": "report_pdf", "content_type": "application/pdf", "filename": "Sample-0038.pdf" }]
}
```

Response `201 Created`:

```json
{
  "scan_id": "0f8b…",
  "client_scan_id": "SCAN-0038",
  "processing_status": "awaiting_files",
  "required_attachments": ["report_pdf", "bottom_image"],
  "optional_attachments": ["top_image"],
  "upload_expires_at": "2026-11-21T16:37:52Z",
  "received_at": "2026-11-20T16:38:10Z"
}
```

Idempotency behaviour:

| Situation | Result |
| --- | --- |
| New `(device, client_scan_id)` | `201` with new scan |
| Same key, canonical payload hash identical | `200` with the existing scan (no new rows, no new notifications) |
| Same key, different payload | `409 scan_conflict` with `existing_scan_id`; original retained |
| Same key, original scan `failed` | `409 scan_already_failed` with the failure code; the device must use a new `client_scan_id` |
| Same key, original scan `completed` and attachments verified | `200` with the completed scan |

Validation rules:

1. Token is a device token; `device_id` claim resolves to an active device.
2. `device_id` in the payload (if present) equals the token's device → else `403 device_mismatch`.
3. Any `department_id` in the payload is ignored (never read).
4. Active assignment exists; its department is snapshotted into the scan.
5. Payload validates against the schema; unknown top-level fields → `422`.
6. `analyzed_at` is not more than 1 hour in the future (provisional) → `422 invalid_timestamp`.
7. `measurements` bases are internally consistent (unit/basis pairs) → `422`.
8. Attachments manifest roles are unique except `other`.

Errors: `401 invalid_token`, `403 device_suspended`, `403 device_mismatch`,
`409 scan_conflict`, `422 schema_invalid`, `429 rate_limited`, `503 dependency_unavailable`.

### 3.3 `POST /api/v1/device/scans/{scan_id}/attachments/prepare`

| Field | Value |
| --- | --- |
| Auth | `device` (must own the scan) |
| Purpose | Obtain a protected upload target for one attachment role |

Request:

```json
{ "role": "report_pdf", "content_type": "application/pdf", "size_bytes": 184320, "sha256": "9f2c…", "filename": "Sample-0038.pdf" }
```

Response `200`:

```json
{
  "upload_id": "5b7e…",
  "method": "PUT",
  "url": "https://storage.example/presigned…",
  "headers": { "Content-Type": "application/pdf", "x-amz-checksum-sha256": "…" },
  "expires_at": "2026-11-20T16:48:10Z"
}
```

In development (`STORAGE_BACKEND=local`) `url` is
`/api/v1/device/scans/{scan_id}/files/{upload_id}` on the backend, authenticated by the
same device token.

Validation: scan belongs to the token's device; scan is not `completed`; role not
already `verified`; size within configured limit; `content_type` in the role allowlist;
`sha256` present and well-formed. Re-preparing an unverified role supersedes the prior
attempt and returns a new `upload_id`.

Errors: `403 scan_not_owned`, `404 scan_not_found`, `409 role_already_verified`,
`413 file_too_large`, `415 unsupported_media_type`, `422 invalid_checksum`.

### 3.4 `PUT /api/v1/device/scans/{scan_id}/files/{upload_id}` (development only)

Auth: `device`. `Content-Type` must equal the prepared type. Body is the raw bytes.
Verifies size and SHA-256 during streaming; on mismatch the object is discarded and
`422 checksum_mismatch` returned. `201` with `{ "upload_id", "received_bytes", "sha256" }`.
This route does not exist when `STORAGE_BACKEND=s3` (devices upload directly to the
presigned URL).

### 3.5 `POST /api/v1/device/scans/{scan_id}/finalize`

| Field | Value |
| --- | --- |
| Auth | `device` (owner) |
| Purpose | Verify attachments and complete the scan |
| Idempotency | Repeating on `completed` returns `200` and changes nothing |

Request: `{}` (no body required) or `{ "expected_attachments": ["report_pdf", "bottom_image"] }`.

Response `200`:

```json
{
  "scan_id": "0f8b…",
  "processing_status": "completed",
  "quality_verdict": "flagged",
  "finalized_at": "2026-11-20T16:40:02Z",
  "notifications_created": 2
}
```

Processing on finalize: verify each required file exists, size/hash/MIME match, required
roles present, then in one transaction set `completed`, `finalized_at`, persist the
verdict from the evaluation block, and create deduplicated notifications. Any failure
sets `failed` with a `failure_code` and creates a technical `upload_failed` notification
— never a quality verdict.

Errors: `403 scan_not_owned`, `409 missing_attachments` (`details.roles`),
`409 scan_not_finalizable` (wrong state), `422 attachment_verification_failed`,
`503 storage_unavailable`.

### 3.6 `GET /api/v1/device/scans/{scan_id}/status`

Auth: `device` (owner). Returns `{ scan_id, client_scan_id, processing_status,
quality_verdict, failure_code, failure_detail, received_at, finalized_at,
attachments: [{ role, upload_status }] }`. `404` if the scan does not belong to the
device. Polling guidance: 5 s initial, exponential to 60 s; no rate-limit penalty for
one poll per 5 s per device.

### 3.7 Device lifecycle summary

```text
token → POST scans (received → awaiting_files) → prepare/upload per role
      → finalize (verifying) → completed | failed
      → status polling until terminal
```

Retry guidance: network errors and `5xx`/`429` are retryable with backoff; `409` means
do not retry the same key with changed content; `422` requires a payload fix and a new
`client_scan_id` only if the previous scan was already accepted.

---

## 4. Portal API

### 4.1 `GET /api/v1/scans/latest`

| Field | Value |
| --- | --- |
| Auth | `user` |
| Purpose | Latest **completed** scan for the caller's department |
| Query | `department_id` (required for super admin; rejected for others) |

Response `200` (shape shared with scan detail):

```json
{
  "scan": {
    "id": "0f8b…",
    "sample_id": "Sample-0038",
    "batch_code": "BATCH-2026-001",
    "lot_code": "LOT-A",
    "variety": "Raw Rice",
    "analyzed_at": "2026-11-20T16:37:52+05:30",
    "received_at": "2026-11-20T16:38:10Z",
    "finalized_at": "2026-11-20T16:40:02Z",
    "processing_status": "completed",
    "quality_verdict": "flagged",
    "ruleset_version": "demo-v1",
    "certification_status": "advisory_only",
    "device": { "id": "…", "device_uid": "RICE-DEVICE-001", "friendly_name": "Kiosk 1" },
    "department": { "id": "…", "code": "QA-LAB", "name": "Quality Lab" },
    "grain_count": 363,
    "measurements": [
      { "metric_code": "head_rice", "value": 50.68, "unit": "percent", "basis": "estimated_mass_percent", "is_estimated": true },
      { "metric_code": "big_broken", "value": 39.94, "unit": "percent", "basis": "count_percent", "is_estimated": false }
    ],
    "age": {
      "age_min_months": 8, "age_max_months": 10, "age_category": "8-10 Months",
      "proportion_percent": 100, "unit": "months", "method": "biochemical_colour",
      "model_version": null, "validation_status": "unvalidated"
    },
    "files": [
      { "role": "report_pdf", "available": true, "filename": "Sample-0038.pdf", "size_bytes": 184320 },
      { "role": "bottom_image", "available": true, "width_px": 1280, "height_px": 960 },
      { "role": "top_image", "available": false }
    ],
    "advisory": "Pre-inspection advisory only. Optical estimates are not statutory procurement measurements."
  },
  "as_of": "2026-11-20T16:41:00Z"
}
```

Behaviour:

- Returns `204 No Content` when the department has no completed scan.
- Non-completed scans are never returned by this endpoint.
- `age` is `null` when no age result exists; the client renders "Not available".
- `files[].available` reflects `upload_status = 'verified'`; no URLs are included.

### 4.2 `GET /api/v1/scans`

Auth: `user`. Query:

| Param | Type | Notes |
| --- | --- | --- |
| `department_id` | uuid | Required for super admin |
| `from`, `to` | date-time | Filters on `analyzed_at`, inclusive start, exclusive end |
| `sample_id` | string | Exact or prefix match (server-defined, prefix ≥3 chars) |
| `batch_id` / `lot_id` | string | Batch/lot code within the department |
| `device_id` | uuid | Devices of that department only |
| `quality_verdict` | enum | `pass`,`flagged`,`inconclusive`,`lab_confirmation_required` |
| `has_age` | bool | `true` only scans with an age result |
| `page`, `page_size` | int | Defaults 1 / 25; max 100 |
| `sort` | enum | `analyzed_at_desc` (default), `analyzed_at_asc` |

Only completed scans are listed. Response:

```json
{
  "items": [
    {
      "id": "0f8b…", "sample_id": "Sample-0038", "batch_code": "BATCH-2026-001",
      "lot_code": "LOT-A", "analyzed_at": "…", "device_uid": "RICE-DEVICE-001",
      "quality_verdict": "flagged", "has_age": true, "has_report": true,
      "age_summary": "8-10 Months"
    }
  ],
  "page": 1, "page_size": 25, "total": 87, "total_pages": 4
}
```

`total` counts only visible rows; no cross-department leakage into counts.

### 4.3 `GET /api/v1/scans/{scan_id}`

Auth: `user`. Returns the scan detail shape from §4.1 plus `evaluations` (per-parameter
verdicts) and `raw_payload` **only** when the caller is `super_admin` (audited) — other
roles receive normalised data and file metadata only. Unknown or out-of-scope IDs
return `404`.

### 4.4 `GET /api/v1/scans/{scan_id}/report`

Auth: `user`. Purpose: obtain the original device PDF.

- Default response: `302`-free JSON `{ "url": "…", "expires_at": "…", "filename": "…", "size_bytes": 184320, "sha256": "…" }` where `url` is a short-lived signed URL (production) or an authenticated streaming route (development).
- `?disposition=inline` requests preview; the API sets `Content-Disposition` accordingly.
- Requires `report_pdf` to be `verified`; otherwise `404 report_unavailable`.
- Every download is audited with actor, scan, file and (for super admin) the reason.

Errors: `403`/`404` for out-of-scope scans, `404 report_unavailable`, `410 file_expired`.

### 4.5 `GET /api/v1/analytics/quality`

Auth: `user`. Query: `department_id` (super admin), `from`, `to`, `batch_id`, `lot_id`,
`device_id`, `metric_code` (repeatable), `basis` (repeatable), `granularity=day|week|month`.

Response:

```json
{
  "scope": { "department_id": "…", "from": "…", "to": "…", "filters": { "batch_id": null } },
  "scan_volume": 42,
  "verdict_distribution": { "pass": 20, "flagged": 18, "inconclusive": 3, "lab_confirmation_required": 1 },
  "series": [
    {
      "metric_code": "head_rice",
      "label": "Head Rice",
      "basis": "estimated_mass_percent",
      "unit": "percent",
      "n": 42,
      "points": [{ "bucket": "2026-11-01", "value": 50.68, "n": 3 }],
      "aggregation": "mean"
    }
  ],
  "excluded": [{ "metric_code": "head_rice", "basis": "count_percent", "reason": "insufficient_data" }]
}
```

Rules: one series per `(metric_code, basis)`; never a blended average; `n` is always
present; incompatible bases produce separate series; the response states the
aggregation method. Empty period → `scan_volume: 0` with empty series (never an error).
An unsupported metric returns `422 unsupported_metric`.

### 4.6 `GET /api/v1/analytics/age`

Auth: `user`. Query: same filters plus `model_version` (repeatable).

Response:

```json
{
  "scope": { "department_id": "…", "from": "…", "to": "…" },
  "availability": { "scans_in_scope": 42, "with_age": 17, "without_age": 25 },
  "units": ["months"],
  "series": [
    {
      "method": "biochemical_colour", "model_version": null, "unit": "months", "n": 17,
      "aggregation": "mean_range",
      "points": [{ "bucket": "2026-11-01", "age_min_months": 8, "age_max_months": 10, "n": 2 }]
    }
  ],
  "warnings": ["3 scans reported a different method and were excluded from the trend"]
}
```

Rules: scans without an age result are excluded from series and counted in
`availability`; mixed methods/model versions are never merged silently; with fewer than
the minimum sample (provisional `n < 3`) the series is returned with
`"insufficient_data": true` rather than hidden.

### 4.7 `POST /api/v1/batches/compare`

Auth: `user`. Purpose: side-by-side comparison of 2–10 batches in one department.

Request:

```json
{ "batch_ids": ["uuid-a", "uuid-b"], "from": null, "to": null, "metric_codes": ["head_rice", "big_broken"] }
```

Response:

```json
{
  "batches": [
    {
      "batch_id": "uuid-a", "batch_code": "BATCH-2026-001", "lot_code": "LOT-A",
      "scan_count": 12, "date_range": { "from": "…", "to": "…" },
      "verdict_distribution": { "pass": 7, "flagged": 5 },
      "metrics": [
        { "metric_code": "head_rice", "basis": "estimated_mass_percent", "unit": "percent", "n": 12, "mean": 71.9, "min": 60.1, "max": 80.2 }
      ],
      "age": { "available": 5, "unavailable": 7, "method": "biochemical_colour", "model_version": null }
    }
  ],
  "comparability": {
    "comparable": true,
    "warnings": [
      { "code": "different_measurement_bases", "metric_code": "head_rice", "message": "Batch A reports count basis; Batch B reports estimated mass basis. Values are not directly comparable." },
      { "code": "different_ruleset_versions", "message": "Ruleset demo-v1 and demo-v2 are both present." },
      { "code": "missing_age_data", "message": "Batch B has no age results." }
    ]
  },
  "ranking": null,
  "ranking_note": "No objective quality ranking is produced without an approved scoring formula."
}
```

Validation: 2–10 distinct batch IDs, all in the caller's department (`404` otherwise),
each with ≥1 completed scan (otherwise `422 batch_without_completed_scans`).

### 4.8 `GET /api/v1/notifications`

Auth: `user`. Query `unread_only` (bool), `page`, `page_size`.

```json
{
  "items": [
    {
      "id": "…", "event_type": "quality_flagged", "severity": "warning",
      "title": "Quality flag on Sample-0038", "body": "…",
      "scan_id": "0f8b…", "created_at": "…", "read_at": null
    }
  ],
  "unread_count": 4, "page": 1, "page_size": 25, "total": 31
}
```

Notifications are scoped to the caller's department **and** to recipient rows for that
user. Marking read: `POST /api/v1/notifications/{id}/read` → `204`; marking an alert
addressed to another user returns `404`.

---

### 4.9 Implemented portal read endpoints (authoritative)

All require a human bearer token. Department scope is resolved server-side; a super admin
must pass `department_id`. `start_date` / `end_date` filter `analyzed_at`.

| Method | Path | Response |
| --- | --- | --- |
| GET | `/api/v1/scans/latest` | §4.1 scan detail, or `204` when the department has no completed scan |
| GET | `/api/v1/scans/history` | `{items, total, page, per_page, pages}` |
| GET | `/api/v1/scans/{scan_id}` | §4.1 scan detail |
| GET | `/api/v1/scans/{scan_id}/report` | `{url, expires_at, filename, size_bytes, sha256, advisory}` |
| GET | `/api/v1/scans/{scan_id}/report/download` | Streamed PDF, `Cache-Control: no-store`; `?disposition=attachment\|inline` |
| GET | `/api/v1/scans/analytics/quality` | `{total_scans, quality_distribution, status_distribution, parameter_summary}` |
| GET | `/api/v1/scans/analytics/rice-age` | `{total_scans_with_age, age_results[]}` with flat age fields |
| GET | `/api/v1/scans/analytics/reports` | `{items[]}` with `has_report`, `report_filename`, `age_available` |
| GET | `/api/v1/scans/analytics/batch-comparison` | `{batches: {<batch_code>: [{scan_id, sample_id, measurements: {basis: [...]}}]}}` |
| GET | `/api/v1/scans/notifications` | `{items[]}` for the caller only; `?unread_only=` supported |

History filters: `batch_code`, `device_id`, `processing_status`, `quality_verdict`,
`start_date`, `end_date`, `page`, `per_page`. `parameter_summary` is keyed by
`metric_code` then `basis_unit` (`{count, min, max, avg}`) so incompatible bases are
never blended. `age_results` carries `age_value_months`, `age_min_months`,
`age_max_months`, `age_category`, `proportion_percent`, `unit`, `method`,
`model_version`, `validation_status` per scan; missing age is `null`, never `0`.

Static paths are declared before `/scans/{scan_id}` in the router; otherwise `history`
and `notifications` would be parsed as scan identifiers.

## 5. Administration API

All admin endpoints require `Authorization: Bearer`, are department-scoped where
applicable, and audit every mutation.

### 5.1 Departments

| Method | Path | Roles | Purpose |
| --- | --- | --- | --- |
| GET | `/admin/departments` | `super_admin` | List all departments (active/inactive) |
| POST | `/admin/departments` | `super_admin` | Create `{ code, name, location? }` → `201` |
| GET | `/admin/departments/{id}` | `super_admin`, own `department_admin` | Detail |
| PATCH | `/admin/departments/{id}` | `super_admin` | Update `name`, `location`, `is_active` (code is immutable) |

`code` uniqueness violation → `409 department_code_taken`. Deactivation with active
devices returns `409 department_has_active_devices` unless `?force=true` (audited).

### 5.2 Users and memberships

| Method | Path | Roles | Purpose |
| --- | --- | --- | --- |
| GET | `/admin/users` | `super_admin`; `department_admin` (own department only) | List users |
| POST | `/admin/users` | `super_admin`; `department_admin` (membership limited to own department) | Create user + initial membership |
| GET | `/admin/users/{id}` | `super_admin`; `department_admin` if the user shares the department | Detail |
| PATCH | `/admin/users/{id}` | `super_admin` | Update name, active state, super-admin flag (audited) |
| POST | `/admin/users/{id}/memberships` | `super_admin`; `department_admin` (own department) | Assign department role |
| PATCH | `/admin/memberships/{id}` | `super_admin`; `department_admin` (own department) | Change role or deactivate |
| POST | `/admin/users/{id}/password-reset` | `super_admin` | Issue a one-time reset token (flow pending DR-011) |

Rules: a `department_admin` cannot create or promote a `super_admin`, cannot manage a
user outside their department, and cannot grant a role they do not hold. Exact
Department Admin capabilities are pending DR-019; until confirmed, the API treats them
as **own-department user creation and role change only**, and this is enforced in the
service layer rather than assumed to be the final policy.

### 5.3 Devices, assignments and credentials

| Method | Path | Roles | Purpose |
| --- | --- | --- | --- |
| GET | `/admin/devices` | `super_admin`; `department_admin` (own department, read-only) | List with status, last seen, active department |
| POST | `/admin/devices` | `super_admin` | Register device `{ device_uid, serial_number, model?, firmware_version?, installation_location?, department_id }` |
| GET | `/admin/devices/{id}` | `super_admin`; `department_admin` if assigned to their department | Detail + assignment history |
| PATCH | `/admin/devices/{id}` | `super_admin` | Update metadata or status (`active`, `suspended`, `retired`) |
| GET | `/admin/devices/{id}/assignments` | `super_admin`; `department_admin` (own department) | Assignment history with effective periods |
| POST | `/admin/devices/{id}/assignments` | `super_admin` | Reassign `{ department_id, reason? }`; closes the active row and inserts a new one |
| POST | `/admin/devices/{id}/credentials` | `super_admin` | Issue initial credential; returns `client_id` + secret **once** |
| POST | `/admin/devices/{id}/credentials/rotate` | `super_admin` | Rotate; returns new secret once, revokes the previous credential |
| POST | `/admin/devices/{id}/credentials/{credential_id}/revoke` | `super_admin` | Revoke without replacement (device offline) |

Registration response includes the plaintext device secret exactly once; it is never
retrievable again and never written to logs or audit metadata.

Reassignment semantics: only the active assignment is closed; historical scans keep
their original `department_id`; the response includes `previous_department_id`,
`new_department_id`, `effective_from`, and `affected_scans: 0` to make the
non-moving behaviour explicit.

### 5.4 Audit logs

| Method | Path | Roles | Purpose |
| --- | --- | --- | --- |
| GET | `/admin/audit-logs` | `super_admin` | Filtered, paginated audit review |

Query: `from`, `to`, `actor_user_id`, `actor_device_id`, `department_id`, `action`,
`target_type`, `target_id`, `page`, `page_size`. Read-only; no endpoint mutates or
deletes audit rows.

---

## 6. Department-scope enforcement summary

| Endpoint group | Scope applied | Super admin behaviour |
| --- | --- | --- |
| `/scans/latest`, `/scans`, `/scans/{id}` | `scans.department_id = caller department` | `department_id` required; audited |
| `/scans/{id}/report` | scan scope + verified file | same; audited with file ID |
| `/analytics/*` | department + completed scans only | `department_id` required; audited |
| `/batches/compare` | every batch validated against department | `department_id` required; audited |
| `/notifications` | department + recipient row | own recipient rows only (no global inbox) |
| `/admin/*` | role + department per row | global |

Implementation note: scope is applied in the service/repository layer, not the router.
The same functions are reused by any future worker so department isolation cannot be
bypassed by a new entry point.

---

## 7. Error code reference

| Code | HTTP | Meaning |
| --- | --- | --- |
| `validation_error` | 422 | Schema/field validation failed; `details.fields` present |
| `invalid_credentials` | 401 | Login failed |
| `session_revoked` | 401 | Refresh token reuse detected or session revoked |
| `invalid_token` | 401 | Access token invalid/expired |
| `invalid_client` | 401 | Device credential rejected |
| `device_mismatch` | 403 | Payload device differs from authenticated device |
| `device_suspended` | 403 | Device not active |
| `device_unassigned` | 403 | No active department assignment |
| `forbidden` | 403 | Role not permitted |
| `not_found` | 404 | Missing or not visible |
| `scan_conflict` | 409 | Same idempotency key, different payload |
| `scan_already_failed` | 409 | Retry of a terminally failed scan |
| `missing_attachments` | 409 | Required roles absent at finalize |
| `role_already_verified` | 409 | Re-preparing a verified attachment |
| `scan_not_finalizable` | 409 | Illegal state transition |
| `department_required` | 400 | Super admin omitted `department_id` |
| `file_too_large` | 413 | Declared size above configured limit |
| `unsupported_media_type` | 415 | Type outside the role allowlist |
| `checksum_mismatch` | 422 | Uploaded bytes do not match declared SHA-256 |
| `rate_limited` | 429 | Throttled; `Retry-After` set |
| `dependency_unavailable` | 503 | Database/storage unavailable |

---

## 8. Contract change process

1. Any field addition/removal/rename updates this document **and**
   `device-payload.schema.json` in the same commit.
2. Device-facing changes are marked `PROVISIONAL` until the firmware team confirms them,
   and linked to a decision-register entry.
3. Additive optional fields may ship within v1; required-field changes need a new
   `schema_version` and an acceptance window for older devices.
4. Deprecations are announced in this document with a removal version.
5. OpenAPI is generated from the implementation once endpoints exist; this document
   remains the reviewable contract of record for Phase 1.
