# Rice Age system flow

`frontend/src/routes/routes.tsx` protects portal routes and calls FastAPI through
`frontend/src/services/apiClient.ts`. `backend/app/main.py` hosts `/api/v1`; routers
call services, which own authorization and persistence. PostgreSQL stores metadata and
`backend/app/storage/` keeps bytes private locally (development) or in S3 (production).

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
