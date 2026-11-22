# Deployment guide

Provision PostgreSQL 16, private S3-compatible object storage, TLS termination, backend
hosting and static frontend hosting. Copy `.env.example` values into a secret manager.
Production requires `ENVIRONMENT=production`, `DEBUG=false`, a unique 32+ character
`APP_SECRET_KEY`, explicit `CORS_ORIGINS`, `STORAGE_BACKEND=s3`, bucket configuration and
AWS credentials. Port 15432 is local-only.

Run `alembic upgrade head` once per release using a deployment role. Back up before every
migration and test restoration in isolation. The initial migration downgrade removes
tables; never downgrade production without an approved recovery plan.

Deploy the non-root production targets from `backend/Dockerfile` and `frontend/Dockerfile`.
Verify health, readiness, login, device token issuance, authorized report download and a
cross-department denial. Configure logs, backups, restore drills and malware scanning
before production approval.
