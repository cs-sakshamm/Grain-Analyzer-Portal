# Development Setup — Rice Age Portal

Reproducible local environment for the Phase 1 foundation. Verified on Windows with
Git Bash and Python 3.14 / Node 24; CI uses Python 3.12 and Node 22.

---

## 1. Prerequisites

| Tool | Minimum | Notes |
| --- | --- | --- |
| Python | 3.12 | 3.12–3.14 verified; CI pins 3.12 |
| Node.js | 22 | npm 10+ |
| PostgreSQL | 16 | Only needed outside Docker (Compose provides 17-alpine) |
| Docker Desktop | current | Optional; the backend and frontend also run natively |
| Git | current | HTTPS credentials required to push to `origin` |

Disk: ~1 GB for dependencies and Docker images.

---

## 2. Repository layout

```text
backend/    FastAPI service, migrations, tests
frontend/   React + Vite portal shell
docs/       architecture, database, api, security, development, decisions
.github/    CI workflow
docker-compose.yml
.env.example
```

---

## 3. Environment file

```bash
cp .env.example .env
```

Then edit `.env` for local values. `.env` is git-ignored. `.env.example` contains only
placeholders.

Notes:

- `APP_SECRET_KEY` may keep the development placeholder **outside production**. In
  production the application refuses to start with it.
- `DATABASE_URL` is used by the backend when run natively. Compose overrides it to point
  at the `db` service.
- Upload limits in `.env.example` are **provisional** (DR-005) and are not business
  rules.
- `STORAGE_BACKEND=local` writes files under `STORAGE_LOCAL_ROOT` (`./storage`,
  git-ignored). Production must use `s3`.

---

## 4. Option A — Docker Compose (recommended)

```bash
docker compose up --build
```

| Service | URL |
| --- | --- |
| Frontend (Vite) | http://localhost:5173 |
| Backend API | http://localhost:8000/api/v1/health |
| Readiness (DB check) | http://localhost:8000/api/v1/health/ready |
| PostgreSQL | `localhost:5432` (credentials from `.env`) |

The backend container waits for the database health check, then starts Uvicorn with
`--reload` against the bind-mounted source.

Stop and remove volumes (destroys local data):

```bash
docker compose down -v
```

If Docker Desktop is not running, the CLI reports a missing engine pipe
(`dockerDesktopLinuxEngine`) — start Docker Desktop and retry. Compose configuration can
still be validated without the engine:

```bash
docker compose config --quiet
```

---

## 5. Option B — native processes

### 5.1 Database

Start PostgreSQL locally (or only the database from Compose):

```bash
docker compose up -d db
```

Create the database if you are not using the Compose service:

```sql
CREATE DATABASE rice_age;
CREATE USER rice_age WITH PASSWORD 'replace-with-local-dev-password';
GRANT ALL PRIVILEGES ON DATABASE rice_age TO rice_age;
```

### 5.2 Backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash
# source .venv/bin/activate        # macOS / Linux

pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

Verify:

```bash
curl -s http://localhost:8000/api/v1/health
# {"status":"ok","service":"Rice Age Portal API","version":"0.1.0","environment":"development"}
curl -s http://localhost:8000/api/v1/health/ready
# {"status":"ready","database":"ok"}       (503 if PostgreSQL is unreachable)
```

Interactive docs: http://localhost:8000/docs (disabled in production).

### 5.3 Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server proxies `/api` to `VITE_PROXY_TARGET` (default
`http://localhost:8000`), so the shell can call the backend without CORS problems.

---

## 6. Database migrations

Alembic is configured; **Phase 1 intentionally ships no revisions** because the logical
schema is still subject to stakeholder decisions. The commands below are the workflow
once Phase 2 adds the first revision.

```bash
cd backend
alembic revision --autogenerate -m "create core identity tables"
alembic upgrade head
alembic current
alembic downgrade -1
```

`migrations/env.py` reads `DATABASE_URL` from application settings, so the database is
never configured in a committed secret. `alembic upgrade head` with no revisions is a
safe no-op today.

Rules: never edit an applied revision; adding a column requires a new revision plus an
update to `docs/database/DATABASE_SCHEMA.md`.

---

## 7. Checks and tests

Full project-wide strategy, including the required suites per feature and
acceptance-scenario traceability: [`docs/development/TESTING_STRATEGY.md`](TESTING_STRATEGY.md).

Run everything the way CI does:

