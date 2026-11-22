# Security Architecture — Rice Age Portal

**Status:** Phase 1 design baseline. Implementation status is stated per section; do not
read a design description as a working control.

Sources: SOR §3 (authorization), §9.1 (security controls), PRD §2.1 and §12, and the
Phase 1 rules on department isolation, device identity and file access.

---

## 1. Principles

1. **Two identity planes.** Humans and IoT devices authenticate through separate
   mechanisms with separate credentials, tokens, scopes and endpoints. A device identity
   is never a user account and cannot reach the human portal.
2. **Server-side authority.** Every read, write, aggregate and download is authorized in
   the backend. Frontend hiding is presentation only.
3. **Department isolation is a data rule, not a filter.** Scope is applied in the service
   layer, and `scans.department_id` is an immutable acceptance-time snapshot.
4. **Least privilege.** Tokens carry only the scopes needed; admin capabilities are
   explicit; super-admin actions are audited.
5. **Private by default.** Files, reports and images are never public; access is granted
   per request and expires.
6. **Nothing invented.** Security decisions that depend on stakeholder policy (retention,
   email channel, deployment model) stay open until confirmed.
7. **Fail closed, disclose nothing.** Denials are indistinguishable from absence where
   existence is sensitive; errors carry a correlation ID, not internals.

---

## 2. Human authentication

### 2.1 Account lifecycle

- Accounts are provisioned by administrators (`super_admin`, or `department_admin` for
  their own department subject to DR-019). **No public self-registration.**
- Deactivation (`users.is_active = false`) blocks login immediately and revokes all
  sessions. Accounts are never reused for another person.
- Email changes require a super-admin action and re-verification; the login identifier is
  case-insensitive (`citext`).

### 2.2 Password storage

- **Argon2id** via `argon2-cffi`, encoded string stored in `users.password_hash`.
- Parameters: memory ≥ 64 MiB, iterations ≥ 3, parallelism 2 (tuned once on the
  deployment host and recorded in configuration; rehash on successful login when
  parameters change).
- Passwords are never logged, never emailed, never stored reversibly, and never included
  in audit metadata.
- Minimum policy (provisional until confirmed): ≥ 12 characters, deny a small
  compromised/common-password list, allow passphrases, no forced composition rules, no
  periodic rotation.
- Login comparison is constant-time and identical for unknown email vs wrong password
  (same status, similar timing, generic message).

### 2.3 Tokens and sessions

| Artifact | Design |
| --- | --- |
| Access token | JWT (HS256 with a per-environment secret, or RS256 when a managed identity provider is chosen), 15-minute TTL, claims: `sub`, `typ=user`, `is_super_admin`, `departments` (IDs + roles), `jti`, `iat`, `exp` |
| Refresh token | Opaque 256-bit random value, stored **only** as SHA-256 in `user_sessions.refresh_token_hash`, 8-hour idle / 7-day absolute TTL |
| Transport | Access token in memory in the browser, sent as `Authorization: Bearer`; refresh token in `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth` cookie |
| Rotation | Every refresh issues a new refresh token and revokes the old row |
| Reuse detection | Presenting an already-rotated token revokes the entire `token_family_id` and requires re-login |
| Logout | Revokes the session family and clears the cookie |
| Deactivation / role change | All sessions for the user are revoked; access tokens expire within 15 minutes and the API re-checks membership on each request where it matters |

Access tokens are **never** stored in `localStorage`, `sessionStorage`, IndexedDB, URLs,
or analytics.

### 2.4 Password reset

Not designed for Phase 1 (DR-011). The intended flow is a single-use, 30-minute,
hashed reset token delivered by the chosen channel; the token is invalidated on use and
on password change. Until a channel is agreed, a super admin can issue a reset link
manually — recorded in the audit log.

### 2.5 Human authentication endpoints and throttling

- `POST /auth/login` — 5 failures per 15 minutes per account+IP pair, then `429` with
  `Retry-After`; progressive delay.
- `POST /auth/refresh` — 60/minute per session.
- All auth responses are `Cache-Control: no-store`.

---

## 3. Device authentication

### 3.1 Credential model

