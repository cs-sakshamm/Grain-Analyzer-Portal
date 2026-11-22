# Testing Strategy — Rice Age Portal

**Status:** strategy for the whole project, with the Phase 1 foundation implemented.
Sections marked *planned* describe tests that must be written with the corresponding
feature — they are not claimed as passing.

---

## 1. Principles

1. **Test behaviour, not implementation.** A test must fail if the business rule
   regresses. No assertion-free, tautological, or snapshot-only tests.
2. **Security rules are test requirements.** Department isolation, role authorization,
   device/human separation, idempotency and file access are tested as first-class
   behaviour, not left to manual checks.
3. **No invented fixtures as truth.** Fixtures derive from the supplied artifacts
   (Sample-0038) and the published JSON Schema, never from values invented to make a
   test pass.
4. **Deterministic and offline.** No live device, no external network, no shared
   production database. Time is injected or frozen where behaviour depends on it.
5. **Every fixed bug gets a regression test** in the same change.
6. **Coverage targets apply to high-risk modules**, not to a vanity global percentage.

---

## 2. Test layers

| Layer | Tool | Scope | Where |
| --- | --- | --- | --- |
| Unit | Pytest | Services, scope predicates, state machine, validators, formatters | `backend/tests/unit/` |
| API integration | Pytest + FastAPI TestClient | Route contracts, status codes, error envelope, auth dependencies | `backend/tests/api/` |
| Database integration | Pytest + PostgreSQL | Constraints, partial unique indexes, transactions, migrations | `backend/tests/db/` |
| Contract | Pytest + `jsonschema` | Device payload schema acceptance/rejection | `backend/tests/contract/` |
| Frontend logic | Vitest | Formatting, basis labels, guards, comparability rules | `frontend/src/**/*.test.ts` |
| Frontend components | Vitest + Testing Library | Loading/empty/error/unavailable states, verdict labelling | `frontend/src/**/*.test.tsx` |
| End-to-end | Playwright | Login, latest scan, download authorization, isolation | `frontend/e2e/` |
| Performance | k6 or Locust | Ingestion and dashboard reads at agreed volume | `tests/perf/` (only after DR-018) |

Phase 1 establishes Pytest, Vitest, the JSON Schema check and CI. The remaining
directories are created when their first tests land, not as empty placeholders.

---

## 3. Test environments

| Environment | Database | Storage | Purpose |
| --- | --- | --- | --- |
| Unit | none / in-memory | in-memory adapter | Fast logic tests, no I/O |
| API | PostgreSQL service container | in-memory or temp-dir adapter | Real constraints and transactions |
| Local dev | Compose PostgreSQL | local filesystem | Manual verification |
| CI | PostgreSQL service | temp-dir adapter | Gate on every push/PR |

Rules:

- Database tests run against **PostgreSQL**, not SQLite, because the schema depends on
  partial unique indexes, `citext`, `jsonb`, `inet` and enum types that SQLite cannot
  reproduce.
- Each test runs in a transaction that is rolled back, or against a schema created and
  dropped per session. Tests never depend on execution order.
- Upload tests use a fake `StoragePort` that records keys and can simulate failures; the
  S3 adapter is exercised only in a dedicated integration job once configured.

---

## 4. Required suites by feature

### 4.1 Authentication (human)

- Valid login issues an access token and a refresh cookie; response contains memberships.
- Unknown email and wrong password return the same `401` body (no account enumeration).
- Inactive user is rejected; deactivation revokes existing sessions.
- Refresh rotates the token; replaying the old token revokes the family.
- Logout revokes the session and clears the cookie.
- Access token expiry yields `401` without leaking data; a protected route is never
  served with a stale principal.

### 4.2 Device authentication

- Valid client credentials issue a device token scoped to `device:scan`.
- Revoked/expired credential, suspended device and unassigned device are rejected with
  identical `401/403` behaviour and no detail leakage.
- A human token on a device route (and vice versa) is rejected.
- Rotating a credential invalidates the previous one immediately at the token endpoint.
- Repeated failures are throttled.

### 4.3 Role authorization

Matrix tests assert every endpoint against each role:

| Check | Expected |
| --- | --- |
| Department User hits admin route | `403` |
| Department Admin hits department CRUD | `403` |
| Department Admin manages own-department user | allowed (per DR-019 interim policy) |
| Department Admin manages another department's user | `403`/`404` |
| Super Admin reads without `department_id` | `400 department_required` |
| Super Admin cross-department read | `200` + audit row |
| Device token on portal route | `403` |

