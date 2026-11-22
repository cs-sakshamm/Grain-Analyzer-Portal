# AGENTS.md — Engineering Rules for Rice Age Portal

This file governs all automated and human work in this repository, for Phase 1 and
every later phase. Read it before changing anything. It is subordinate to the
supplied PRD, SOR and APSCSCL sample report; when they disagree with this file, the
source documents win and the disagreement goes into the decision register.

---

## 1. Project overview

Rice Age is an IoT rice quality and age analysis portal for departmental users.

- IoT devices perform optical rice analysis and submit structured JSON results, an
  original PDF report, and primary (bottom) / secondary (top) platen images.
- Department users view their latest **completed** scan, history, quality analytics,
  device-supplied rice-age output, batch comparisons, and original reports.
- Devices are assigned to exactly one department at a time; ownership is resolved by
  the backend from the authenticated device, never from the payload.
- Outputs are advisory. Nothing in this product certifies statutory rice quality.

Roles: `super_admin`, `department_admin`, `department_user`, plus the separate
non-human `device` machine identity.

---

## 2. Non-negotiable business rules

1. **Department isolation** — every read, write, download and aggregate is scoped
   server-side to the caller's department. Never rely on UI hiding.
2. **No payload-supplied department** — a `department_id` sent by a device is
   discarded; ownership comes from `device_assignments` at acceptance time.
3. **Historical ownership is immutable** — scans store the department snapshot taken
   when accepted. Reassignment never moves or exposes historical scans.
4. **Latest scan = latest completed** — never surface `received`, `awaiting_files`,
   `verifying` or `failed` as the latest result.
5. **Processing state and quality verdict are separate** — both nullable, never merged
   into one field.
6. **Age is device-supplied only** — nullable, `0` is never a substitute for missing,
   and the portal never infers age from images. Preserve unit, model version,
   confidence, method and validation status.
7. **Measurement basis is preserved** — count %, estimated-mass %, physical mass, and
   any other supplied basis stay distinct. Never combine incompatible bases in one
   metric, and never label an estimate as a measurement.
8. **Idempotency** — unique `(device_id, client_scan_id)`; identical replay is safe,
   conflicting replay returns `409`; no duplicate files, notifications or scans.
9. **Private files only** — store storage keys and hashes, never public URLs. Access
   is authorised per request and time-limited.
10. **No invented requirements** — do not create thresholds, grading rules, age
    semantics, file limits, or device capabilities that the sources do not state.

---

## 3. Architecture conventions

- Modular monorepo: `frontend/`, `backend/`, `docs/`, `infrastructure/`,
  `device-simulator/`.
- Backend layering: `api/` (HTTP) → `services/` (business rules) → `repositories/`
  (SQL) → `models/` (ORM). Keep HTTP concerns out of services and SQL out of routes.
- Department and role authorization lives in the service layer so every entry point
  (API, future workers) inherits it. Route-level dependency checks are additive.
- Frontend is feature-sliced: `src/features/<feature>/` owns its components, hooks,
  queries and types; `src/components/` holds only cross-feature primitives.
- Never put business rules (verdict logic, basis blending, age derivation) in the
  frontend.
- No new infrastructure (Redis, Celery, brokers, search clusters) without a
  demonstrated requirement recorded in the decision register.

## 4. Folder responsibilities

| Path | Responsibility |
| --- | --- |
| `backend/app/api/` | Routers, request/response wiring, dependencies |
| `backend/app/core/` | Settings, logging, security primitives, shared errors |
| `backend/app/models/` | SQLAlchemy ORM models |
| `backend/app/schemas/` | Pydantic request/response and payload schemas |
| `backend/app/services/` | Business rules, authorization, orchestration |
| `backend/app/repositories/` | Query/persistence layer |
| `backend/app/security/` | Human auth, device auth, password hashing, tokens |
| `backend/app/storage/` | Storage abstraction and adapters |
| `backend/app/workers/` | Background processing (only when introduced) |
| `backend/migrations/` | Alembic environment and revisions |
| `backend/tests/` | Pytest suites |
| `frontend/src/app/` | App composition, providers, router |
| `frontend/src/features/` | Feature modules (scan, history, analytics, age, reports, batches, notifications, admin) |
| `frontend/src/components/` | Shared UI primitives |
| `frontend/src/layouts/` | Role-aware shells |
| `frontend/src/services/` | Typed API client layer |
| `frontend/src/lib/` | Formatting, guards, utilities, design tokens |
| `docs/` | Architecture, database, API, security, development, decisions |
| `infrastructure/` | Docker and deployment assets |

Do not create empty directories or placeholder files to "fill" the structure.

## 5. Coding standards

**Backend (Python)**
- Python 3.12+; type hints everywhere; Pydantic v2 only.
- Ruff for lint and format; line length 100.
- SQLAlchemy 2.0 typed mappings; no raw string SQL with user input.
- Timestamps are timezone-aware UTC (`TIMESTAMPTZ` in PostgreSQL).
- Money/mass/percentage values use `Decimal`/`NUMERIC`, never binary floats in
  persistence.