| Element | Design |
| --- | --- |
| Identity | `devices.id` + `devices.device_uid`; never a human `users` row |
| Credential | Per-device `client_id` (public, `dev_` + random) and a 32-byte random secret, returned once at issuance/rotation |
| Storage | `device_credentials.secret_hash` — Argon2id; plaintext is never persisted or logged |
| Rotation | New version inserted, previous revoked in one transaction; optional short overlap decided by policy |
| Revocation | `revoked_at` set; outstanding device tokens remain valid only until their 15-minute expiry, and the token endpoint rejects the credential immediately |
| Uniqueness | Partial unique index guarantees one active credential per device; no global/shared API key exists |

### 3.2 Token issuance

`POST /api/v1/device-auth/token` with `client_credentials`. Checks, in order: credential
exists → secret verifies → not revoked/expired → device `active` → active department
assignment. All failures return `401 invalid_client` with no differentiation. Tokens are
JWT access tokens with `typ=device`, `device_id`, `scope=device:scan`, `jti`, and a
15-minute TTL. Device tokens are valid only on `/api/v1/device*` routes.

### 3.3 Device lifecycle controls

- **Enrollment:** Super Admin registers the device, assigns a department, and issues the
  initial credential through a protected channel (operator hand-off). No universal
  embedded key.
- **Suspension/retirement:** blocks token issuance and ingestion instantly; the device is
  treated as disconnected.
- **Reassignment:** only Super Admin; closes the assignment, opens a new one, audits both
  departments, and never rewrites historical scans.
- **Compromise:** revoke credential, rotate, optionally suspend; audit and review scans
  submitted during the exposure window.
- **Last seen / last error:** operational visibility for stale or failing devices without
  exposing secrets.

### 3.4 Abuse protections

- Token endpoint: 10/minute per `client_id`, 60/minute per IP.
- Scan submission: 30/minute per device; finalize 60/minute per device.
- Payload size cap enforced before JSON parsing (default 1 MiB, provisional).
- Repeated `409` conflicts are counted per device and alerted after a threshold.
- Failed credential attempts are audit-logged with device/client ID and source IP.

---

## 4. Authorization

### 4.1 Role matrix

| Capability | Super Admin | Department Admin | Department User | Device |
| --- | --- | --- | --- | --- |
| Department management | All | — | — | — |
| Device register / reassign / suspend | All | View own department | — | — |
| Device credentials issue/rotate/revoke | All | — | — | — |
| User management | All | Own department (pending DR-019) | — | — |
| Latest scan / history / detail | All (explicit department) | Own department | Own department | Own submission status |
| Quality / age analytics | All | Own department | Own department | — |
| Batch comparison | All | Own department | Own department | — |
| Reports / images | All (audited) | Own department | Own department | — |
| Notifications | Own inbox | Own inbox | Own inbox | — |
| Audit logs | All | — | — | — |
| Submit scans | — | — | — | Own scans only |

### 4.2 Enforcement points

1. **Authentication dependency** resolves a `Principal` (`user` or `device`) from the
   token and rejects the wrong plane (`403`).
2. **Membership resolution** loads active memberships from the database on every request
   (a 15-minute token is not trusted for membership changes beyond that).
3. **Service-layer scope**: every department-scoped function receives the principal and
   adds `department_id = :caller_department` (or validates an explicit super-admin
   selection). Repositories never accept an unscoped "list all" call from an API path.
4. **Object-level checks**: `scan.department_id`, `batch.department_id`,
   `notification.department_id` are compared to the resolved scope before returning data
   or issuing a file URL.
5. **File access**: authorization precedes URL signing; there is no public bucket and no
   direct object path in any response.
6. **Super admin**: cross-department access requires an explicit `department_id`, is
   audited with actor/target/reason, and cannot be performed by a device token.

### 4.3 Historical department ownership

- `scans.department_id` is written once from `device_assignments` at acceptance and has
  no update path in application code.
- Reads never join to the device's current assignment to determine visibility.
- Reassignment only closes/opens `device_assignments` rows.
- Analytics for a department therefore remain stable across reassignment; the new
  department sees only scans accepted after the change.

### 4.4 Anti-enumeration

- Out-of-scope IDs return `404` where existence would leak (scan, report, batch).
- Notifications addressed to another user return `404`.
- Counts and totals are computed after scoping, so pagination metadata cannot reveal
  another department's volume.
- Login and device token errors are generic.

---

## 5. File security