### 4.4 Department isolation (mandatory, highest priority)

Pattern: seed Department A and B, plus one user per department and one device each.

1. User A requests B's scan by ID → `404`, response body contains no B identifiers.
2. User A requests B's report/image URL → `404`/`403`, no signed URL issued.
3. `GET /scans` for A never includes B rows; `total` equals A's visible count.
4. Analytics and batch comparison for A never include B scans; comparing a B batch ID
   returns `404`.
5. Notification feed for A never includes B events; marking a B notification read → `404`.
6. Reassigning a device from A to B: pre-existing scans remain visible to A and invisible
   to B; new scans are visible to B and invisible to A.
7. File storage key for A cannot be fetched through the API by B even when guessed.

### 4.5 Scan lifecycle and latest scan

- `POST /device/scans` creates `received`/`awaiting_files`, never `completed`.
- The latest endpoint returns `204` before completion and only the newest completed scan
  after; a newer in-flight scan does not displace the previous completed result.
- Illegal transitions are rejected; finalize on `completed` is idempotent.
- Failure paths set `failed` with a diagnostic code and never set a quality verdict.

### 4.6 Idempotency

- Identical replay returns `200` with the same `scan_id`, creates no second scan row, no
  additional `scan_files`, and no duplicate notifications.
- Conflicting replay (same key, different payload hash) returns `409` and leaves the
  original unchanged.
- Retry of a failed scan behaves as documented (no silent overwrite).
- Concurrent identical submissions yield exactly one scan (transactional uniqueness test).

### 4.7 Attachments and storage

- Prepare rejects oversize, disallowed type, missing checksum, already-verified role.
- Upload with a mismatched SHA-256 is rejected and the object is not recorded as verified.
- Magic-byte mismatch (declared PDF, PNG bytes) is rejected.
- Filename traversal (`../../etc/passwd`) never influences the storage key.
- Finalize with a missing required role returns `409 missing_attachments` with the roles.
- Incomplete uploads expire and the scan moves to `failed`.
- A fake repository failure mid-upload leaves no verified `scan_files` row.

### 4.8 Measurement and age data rules

- A measurement round-trips with its basis; count and estimated-mass rows for the same
  metric coexist.
- Analytics never average across bases and always report `n`.
- A scan with no age result returns `age: null` and renders "Not available".
- Age `0` is preserved as a real value; absence is distinct from zero.
- Mixed `model_version`/`method` age results are excluded from a trend and reported as a
  warning.
- Batch comparison returns `ranking: null` and comparability warnings for mixed bases.

### 4.9 Reports

- Authorised user receives the exact stored bytes (SHA-256 match) with an attachment
  disposition.
- Unauthorised or cross-department request is blocked before URL issuance.
- Expired signed URL is rejected.
- Audit row created for every issuance, including super-admin cross-department reads.

### 4.10 Contract tests

- Valid payloads (Sample-0038 shape, minimal shape, null age) validate.
- Unknown top-level fields, including `department_id`, are rejected.
- Unit/basis mismatches (percent basis with gram unit) are rejected.
- Age range inversion is rejected by the service layer (JSON Schema cannot express
  numeric ordering) and asserted explicitly.

### 4.11 Frontend

- Pure logic: basis labels, "Not available" for missing age, zero preservation, age
  range/scalar formatting, comparability predicate (implemented).
- Components (planned): loading/empty/error/stale states, verdict vs processing badge
  distinction, unavailable image fallback, keyboard operability of filters.
- Contract: Zod parse rejects malformed API payloads instead of rendering garbage.
- E2E (planned): login → latest scan; direct URL for another department blocked;
  report download; session expiry re-authentication.

---

## 5. Acceptance-scenario traceability

| Scenario (SOR §10) | Automated test suite |
| --- | --- |
| AT-01 register and activate device | 4.2, 4.3 |
| AT-02 JSON + PDF + images complete | 4.5, 4.7 |
| AT-03 replay same client scan ID | 4.6 |
| AT-04 conflicting retry | 4.6 |
| AT-05 another department's scan URL | 4.4 |
| AT-06 reassign device | 4.4 (isolation step 6) |
| AT-07 latest scan after completion | 4.5 |
| AT-08 no age result supplied | 4.8, 4.11 |
| AT-09 compare batches with different bases | 4.8, 4.4 |
| AT-10 flagged result notification, no duplicates | 4.6, 4.8 |
| AT-11 original PDF download authorization | 4.9 |
| AT-12 disconnect during image upload | 4.7 |

