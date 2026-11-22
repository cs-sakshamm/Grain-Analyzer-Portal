# Rice Age — IoT Rice Quality & Age Analysis Portal

Secure, department-scoped web portal for Rice Age IoT rice-analysis devices. Devices
submit structured analysis results, the original analysis PDF, and primary/secondary
optical platen images. Departmental users review their latest **completed** scan,
historical records, quality analytics, any device-supplied rice-age output, batch
comparisons, and the original reports.

> **Status: portal API and departmental UI implemented; hardware and production
> infrastructure outstanding.**
> The backend exposes human authentication, department-scoped administration, device
> client-credentials, idempotent scan ingestion, verified private attachments, portal
> reads and analytics. The frontend ships all seven departmental modules behind
> authentication. Physical IoT integration, an admin console, malware scanning and
> production infrastructure are **not** built yet. See
> [`REMAINING_IMPLEMENTATION_GUIDE.md`](REMAINING_IMPLEMENTATION_GUIDE.md).

> **Advisory positioning.** Outputs from the supplied prototype device are
> experimental pre-inspection estimates. Optical percentages are not statutory
> procurement measurements, the portal is not a certification authority, and no
> statutory grade is implied. Rice age is displayed only when supplied by the device
> or its validated pipeline; the portal never infers age from images.

---

## 1. What the portal does

| Module | Responsibility |
| --- | --- |
| Latest Scan | Latest *completed* scan for the user's department, with platen evidence and report actions |
| Scan History | Department-scoped, filtered, paginated history of completed scans |
| Quality Analytics | Trends over compatible measurements, always labelled with measurement basis |
| Rice Age | Device-supplied age results only; nullable and provenance-preserving |
| Reports | Preview/download/print the original device-generated PDF |
| Batch Comparison | Side-by-side comparison within one department, with comparability warnings |
| Alerts & Notifications | In-portal, deduplicated notifications for completion, flags and failures |
| Administration | Departments, users, memberships, devices, assignments, credential rotation, audit |

Human roles: **Super Admin**, **Department Admin**, **Department User**.
Devices are a **separate machine identity** with no human-portal access.

Core invariants — these are enforced in the backend, not in the UI:

1. **Department isolation.** Every scan, report, image, analytics, comparison and
   notification response is scoped server-side to the caller's department.
2. **Device → department is server-resolved.** A department ID in an IoT payload is
   ignored. Ownership comes from the authenticated device's active assignment.
3. **Historical ownership.** Scans keep the department recorded at acceptance;
   reassigning a device never moves old scans.
4. **Latest scan = latest completed scan.** In-flight or failed submissions never
   replace it.
5. **Processing state ≠ quality verdict.** They are separate nullable dimensions.
6. **Measurement basis is preserved.** Count %, estimated-mass %, and physical mass
   are never blended or relabelled.
7. **Idempotency** on `(device_id, client_scan_id)`: identical replay is safe,
   conflicting replay returns `409`.

---

## 2. Technology stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, React Router, TanStack Query, Recharts, React Hook Form, Zod, Lucide icons (shadcn/ui adopted with the first real UI component) |
| Backend | Python, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, PostgreSQL |
| Storage | Local filesystem adapter in development; private S3-compatible object storage in production |
| Tooling | Docker / Docker Compose, Ruff, Pytest, ESLint, Prettier, Vitest, GitHub Actions |

Rationale, responsibilities, alternatives and trade-offs:
[`docs/architecture/SYSTEM_ARCHITECTURE.md`](docs/architecture/SYSTEM_ARCHITECTURE.md).

---

## 3. Repository layout```text
.
├── backend/                 FastAPI service: API, core config, db, security, storage, tests
├── frontend/                React + TypeScript portal shell and conventions
├── docs/
│   ├── architecture/        Repository audit, system architecture, frontend, storage
│   ├── database/            ER model and schema reference
│   ├── api/                 Device + portal API contracts, JSON Schema
│   ├── security/            Security architecture and threat model
│   ├── development/         Local setup, migrations, testing
│   └── decisions/           Open stakeholder decisions
├── postman/                 Postman collection, local environment, sample attachments,
│                            API guide and OpenAPI cross-check tooling
├── references, requirements and documents/   Source PRD, SOR, APSCSCL sample
├── .github/workflows/       CI
├── docker-compose.yml       Development stack (PostgreSQL + backend + frontend)
├── .env.example             Environment template — placeholders only
└── AGENTS.md                Engineering rules for future work
```

---

## 4. Quick start

```bash
cp .env.example .env          # then fill in local-only values
docker compose up --build     # PostgreSQL + backend + frontend

