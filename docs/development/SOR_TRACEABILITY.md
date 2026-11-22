# SOR / PRD traceability summary

| Area | Implementation evidence | Status | Remaining work |
|---|---|---|---|
| Human auth and rotation | `auth_service.py`, `test_auth_admin.py` | Complete | MFA/SSO/reset depend on DR-011. |
| Device auth and ingestion | `device_auth.py`, `device_scans.py`, simulator | Complete boundary | Hardware mapping/connectivity pending. |
| Department isolation/history | `authorization.py`, `admin_service.py`, integration tests | Complete | Regression test required for every new route. |
| Files | `scan_service.py`, `storage/`, report route | Partial | Production malware scanner and S3 provisioning. |
| Department modules | `scans.py`, `frontend/src/pages/` | Partial | Browser E2E and admin UI are pending. |
| Deployment/operations | Dockerfiles, compose, CI | Partial | Hosting, backups, monitoring and secrets provisioning. |

This is a code-evidence audit, not statutory certification. Open stakeholder decisions
remain authoritative in `docs/decisions/DECISION_REGISTER.md`.