```bash
# backend
cd backend
ruff format --check .
ruff check .
pytest

# frontend
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

Individual suites:

```bash
cd backend && pytest tests/test_health.py -v
cd frontend && npm test -- src/lib/format.test.ts
```

What the Phase 1 foundation tests actually cover:

| Test file | Behaviour verified |
| --- | --- |
| `backend/tests/test_health.py` | Liveness; readiness issues a real `SELECT 1`; readiness returns `503` when the dependency fails and does not leak the driver error; production withholds version/docs |
| `backend/tests/test_http_behaviour.py` | Error envelope, request-ID echo/generation/capping, security headers, CORS allowlist enforcement |
| `backend/tests/test_config.py` | CORS normalisation; production rejects placeholder/short secret, local storage and debug; TTL validation |
| `frontend/src/lib/format.test.ts` | Basis labels on percentages, no zero-substitution for missing values, genuine zero preserved, age category/range/scalar formatting |

Not yet covered (added with the features): authentication, role authorization,
department isolation, device auth, idempotency, uploads, report access.

---

## 8. Formatting and linting

```bash
cd backend && ruff format . && ruff check --fix .
cd frontend && npm run format && npm run lint
```

Backend: Ruff (lint + format, line length 100). Frontend: ESLint flat config with
TypeScript, React Hooks and React Refresh rules; Prettier for formatting.

---

## 9. Device payload schema validation

```bash
python - <<'PY'
import json, jsonschema
schema = json.load(open("docs/api/device-payload.schema.json", encoding="utf-8"))
jsonschema.Draft202012Validator.check_schema(schema)
print("schema ok")
PY
```

Requires `pip install jsonschema` (already in `backend/requirements-dev.txt`).

---

## 10. Common troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `dockerDesktopLinuxEngine` pipe not found | Docker Desktop stopped | Start Docker Desktop; retry `docker compose up` |
| `/health/ready` returns 503 | Database unreachable or wrong credentials | Check `docker compose ps`, `.env` password, and `DATABASE_URL` host (`db` inside Compose, `localhost` natively) |
| `ModuleNotFoundError: app` | Backend started outside `backend/` | `cd backend` or set `PYTHONPATH` to the backend directory |
| `psycopg` connection error | PostgreSQL not running | `docker compose up -d db` or start the local service |
| Frontend shows API “Unavailable” | Backend not running, or proxy target wrong | Start Uvicorn; confirm `VITE_PROXY_TARGET` |
| CORS error in the browser | Origin missing from `CORS_ORIGINS` | Add the exact origin (scheme + host + port) and restart the backend |
| `app_secret_key must be set` in production | Placeholder secret with `ENVIRONMENT=production` | Set a real ≥32-character secret; this guard is intentional |
| `storage_backend must be 's3'` in production | Local adapter with production environment | Configure S3 settings; local storage is development/test only |
| Port already in use | Another process on 5173/8000/5432 | Stop it or change the port mapping |
| npm install fails behind a proxy | Registry unreachable | Configure the npm proxy/registry and retry |

---

## 11. Reproducibility checklist for a new developer

1. `git clone` and `git checkout main`.
2. `cp .env.example .env` and set local values.
3. `docker compose up --build` **or** run the database, backend and frontend natively.
4. `curl http://localhost:8000/api/v1/health/ready` returns `{"status":"ready","database":"ok"}`.
5. `cd backend && pytest` passes.
6. `cd frontend && npm run lint && npm run typecheck && npm test && npm run build` passes.
7. Frontend at http://localhost:5173 shows both backend status pills as reachable.

---

## Phase 2 database and tests

Apply the schema and verify the cycle:

```bash
cd backend
export DATABASE_URL='postgresql+psycopg://rice_age:<password>@localhost:5432/rice_age'
alembic upgrade head
alembic downgrade base
alembic upgrade head
```

Integration tests require a **disposable PostgreSQL** database and are skipped without
one; they are never run against SQLite because partial unique indexes, native enums,
JSONB and INET are part of what is being verified:

```bash
export RICE_AGE_TEST_DATABASE_URL='postgresql+psycopg://rice_age:<password>@localhost:5432/rice_age_test'
pytest
```

The test fixture drops and recreates the schema for each test. Use a dedicated database
name; never point this variable at a database holding data you care about. CI starts a
`postgres:16` service, runs the migration up/down/up cycle, then the full suite.
