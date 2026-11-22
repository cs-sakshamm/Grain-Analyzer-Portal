# Rice Age system flow

`frontend/src/routes/config.tsx` (built into a browser router by `routes.tsx`) protects
portal routes and calls FastAPI through `frontend/src/services/apiClient.ts`.
`backend/app/main.py` hosts `/api/v1`; routers call services, which own authorization and
persistence. Static scan paths must be declared before `/scans/{scan_id}` in
`backend/app/api/v1/endpoints/scans.py`. PostgreSQL stores metadata and
`backend/app/storage/` keeps bytes private locally (development) or in S3 (production).

## Portal routes

| Path | Module |
| --- | --- |
| `/` | Latest Scan (latest **completed** scan for the caller's department) |
| `/scan-history` | Scan History |
| `/quality-analytics` | Quality Analytics |
| `/rice-age` | Rice Age (device-supplied only) |
| `/reports` | Reports and original PDF download |
| `/batch-comparison` | Batch Comparison |
| `/alerts` | Alerts & Notifications |
| `/scans/:scanId` | Scan detail (target of history/report/alert deep links) |
| `/status` | System status (liveness + readiness) |
| `/login` | Sign-in; every other route requires a session |

All seven modules are visible to every authenticated portal user; the backend scopes and
authorizes each response. A super admin must add `?department_id=` to scan routes.

## API testing

`postman/` contains an importable collection covering all 42 implemented operations, a
local environment template and `POSTMAN_API_GUIDE.md`. `python
postman/build_collection.py` regenerates it and `python postman/validate_collection.py`
checks it against the app's OpenAPI document.

## Device submission

1. A super administrator registers a device and assignment through the admin API.
2. The device obtains a token at `POST /api/v1/device-auth/token`.
3. It sends schema 1.0 JSON to `POST /api/v1/device/scans`; department ownership is
   taken from its authenticated active assignment, never the payload.
4. It prepares/uploads attachments and finalizes. Required attachment roles are config;
   top image is optional.
5. Finalization verifies checksums and makes a scan completed. Only completed scans
   appear in portal views.

## Invariants

- Reassignment closes the old assignment; existing scan department snapshots never move.
- Processing state and device quality verdict remain distinct.
- Age is optional device output; there is no image inference.
- Measurements remain grouped by basis; count and estimated-mass percentages are not blended.