| Control | Design |
| --- | --- |
| Private storage | Bucket/directory has no public read; no static serving of the storage root |
| Access | API-authorized, then short-lived signed URL (default 300 s) or authenticated stream |
| Key construction | Server-generated UUID + role + extension; client filenames never influence keys |
| MIME validation | Declared type checked against a role allowlist, then magic bytes verified |
| Size limits | Per-role configurable limits; provisional dev values (PDF 25 MiB, image 15 MiB) |
| Integrity | SHA-256 declared at prepare, verified on finalize, stored on `scan_files` |
| Filename handling | Sanitised for display only; path separators, control characters and leading dots stripped; ≤ 200 chars |
| Content headers | `Content-Disposition` with a safe ASCII filename, `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store` |
| Malware | External scanning hook is **not** implemented; decision pending (DR-006). PDFs are never rendered in the portal's origin without sandboxing |
| Retention | Objects follow the retention decision; incomplete uploads expire |
| Super-admin downloads | Audited with scan, file, actor and reason |

Rendering rule: PDFs and images are served from a separate origin or through a
short-lived URL. The portal must not embed user-supplied HTML/SVG in the application
origin.

---

## 6. Transport, headers and browser protections

- HTTPS everywhere; HSTS (`max-age=31536000; includeSubDomains`) at the edge in
  production. HTTP redirects to HTTPS.