---

## 6. Test data

- Device payload fixtures live in `backend/tests/fixtures/` and derive from the published
  schema and the Sample-0038 certificate values. A fixture is never edited to make a
  failing rule pass — the rule is fixed or the decision is recorded.
- Two departments, two devices, two users and one super admin are seeded per isolation
  test, with distinct codes (`DEPT-A`, `DEPT-B`) and opaque IDs.
- No real personal data, no production credentials, no production uploads.
- Time is frozen for tests that assert expiry, stale indicators or retention.
- Generated secrets in tests are obviously fake and never resemble production formats.

---

## 7. Coverage expectations

| Area | Target |
| --- | --- |
| Department scope and authorization services | 100 % branch of decision points |
| Idempotency and scan state machine | Every documented transition and conflict path |
| Attachment verification | Every rejection reason |
| Age and measurement rules | Every nullable/zero/basis case |
| Otherwise | Line coverage ≥ 80 % on changed modules |

Coverage is reported but is not a substitute for the scenario tests above; a high
percentage with missing isolation tests is a failing result.

---

## 8. CI gates

Every push and pull request runs (see `.github/workflows/ci.yml`):

1. `ruff check` and `ruff format --check` (backend).
2. `pytest` (backend).
3. `eslint`, `tsc --noEmit`, `vitest run`, `vite build` (frontend).
4. JSON Schema meta-validation.

Once domain models land: add a PostgreSQL service and run `pytest` against it; once auth
ships: add the isolation suite as a required check (blocking merge); once endpoints
exist: validate generated OpenAPI against the documented contract.

---

## 9. Phase 1 implemented tests

| Suite | Tests | Result |
| --- | --- | --- |
| `backend/tests/test_health.py` | 4 | Pass — liveness, production detail withholding, readiness `SELECT 1`, readiness `503` without leaking the driver error |
| `backend/tests/test_http_behaviour.py` | 5 | Pass — error envelope, request-ID echo/generate/cap, security headers, CORS allowlist |
| `backend/tests/test_config.py` | 13 | Pass — CORS normalisation, production secret/storage/debug guards, TTL and log-level validation |
| `frontend/src/lib/format.test.ts` | 10 | Pass — basis labels, no zero substitution, real zero preserved, age category/range/scalar |
| **Total** | **32** | **Passing locally** |

Non-test checks performed: backend Ruff lint and format, frontend ESLint, TypeScript
`--noEmit`, Vite production build, JSON Schema meta-validation with acceptance and
rejection cases, and `docker compose config` syntax validation.

---

## 10. Known gaps in Phase 1

- No domain models, so no database constraint tests yet.
- No authentication implementation, so auth/role/isolation suites are specified but not
  written.
- No device ingestion endpoint, so idempotency and attachment flows are contract-tested
  only through the schema.
- Docker runtime was not exercised (daemon unavailable in the authoring environment);
  Compose syntax was validated.
- No E2E harness until the first real screen exists.

---

## 11. Phase 2 status

Implemented locally and in CI:

| Suite | What it covers |
| --- | --- |
| `tests/test_health.py`, `test_http_behaviour.py`, `test_config.py` | 22 foundation tests (unchanged) |
| `tests/integration/test_schema_constraints.py` | Case-insensitive email uniqueness, one active assignment/credential, duplicate `client_scan_id`, completed-scan timestamp rule, measurement basis coexistence and unit rules, age information/range/zero, notification key uniqueness, batch uniqueness |
| `tests/integration/test_auth_admin.py` | Login and cookie flags, generic failures, inactive accounts, refresh rotation and reuse revocation, logout, `me`, role denials, own-department limits, department creation, device lifecycle, reassignment history, token-plane separation, suspended devices, audit rows |
| `tests/integration/test_ingestion.py` | Assignment-derived ownership, measurement-basis and age persistence, identical replay, conflicting replay, spoofed department rejection, unassigned device rejection, finalize prerequisites and idempotency, checksum rejection, latest-completed semantics, cross-department scan/report denial, null age, historical ownership |
| `frontend/src/**/*.test.ts` | 15 tests: measurement/age formatting and auth guards |

Integration suites are skipped when `RICE_AGE_TEST_DATABASE_URL` is absent; CI sets it
and also runs `alembic upgrade head`, `downgrade base`, `upgrade head` before pytest.