# backend
cd backend && python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
# http://localhost:8001/api/v1/health

# frontend
cd frontend && npm install && npm run dev
# http://localhost:5173
```

Full prerequisites, migration and test commands, and troubleshooting:
[`docs/development/DEVELOPMENT_SETUP.md`](docs/development/DEVELOPMENT_SETUP.md).

---

## 5. Documentation index

| Document | Purpose |
| --- | --- |
| [`docs/architecture/INITIAL_REPOSITORY_AUDIT.md`](docs/architecture/INITIAL_REPOSITORY_AUDIT.md) | Repository state at Phase 1 start, source-document findings, discrepancies |
| [`docs/architecture/SYSTEM_ARCHITECTURE.md`](docs/architecture/SYSTEM_ARCHITECTURE.md) | Stack decisions, components, data flows, environments, limitations |
| [`docs/architecture/FRONTEND_ARCHITECTURE.md`](docs/architecture/FRONTEND_ARCHITECTURE.md) | Routing, auth flow, role-aware UI, state, forms, charts, accessibility |
| [`docs/architecture/FILE_STORAGE_ARCHITECTURE.md`](docs/architecture/FILE_STORAGE_ARCHITECTURE.md) | Storage abstraction, keys, upload/download flows, retention |
| [`docs/database/ER_DIAGRAM.md`](docs/database/ER_DIAGRAM.md) | Mermaid ER model |
| [`docs/database/DATABASE_SCHEMA.md`](docs/database/DATABASE_SCHEMA.md) | Table-by-table schema, constraints, indexes, retention |
| [`docs/api/API_CONTRACT.md`](docs/api/API_CONTRACT.md) | Device and portal API contracts |
| [`docs/api/device-payload.schema.json`](docs/api/device-payload.schema.json) | Versioned JSON Schema for device scan submission |
| [`docs/security/SECURITY_ARCHITECTURE.md`](docs/security/SECURITY_ARCHITECTURE.md) | Auth models, authorization, file security, threat model |
| [`docs/development/DEVELOPMENT_SETUP.md`](docs/development/DEVELOPMENT_SETUP.md) | Reproducible local environment |
| [`docs/decisions/DECISION_REGISTER.md`](docs/decisions/DECISION_REGISTER.md) | Open stakeholder decisions and technical impact |
| [`postman/POSTMAN_API_GUIDE.md`](postman/POSTMAN_API_GUIDE.md) | Importing the Postman collection, authenticating as a human or a device, and testing every implemented API |

---

## 6. Conventions

- Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`).
- One logical unit per commit; push and verify each unit.
- Never commit secrets, `.env` files, real device credentials, or uploaded data.
- Server-side authorization on every data access — the UI is not an access boundary.
- Do not invent statutory thresholds, grading rules, age semantics, or device
  capabilities. Unresolved requirements go to the decision register.

Engineering rules: [`AGENTS.md`](AGENTS.md).

---

## Implementation status

**Working today (backend + frontend):** executable database schema and migration; human
authentication with rotating refresh sessions; department-scoped RBAC; department, user,
device, credential and assignment administration; device client-credentials; idempotent
scan ingestion; verified private attachments; finalize with deduplicated notifications;
latest scan, scan detail, report download, scan history, quality analytics, rice-age
analytics, report listing, batch comparison and notifications; a CLI device simulator.

The frontend serves the signed-in portal at `/` (Latest Scan) with Scan History, Quality
Analytics, Rice Age, Reports, Batch Comparison, Alerts & Notifications and a System
status page. `frontend/src/routes/config.tsx` is the single source of truth for routes.

**API handover:** import [`postman/Rice_Age_Portal.postman_collection.json`](postman/Rice_Age_Portal.postman_collection.json)
with [`postman/Rice_Age_Local.postman_environment.json`](postman/Rice_Age_Local.postman_environment.json)
and follow [`postman/POSTMAN_API_GUIDE.md`](postman/POSTMAN_API_GUIDE.md). It covers all
42 implemented operations, including the device ingestion lifecycle and the negative
cases (idempotent replay, conflicting replay, cross-department access).

**Not built yet:** physical hardware integration, admin console screens, password reset
by email, notification read state, audit read API, platen image delivery, malware
scanning and production infrastructure. See `REMAINING_IMPLEMENTATION_GUIDE.md`.