- Security headers on API and static responses:
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Permissions-Policy: geolocation=(), camera=(), microphone=()`,
  and a CSP for the frontend:
  `default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`.
- **CORS:** explicit allowlist from `CORS_ORIGINS`; no `*` with credentials; only
  `GET, POST, PATCH, PUT, DELETE, OPTIONS`; `Authorization` allowed; preflight cached
  600 s.
- **CSRF:** the access token is a bearer header (not a cookie), so state-changing API
  calls are not CSRF-susceptible. The refresh cookie is `SameSite=Strict` and only used
  on `/auth/refresh`; that endpoint additionally requires a custom header
  (`X-Requested-With: XMLHttpRequest`) that cross-site forms cannot set.
- **Clickjacking:** `frame-ancestors 'none'` + `X-Frame-Options: DENY`.
- **XSS:** React escaping by default; no `dangerouslySetInnerHTML` with device data;
  device-supplied labels rendered as text; CSP as above.
- **Open redirect:** the post-login return path is restricted to same-origin relative
  paths.

---

## 7. Input validation and injection defence

- Pydantic v2 models for every endpoint; JSON Schema for device payloads; unknown fields
  rejected at the top level.
- SQLAlchemy parameter binding only; no string-interpolated SQL. Raw SQL, if ever needed,
  uses bound parameters and is reviewed.
- Numbers are bounded (`0..100` for percentages, non-negative dimensions, month caps),
  strings length-capped, enums closed, timestamps sanity-checked.
- Reject unexpected content types; body size limits enforced before parsing.
- Pagination bounds and sort-field allowlists prevent expensive/unsafe queries.
- Uploaded archives are not accepted; SVG is not accepted for scan images.
- JSONB payloads are stored, not executed; keys derived from them are validated against
  an allowlist where used in responses.

---

## 8. Secrets management

| Secret | Development | Production |
| --- | --- | --- |
| `APP_SECRET_KEY` | Generated placeholder in `.env` | Secret manager / platform secrets, ≥ 32 bytes, rotated |
| `DATABASE_URL` | Local Postgres container | Managed secret, least-privilege DB role |
| S3 credentials | Not used (local adapter) | Instance role / scoped access key; no bucket-wide admin |
| Device secrets | Seeded by simulator | Generated per device, delivered once, never logged |
| Session/refresh tokens | Runtime only | Runtime only |

Rules: `.env` is git-ignored; only `.env.example` with placeholders is tracked.
Production startup **fails** if `APP_SECRET_KEY` is missing or equals the development
placeholder. Secrets are never written to logs, error responses, audit metadata or
frontend bundles. Docker images contain no secrets.

Database roles: the application uses a role with DML on business tables and
`INSERT/SELECT` only on `audit_logs`; migrations use a separate owner role.

---

## 9. Audit logging

Append-only `audit_logs` (see `docs/database/DATABASE_SCHEMA.md`). Recorded: actor type
and ID, action, target, department scope, timestamp, IP, user agent, request ID,
structured metadata (before/after where safe).

Audited events:

- Login success/failure, logout, refresh reuse detection, password change.
- User create/update/deactivate, membership create/change/deactivate.
- Department create/update/deactivate.
- Device register/suspend/retire, credential issue/rotate/revoke.
- Device reassignment (old and new department).
- Super-admin cross-department scan/report access.
- Report or image download.
- Any future verdict correction or report replacement.

Not recorded: passwords, tokens, device secrets, file bytes, full raw payloads.

Retention ≥ 24 months, pending DR-013; the app role cannot update or delete rows.

---

## 10. Rate limiting and abuse control

Baseline (per instance; a shared store such as Redis is introduced only if multi-instance
enforcement is required):

| Surface | Limit |
| --- | --- |
| `POST /auth/login` | 5 / 15 min per account+IP |
| `POST /device-auth/token` | 10 / min per client, 60 / min per IP |
| `POST /device/scans` | 30 / min per device |
| Attachments prepare/upload | 60 / min per device |
| Portal reads | 120 / min per user |
| Analytics/compare | 30 / min per user |
| Report downloads | 30 / min per user |

`429` responses include `Retry-After`. Repeated authentication failures and conflict
storms are alerted. Limits are configuration values, not constants.

---

## 11. Error handling and observability

- One error envelope with a safe message, machine code and `request_id`.
- No stack traces, SQL, file paths, storage keys, dependency versions or internal host
  names in responses.
- `422` field errors list field names and constraints but not raw input values.
- Logs are structured (JSON in production) with request ID, principal type (never token
  values), route, status and latency.
- Health endpoints expose liveness and readiness only; no version/dependency detail to
  unauthenticated callers in production.

---

## 12. Dependency and supply-chain security

- Locked, pinned dependency versions (`requirements.txt`, `package-lock.json`).
- CI runs dependency audit (`pip-audit`, `npm audit --omit=dev`) and fails on known
  high-severity issues in production dependencies.
- Dependabot (or equivalent) for weekly patch updates; review required before merge.
- Container images use slim base images, run as non-root, and are rebuilt on base-image
  updates.
- No unpinned CDN scripts; the frontend bundle is built and served from our origin.

---

## 13. Threat model

Assumption: authenticated departmental insiders, internet-reachable backend, physically
accessible kiosk devices, and an operator model without a dedicated 24×7 SOC.

| # | Threat | Vector | Impact | Mitigation | Residual |
| --- | --- | --- | --- | --- | --- |
| T1 | Cross-department data access (IDOR) | Guessing scan/report/batch IDs via API | Disclosure of another department's results and reports | Server-side scope on every query; `404` on out-of-scope; opaque UUIDs; audit of super-admin access; isolation tests in CI | Low |
| T2 | Department spoofing in ingestion | Sending `department_id` or another `device_id` in payload | Scans attributed to the wrong department | Department resolved from authenticated device's active assignment; payload device must match token; payload department ignored; rejected with 403 | Low |
| T3 | Historical data migration on reassignment | Reassign then read old scans | New department sees previous department's history | Immutable `scans.department_id` snapshot; reads never use live assignment; explicit reassignment test | Low |
| T4 | Stolen device secret | Extract credential from kiosk | Forged scan submissions until detected | Per-device Argon2id-hashed secret, no shared key, short tokens, rotation/revocation, rate limits, conflict/stale-device alerts, audit trail | Medium (physical access cannot be fully prevented) |
| T5 | Replay / duplicate submission | Network retry or malicious replay | Duplicate scans, duplicated alerts, distorted analytics | `(device_id, client_scan_id)` unique; payload hash; 409 on conflict; unique `notifications.event_key` | Low |
| T6 | Malicious upload | PDF/image with malware, polyglot, oversized file | Operator workstation compromise, storage abuse | MIME allowlist + magic bytes, size caps, SHA-256, sanitised names, private storage, `nosniff`, separate-origin serving, no SVG | Medium until malware scanning is decided |
| T7 | Path traversal via filename | `../../` in attachment name | Write outside storage prefix | Server-generated keys; filenames sanitised and used only for display | Low |
| T8 | Public report URL leakage | Copied presigned URL shared externally | Report disclosure | 5-minute signed URLs, authenticated issuance, no public bucket, audit of issuance | Medium (a shared link works until expiry) |
| T9 | Credential stuffing / brute force | Automated login attempts | Account takeover | Argon2id, generic errors, progressive delays, per-account+IP throttling, stub for MFA later | Medium |
| T10 | Session theft / XSS | Token exfiltration | Impersonation | Access token in memory only, HttpOnly refresh cookie, CSP, React escaping, short TTL, refresh rotation with reuse detection | Low-Medium |
| T11 | CSRF on refresh | Cross-site request to `/auth/refresh` | Session fixation / data theft | `SameSite=Strict`, custom header requirement, no state change in refresh beyond rotation | Low |
| T12 | Super-admin abuse | Legitimate privileged account reads all departments | Broad disclosure | Explicit department selection, mandatory audit, least-privilege grants, review of audit log; MFA recommended later | Medium |
| T13 | Verdict manipulation | Editing submitted status/threshold | Misleading quality claims | Scans and raw payloads immutable; corrections are new records; audit; UI shows source ruleset | Low |
| T14 | SQL injection | Crafted filters or payloads | Data breach | ORM/bound parameters, enum and sort allowlists, validation | Low |
| T15 | DoS via ingestion | Flood of scans/large payloads | Service unavailability | Per-device rate limits, body size caps, DB indexes, readiness checks, alerting | Medium (no WAF assumed) |
| T16 | Audit log tampering | Insider with DB access | Loss of accountability | Append-only grants, no app update/delete path, off-host log shipping recommended | Medium |
| T17 | Backup exposure | Unencrypted dump or bucket | Full data disclosure | Encrypted backups, restricted access, restore drills, no production data in dev | Medium until DR-014/015 confirmed |
| T18 | Misleading certification claim | UI wording implying statutory grade | Legal/procurement harm | Advisory labels mandatory in data and UI; original PDF preserved; no portal-generated certificate | Low |
| T19 | Stale data presented as current | Disconnected device | Wrong operational decision | Last-sync timestamps, stale indicators, processing states distinct from verdicts | Low |
| T20 | Insider mass export | Repeated authorized downloads | Data exfiltration | Rate limits, download audit, retention review; DLP out of scope | Medium |

---

## 14. Security testing plan (implemented progressively)

| Area | Test |
| --- | --- |
| AuthN | Valid/invalid login, inactive user, throttling, refresh rotation, reuse detection, logout revocation |
| Device AuthN | Valid credential, revoked/expired credential, suspended device, unassigned device, human token on device route and vice versa |
| AuthZ | Role matrix per endpoint; Department Admin confined to own department; super admin requires explicit department and is audited |
| Isolation | Department A cannot read B's scan, report, image, analytics, comparison or notification; totals do not leak |
| Idempotency | Identical replay → 200, no duplicate rows/notifications/files; conflicting replay → 409 |
| Uploads | Type/size/checksum failures; path traversal filename; duplicate role; incomplete finalize |
| Files | Unauthorized download blocked; expired URL rejected; audit entry written |
| Data rules | Nullable age survives round-trip; `0` never substituted; bases never blended in analytics; latest endpoint excludes non-completed scans |
| Schema | Device payload schema rejects unknown fields, bad bases, invalid ranges |

Phase 1 implements the foundation tests (health, configuration guardrails, error
envelope, security headers). The remainder are required as their features land.

---

## 15. Incident response (baseline)

1. **Detection:** auth-failure spikes, conflict storms, stale devices, 5xx rate, audit
   anomalies.
2. **Containment:** revoke device credentials / suspend device; revoke user sessions;
   disable account; block source at the edge.
3. **Eradication:** rotate affected secrets, patch the defect, review uploaded files.
4. **Recovery:** restore from encrypted backup if integrity is in doubt; verify hash
   manifests.
5. **Review:** timeline from `audit_logs` + request IDs; record follow-up actions.

Ownership, on-call and breach-notification obligations are pending DR-016…DR-018 (scale,
deployment, operations owner).

---

## 16. Open security decisions

| Decision | Impact |
| --- | --- |
| DR-010 deployment model | Determines secret manager, TLS termination, backup and log shipping |
| DR-011 authentication implementation (MFA, SSO, password reset channel) | Token model is compatible with adding MFA; SSO would replace password login |
| DR-012 notification provider | Email introduces a new data flow and PII handling surface |
| DR-013/014/015 retention, backup, RTO/RPO | Drives encrypted backup, purge jobs and audit retention |
| DR-006 file allowlist / malware scanning | Upload security posture |
| DR-019 Department Admin permissions | Authorization matrix for user management |
| Multi-instance rate limiting | Whether a shared limiter store is required |