- Enum values are stored as stable lowercase strings; never rename a stored value.

**Frontend (TypeScript)**
- Strict TypeScript; no `any` without a written justification.
- Function components and hooks only. TanStack Query for server state; no ad-hoc
  `fetch` in components.
- Zod schemas validate every external payload at the boundary.
- Tailwind utilities plus shared design tokens; no inline hex colours in components.
- Every data-driven view implements loading, empty, error and (where relevant)
  stale/unavailable states.

## 6. Security requirements

- Human auth: email + password (Argon2id), short-lived access token, rotating refresh
  session stored hashed server-side, logout revocation.
- Device auth: separate client-credentials flow, per-device secret, stored only as a
  hash, rotatable and revocable, never a shared key, never usable for human login.
- Authorize in the service layer on every access path, including file downloads.
- Signed URLs are short-lived and issued only after authorization.
- Validate uploads: declared type, magic bytes, size, and SHA-256; sanitise filenames;
  never trust client paths.
- Parameterised queries only; CORS allowlist from settings; safe error bodies (no
  stack traces, no internal identifiers beyond a correlation ID).
- Audit security-sensitive actions (assignment changes, credential rotation, user
  changes, super-admin cross-department access, verdict corrections).
- Never commit secrets. `.env` is ignored; only `.env.example` with placeholders is
  tracked.

## 7. Database conventions

- PostgreSQL; `UUID` primary keys generated by the application or `gen_random_uuid()`.
- Snake_case identifiers; plural table names; every table has `created_at`.
- Explicit foreign keys with deliberate `ON DELETE` behaviour; no orphan rows.
- Partial unique indexes for "at most one active row" rules (active assignment per
  device, active credential per device).
- Department-scoped tables carry `department_id` and are indexed for
  `(department_id, <sort key>)`.
- Schema changes require a new Alembic revision plus an update to
  `docs/database/DATABASE_SCHEMA.md`. Never edit an applied migration.
- Do not implement the physical schema before the corresponding design is documented
  and the open decisions it depends on are understood.

## 8. API conventions

- All routes under `/api/v1`; device routes under `/api/v1/device`.
- JSON in, JSON out; `snake_case` fields; RFC 3339 timestamps with offsets.
- Errors use one envelope: `{"error": {"code", "message", "details", "request_id"}}`.
- Status codes: 200/201 success, 202 accepted/processing, 400 malformed, 401
  unauthenticated, 403 unauthorized, 404 not found **or** not visible, 409 conflict,
  422 schema-invalid, 429 throttled, 5xx retryable system error.
- Cross-department access returns 403 or 404 with no data disclosure.
- Idempotency is mandatory on device scan submission and finalize.
- Update `docs/api/API_CONTRACT.md` and `docs/api/device-payload.schema.json` in the
  same change as any contract-affecting code.

## 9. Testing requirements

- Pytest for backend unit/integration tests; Vitest for frontend logic/components.
- Every changed behaviour gets a test that would fail without the change. No
  assertion-free or tautological tests.
- Required coverage areas as features land: department isolation, role authorization,
  device auth, idempotency and conflict replay, upload verification, report access,
  nullable age, measurement-basis separation.
- Tests must not depend on a live device, external network, or production services.
- Docker is optional for tests; the suite must run without it.

## 10. Git, commit and push policy

1. Inspect `git status`, current branch and remote before starting.
2. Work in small, logically complete units.
3. After each unit: format, lint, test, build where applicable, then inspect
   `git diff`.
4. Stage only intended files. Never stage `.env`, secrets, uploads, or local databases.
5. Conventional Commit messages describing the completed work.
6. Commit, push to the current branch, and **verify** the push. A local commit is not
   a push.
7. Never `git push --force`, `git push --force-with-lease`, or `git reset --hard`
   without explicit authorisation for a specific recovery.
8. If a push fails, keep the local commit, report the exact error, and give the retry
   command. Do not claim success.
9. Fetch before pushing when the branch may be behind; never overwrite others' work.

## 11. Documentation discipline

- Architecture, schema, contract or security changes require the matching document to
  be updated in the same change.
- Unresolved stakeholder questions go into `docs/decisions/DECISION_REGISTER.md` with
  an ID, impact, options and owner. A decision is only `Confirmed` when a stakeholder
  actually confirmed it — never on inference.
- Keep the advisory/prototype disclaimers intact in documentation and UI copy.
- Do not claim a capability is implemented because a document describes it.

## 12. Phase boundaries

Phase 1 delivers foundation, architecture, contracts, database design, security design,
development environment and tests. It does **not** deliver the seven module UIs,
production auth experience, admin console, live device integration, streaming, remote
control, image-based age inference, statutory grading, physical mass measurement,
government integration, public report access, or default cross-department sharing.
