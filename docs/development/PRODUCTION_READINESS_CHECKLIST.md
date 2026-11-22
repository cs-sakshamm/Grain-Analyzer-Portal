# Production readiness checklist

- [ ] Stakeholders resolve required decisions in `docs/decisions/DECISION_REGISTER.md`.
- [ ] Production PostgreSQL 16 is backed up and restore-tested.
- [ ] Private S3 bucket, IAM least privilege, malware scanning and retention lifecycle are approved.
- [ ] TLS, production CORS allowlist, secret manager and unique `APP_SECRET_KEY` are configured.
- [ ] Distributed rate limiting is supplied if multiple backend workers are used (DR-026).
- [ ] Device credentials are issued per device and hardware submission is verified.
- [ ] Migration, backend suite, frontend lint/typecheck/tests/build and simulator E2E pass.
- [ ] Department isolation and authorized report download are manually retested.
