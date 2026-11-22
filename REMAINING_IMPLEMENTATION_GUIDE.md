# Next-developer implementation guide

## Current implementation

API routers: `backend/app/api/v1/endpoints/`; service authorization: `backend/app/services/`;
schema: `backend/migrations/versions/0001_initial_schema.py`; device contract:
`docs/api/device-payload.schema.json`; simulator: `device-simulator/simulator.py`; portal
pages: `frontend/src/pages/`.

## API integration

`postman/Rice_Age_Portal.postman_collection.json` (with
`postman/Rice_Age_Local.postman_environment.json` and `postman/POSTMAN_API_GUIDE.md`)
covers all 42 implemented operations: health, human auth, administration, device
credentials, the scan ingestion lifecycle, portal reads/analytics and the security
negative cases. Regenerate with `python postman/build_collection.py`; validate against
the app's OpenAPI document with `python postman/validate_collection.py`.

There is no audit read API, no notification mark-as-read, no password reset by email, no
platen image download and no admin console UI. Admin functionality is API-only.

## Remaining work

| Priority | Owner | Work | Acceptance |
|---|---|---|---|
| Critical | IoT developer | Map hardware to schema 1.0, submit, attach, finalize. | A completed scan is visible only to its assigned department. |
| Critical | DevOps | Provision PostgreSQL 16, private object storage, HTTPS, secrets, backup/restore and monitoring. | Production rejects development secret and local storage. |
| High | Stakeholder | Confirm payload, upload limits, attachment policy, thresholds and retention. | Resolve DR-001–DR-023; do not invent values. |
| High | Security | Add malware scanning and a distributed limiter before horizontal scale. | DR-026 is resolved with deployment architecture. |
| Medium | Frontend | Implement admin UX if approved. | Reuse `/api/v1/admin/*`; do not duplicate authorization. |
| Medium | Backend | Add an audit read API if operators need it; audit rows are already written. | Read is department-scoped and role-restricted. |
| Medium | Backend | Add notification read-state endpoint and platen image delivery. | Access stays department-scoped and audited. |
| Low | Frontend | Wire scan-history filters and pagination to the supported query parameters. | No client-side filtering of a server-scoped list. |

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
