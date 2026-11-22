# Next-developer implementation guide

## Current implementation

API routers: `backend/app/api/v1/endpoints/`; service authorization: `backend/app/services/`;
schema: `backend/migrations/versions/0001_initial_schema.py`; device contract:
`docs/api/device-payload.schema.json`; simulator: `device-simulator/simulator.py`; portal
pages: `frontend/src/pages/`.

## Remaining work

| Priority | Owner | Work | Acceptance |
|---|---|---|---|
| Critical | IoT developer | Map hardware to schema 1.0, submit, attach, finalize. | A completed scan is visible only to its assigned department. |
| Critical | DevOps | Provision PostgreSQL 16, private object storage, HTTPS, secrets, backup/restore and monitoring. | Production rejects development secret and local storage. |
| High | Stakeholder | Confirm payload, upload limits, attachment policy, thresholds and retention. | Resolve DR-001–DR-023; do not invent values. |
| High | Security | Add malware scanning and a distributed limiter before horizontal scale. | DR-026 is resolved with deployment architecture. |
| Medium | Frontend | Implement admin UX if approved. | Reuse `/api/v1/admin/*`; do not duplicate authorization. |

## Device protocol

Call `POST /api/v1/device-auth/token` with issued credentials, then send the token as
`Authorization: Bearer <token>`. Submit `POST /api/v1/device/scans`; prepare each file at
`POST /api/v1/device/scans/{scan_id}/attachments/prepare`, upload, then finalize at
`POST /api/v1/device/scans/{scan_id}/finalize`. Equal replay is safe; conflicting payload
replay returns `409`. Hardware fields absent from the schema are **pending confirmation**.
Introduce a new schema version; never repurpose historical fields.

## Verified commands

```powershell
docker compose up -d db
cd backend; .\.venv\Scripts\alembic upgrade head
cd ..\frontend; npm ci; npm run lint; npm run typecheck; npm test -- --run; npm run build
```

Use a disposable database for migration downgrade/re-upgrade. See the API contract and
testing strategy for fuller procedures.
