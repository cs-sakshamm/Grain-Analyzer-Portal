# Decision Register — Rice Age Portal

Every unresolved requirement is recorded here rather than guessed. Status values:

- **Pending** — no stakeholder decision; do not implement as if confirmed.
- **Confirmed** — a named stakeholder confirmed it (include who and when).
- **Rejected** — considered and declined (include why).

Nothing in this register is `Confirmed` in Phase 1: the PRD and SOR are explicitly
"review drafts" with decisions open, and no stakeholder sign-off has been provided.

Where a decision blocks implementation, the Phase 1 design either supports multiple
outcomes (nullable columns, generic measurement codes, configurable limits) or defers
the feature.

---

## Summary

| ID | Topic | Status | Blocks |
| --- | --- | --- | --- |
| DR-001 | Final rice-age result format | Pending | Age analytics and comparison UI |
| DR-002 | Age unit and interpretation | Pending | Age display and trend charts |
| DR-003 | Age model version and confidence semantics | Pending | Cross-scan age comparison |
| DR-004 | Device JSON payload specification | Pending | Scan ingestion implementation |
| DR-005 | Maximum upload size | Pending | Upload limit enforcement |
| DR-006 | Supported file formats (and malware scanning) | Pending | File type allowlist |
| DR-007 | Mandatory vs optional attachments | Pending | Finalize validation rules |
| DR-008 | Quality verdict rules and authority | Pending | Any verdict presentation as authoritative |
| DR-009 | Verdict priority with multiple conditions | Pending | Aggregated verdict display |
| DR-010 | Cloud vs on-premises deployment | Pending | Production infrastructure |
| DR-011 | Authentication implementation (MFA/SSO/reset) | Pending | Production auth experience |
| DR-012 | Email or other notification provider | Pending | Out-of-portal notifications |
| DR-013 | Data retention policy | Pending | Purge jobs, audit retention |
| DR-014 | Backup frequency | Pending | Backup automation |
| DR-015 | RTO / RPO | Pending | Disaster recovery design |
| DR-016 | Expected number of departments | Pending | Capacity, seeding, isolation testing |
| DR-017 | Expected number of devices | Pending | Capacity, rate limits |
| DR-018 | Expected scan volume | Pending | Performance targets, indexing, workers |
| DR-019 | Department Admin user-management permissions | Pending | Admin authorization matrix |
| DR-020 | Exact batch comparison rules | Pending | Comparison UI and API |
| DR-021 | Final report layout and approval requirements | Pending | Report module beyond original PDF |
| DR-022 | Authoritative sample/certificate artifact (0034 vs 0038) | Pending | Age contract, fixtures |
| DR-023 | Source verdict vs parameter verdict inconsistency | Pending | Verdict display semantics |

---

## DR-001 — Final rice-age result format

| Field | Content |
| --- | --- |
| **Current understanding** | SOR §5.3 permits a "nullable age value, unit, model/method version, optional uncertainty/validation". PRD PR-04 leaves "numeric age / category / both" open. The Sample-0038 certificate prints `Biochemical Age: 8-10 Months (100%)` plus a colour-reference table of estimated ranges. |
| **Options** | (a) scalar months; (b) category/range only; (c) both scalar and range with proportion; (d) qualitative class with freshness rating. |
| **Technical impact** | `age_results` already supports scalar, min/max range, category and proportion. If the device later supplies only a colour/class, no migration is needed. If it supplies a richer distribution (multiple buckets per scan), the one-result-per-scan constraint would need a child table. |
| **Recommended approach** | Support all four in storage; render the most specific supplied form, preferring scalar, then category, then range. Do not compute one from another. |
| **Status** | Pending |
| **Stakeholder** | IoT/algorithm owner + Product Owner |

---

## DR-002 — Age unit and interpretation

| Field | Content |
| --- | --- |
| **Current understanding** | The certificate labels the result "Biochemical Age" with a month range and a freshness rating ("Sound Commercial Grain (Medium Storage Age)"). The PRD states the method, units and validated meaning are pending firmware-team confirmation. |
| **Options** | Calendar months since harvest; storage duration band; a device-specific index; unknown. |
| **Technical impact** | Whether `months` is a duration or an ordinal band. Comparisons and trend charts are only valid if the semantics are consistent across scans. |
| **Recommended approach** | Store unit verbatim (`age_results.unit`) and never relabel; until confirmed, display the supplied text and disable cross-scan age trend claims. |
| **Status** | Pending |
| **Stakeholder** | IoT/algorithm owner |

---

## DR-003 — Age model version and confidence semantics

| Field | Content |
| --- | --- |
| **Current understanding** | Payload may carry `model_version`, `confidence`, `validation_status`. No definition of confidence scale (0–1 vs 0–100) or what "validated" means. |
| **Options** | Percentage confidence; categorical (low/medium/high); none. Model versions may be comparable or not. |
| **Technical impact** | Comparison grouping; whether confidence is displayed numerically or as a band; whether `validation_status` can ever be `validated` without external evidence. |
| **Recommended approach** | Store as supplied with a normalised numeric range only when the device declares the scale; compare only identical `model_version` + `method`; `validation_status` defaults to `unvalidated` when absent. |
| **Status** | Pending |
| **Stakeholder** | IoT/algorithm owner + Quality lead |

---

## DR-004 — Device JSON payload specification

| Field | Content |
| --- | --- |
| **Current understanding** | SOR §5.3–5.4 gives an illustrative payload; the endpoint list and "final HTTP contracts, schemas, upload strategy, limits and security profile must be agreed with the IoT firmware team". |
| **Options** | Accept the SOR illustrative shape as-is; adopt the generic `measurements[]` array; a hybrid (both), as drafted. |
| **Technical impact** | Ingestion validation, metric code mapping, device simulator, firmware changes. Unknown top-level fields are currently rejected, so firmware additions need a contract revision. |
| **Recommended approach** | `docs/api/device-payload.schema.json` v1.0 as the reviewable baseline; version the schema and keep optional fields additive. |
| **Status** | Pending (provisional contract published for review) |
| **Stakeholder** | IoT firmware team + Technical Lead |

---

## DR-005 — Maximum upload size

| Field | Content |
| --- | --- |
| **Current understanding** | No limit stated. Phase 1 uses configurable provisional values (PDF 25 MiB, image 15 MiB) for local development only. |
| **Options** | Per-role limits based on device output; a single global cap; none until measured. |
| **Technical impact** | Reverse-proxy and application body limits, storage cost, timeout tuning, device retry behaviour. |
| **Recommended approach** | Measure real device output, then set per-role limits with headroom; keep them configuration, not code. |
| **Status** | Pending |
| **Stakeholder** | IoT firmware team + Operations |

---

## DR-006 — Supported file formats (and malware scanning)

| Field | Content |
| --- | --- |
| **Current understanding** | PDF plus optical images; exact formats and whether SVG/TIFF are possible are unspecified. Malware scanning is "where appropriate" in SOR §9.1. |
| **Options** | PDF + JPEG/PNG only; add WebP/TIFF; plus external AV scanning. |
| **Technical impact** | Role↔MIME allowlist, magic-byte checks, preview support, storage cost, security posture. |
| **Recommended approach** | Start with PDF + JPEG + PNG; reject SVG and archives; add malware scanning before production if the deployment handles untrusted uploads. |
| **Status** | Pending |
| **Stakeholder** | IoT firmware team + Security owner |

---

## DR-007 — Mandatory vs optional attachments

| Field | Content |
| --- | --- |
| **Current understanding** | SOR says the PDF and both images are produced "when produced"/"where required by device capability"; FR-01 expects both platen images where provided. It is unclear whether a completed scan requires all three. |
| **Options** | PDF + bottom image mandatory, top optional; all three mandatory; per-device capability profile. |
| **Technical impact** | Finalize validation, "completed" semantics, UI unavailable states, device retry behaviour. |
| **Recommended approach** | Per-device capability profile with PDF + bottom mandatory by default; make the policy configuration, not schema. |
| **Status** | Pending |
| **Stakeholder** | IoT firmware team + Product Owner |

---

## DR-008 — Quality verdict rules and their authority

| Field | Content |
| --- | --- |
| **Current understanding** | The portal must display supplied verdicts and must not recompute them. Whether any threshold is statutory or validated is explicitly unresolved; the certificate's limits come from a demo prototype. |
| **Options** | Display-only source verdicts; validated APSCSCL rule set; no verdict display at all beyond raw values. |
| **Technical impact** | Whether `quality_evaluations` gains authoritative rule references; wording of every verdict badge; whether any compliance claim is possible. |
| **Recommended approach** | Display-only, with ruleset version and advisory label; never describe a verdict as certification. |
| **Status** | Pending |
| **Stakeholder** | Quality lead (APSCSCL) |

---

## DR-009 — Verdict priority when multiple conditions occur

| Field | Content |
| --- | --- |
| **Current understanding** | Four verdicts exist. The SOR does not define precedence when parameters disagree (e.g. one PASS, one FLAG, one LAB CONFIRMATION). The certificate's overall disposition is FLAG while several rows read PASS. |
| **Options** | Worst-case wins; explicit priority list; device supplies overall only; no aggregation. |
| **Technical impact** | Whether the backend stores a derived overall verdict (currently forbidden until agreed) and how analytics count outcomes. |
| **Recommended approach** | Use the device's `evaluation.overall` verbatim; if absent, show "not stated" rather than deriving one. If aggregation is later required, implement it in the service layer with a documented, stakeholder-approved priority. |
| **Status** | Pending |
| **Stakeholder** | Quality lead |

---

## DR-010 — Cloud vs on-premises deployment

| Field | Content |
| --- | --- |
| **Current understanding** | SOR §6 says "the hosting model remains open"; §11 lists cloud/on-prem as an owner decision. |
| **Options** | Managed cloud (object storage, managed PostgreSQL); on-prem server with S3-compatible storage (MinIO); hybrid. |
| **Technical impact** | Secret management, TLS termination, storage adapter configuration, backups, CI/CD target, monitoring. |
| **Recommended approach** | Keep the stack provider-neutral; storage and DB are already abstracted. Decide before production hardening. |
| **Status** | Pending |
| **Stakeholder** | Project owner |

---

## DR-011 — Authentication implementation

| Field | Content |
| --- | --- |
| **Current understanding** | Email + password login is confirmed. MFA, SSO, password-reset channel and session lifetime policy are unspecified. |
| **Options** | Local accounts (Argon2id) with rotating refresh sessions; add TOTP MFA; institutional SSO/OIDC. |
| **Technical impact** | `user_sessions` and `users.password_hash` are compatible with MFA; SSO would add an identity-provider dependency and possibly remove password storage. |
| **Recommended approach** | Implement local accounts as designed; treat MFA as a policy flag; design SSO as a later adapter. |
| **Status** | Pending |
| **Stakeholder** | Project owner + Security owner |

---

## DR-012 — Email or other notification provider

| Field | Content |
| --- | --- |
| **Current understanding** | In-portal notifications are in scope; email is explicitly not assumed and user opt-outs/routing are undecided. |
| **Options** | In-portal only; email via a transactional provider; SMS/other. |
| **Technical impact** | New PII flow, provider credentials, delivery retries, deduplication across channels, unsubscribe handling. |
| **Recommended approach** | Ship in-portal only; add a notification-channel abstraction before any email work. |
| **Status** | Pending |
| **Stakeholder** | Product Owner |

---

## DR-013 — Data retention policy

| Field | Content |
| --- | --- |
| **Current understanding** | "Configurable retention" is required; no period is given. Retention affects scans, raw payloads, files, notifications and audit logs. |
| **Options** | Fixed multi-year retention; per-department policy; indefinite with archival. |
| **Technical impact** | Purge jobs, object-store lifecycle rules, audit retention, backup size, legal hold. |
| **Recommended approach** | Define per-table periods with audit retention longer than scan retention; implement deletion only after approval. No automatic deletion is enabled now. |
| **Status** | Pending |
| **Stakeholder** | Project owner + Legal/Compliance |

---

## DR-014 — Backup frequency

| Field | Content |
| --- | --- |
| **Current understanding** | Encrypted backups and restores are required; frequency is unspecified. |
| **Options** | Daily full + WAL archiving; hourly incremental. |
| **Technical impact** | RPO achievability, storage cost, restore procedure, drill schedule. |
| **Recommended approach** | Daily encrypted full backup plus continuous WAL archiving once volume is known. |
| **Status** | Pending |
| **Stakeholder** | Operations owner |

---

## DR-015 — RTO / RPO

| Field | Content |
| --- | --- |
| **Current understanding** | Not stated. |
| **Options** | e.g. RTO 8 h / RPO 24 h; tighter targets cost more. |
| **Technical impact** | Standby strategy, backup frequency, runbooks, testing. |
| **Recommended approach** | Agree business targets before sizing infrastructure. |
| **Status** | Pending |
| **Stakeholder** | Project owner |

---

## DR-016 — Expected number of departments

| Field | Content |
| --- | --- |
| **Options** | Single-digit pilot; tens; state-wide. |
| **Technical impact** | Seeding, admin UX, index selectivity (limited), isolation test matrix, reporting scope. |
| **Recommended approach** | Design is department-scalable; no hard-coded department list. |
| **Status** | Pending |
| **Stakeholder** | Project owner |

---

## DR-017 — Expected number of devices

| Field | Content |
| --- | --- |
| **Options** | A few kiosks; hundreds. |
| **Technical impact** | Token issuance rate, connection concurrency, rate-limit tuning, credential operations. |
| **Recommended approach** | Per-device credentials and rate limits scale linearly; size infrastructure after confirmation. |
| **Status** | Pending |
| **Stakeholder** | IoT lead |

---

## DR-018 — Expected scan volume

| Field | Content |
| --- | --- |
| **Options** | Tens per day; thousands per day; seasonal peaks at procurement. |
| **Technical impact** | Performance targets (currently provisional), partitioning (not planned), analytics query cost, worker need, storage growth. |
| **Recommended approach** | Establish volume and peak pattern, then set p95 targets and consider pre-aggregation. |
| **Status** | Pending |
| **Stakeholder** | Project owner + IoT lead |

---

## DR-019 — Department Admin user-management permissions

| Field | Content |
| --- | --- |
| **Current understanding** | SOR §3.1 says Department Admin may manage "own department" users; PRD §12 asks whether department admins can manage users and what downloads are allowed. |
| **Options** | Create users + assign roles within own department; also reset passwords; read-only user list. |
| **Technical impact** | Authorization matrix and tests; whether Department Admin can grant `department_admin`. |
| **Recommended approach** | Implement own-department create/role-change only (no super-admin creation, no cross-department), then widen after confirmation. |
| **Status** | Pending |
| **Stakeholder** | Product Owner |

---

## DR-020 — Exact batch comparison rules

| Field | Content |
| --- | --- |
| **Current understanding** | Compare two or more batches with warnings on missing data, differing bases and differing models; no objective ranking without an agreed formula. |
| **Options** | Descriptive side-by-side only; weighted score per batch; pass-rate comparison. |
| **Technical impact** | Response shape, whether any derived score is stored or computed, UI wording. |
| **Recommended approach** | Descriptive aggregates only; return `ranking: null` with an explanation until a formula is approved. |
| **Status** | Pending |
| **Stakeholder** | Quality lead + Product Owner |

---

## DR-021 — Final report layout and approval requirements

| Field | Content |
| --- | --- |
| **Current understanding** | Phase 1 and the MVP serve the original device PDF unmodified. A portal-generated report layout, branding and approval workflow are only mentioned as future scope. |
| **Options** | Original PDF only; portal cover page + original PDF; fully generated report with approval signature. |
| **Technical impact** | Whether a report-rendering subsystem (HTML→PDF) and approval entity are needed; certification wording. |
| **Recommended approach** | Continue serving the original PDF byte-for-byte; any generated report requires explicit authority and an approval model. |
| **Status** | Pending |
| **Stakeholder** | APSCSCL Quality lead + Project Owner |

---

## DR-022 — Authoritative sample/certificate artifact (0034 vs 0038)

| Field | Content |
| --- | --- |
| **Current understanding** | The PRD/SOR describe Sample-0034 as having no rice-age estimate. The repository's actual PDF is Sample-0038 and includes a biochemical age band. The two artifacts also disagree on grain count (363 vs 364) and dimensions (5.25/2.61 vs 5.44/2.70). |
| **Options** | Sample-0038 is the current device output and supersedes 0034; both are valid for different firmware versions; the PRD text is stale. |
| **Technical impact** | Age contract, fixture data, acceptance tests, report rendering expectations. |
| **Recommended approach** | Treat Sample-0038 as the observed artifact and Sample-0034 only as a historical wireframe; obtain confirmation before writing fixtures or age UI copy. |
| **Status** | Pending |
| **Stakeholder** | IoT lead / Product Owner |

---

## DR-023 — Source verdict vs parameter verdict inconsistency

| Field | Content |
| --- | --- |
| **Current understanding** | The SOR flags that screenshots and the PDF present pass/fail indicators differently; the Sample-0038 table itself shows rows whose values and statuses look inconsistent (e.g. small-broken count 50.69% marked PASS against Max 1.00%). |
| **Options** | Device is correct and labels are misaligned; portal should display only overall verdict; portal should display per-parameter values without status until verified. |
| **Technical impact** | Verdict UI, analytics counts, trust in the data, potential need for a "disputed" flag. |
| **Recommended approach** | Store and display exactly what the device sends, keyed by metric and basis; do not infer status from values; add an explicit advisory that parameter statuses are device-reported. |
| **Status** | Pending |
| **Stakeholder** | Quality lead + IoT firmware team |

---

## Register maintenance

- Add an entry before implementing behaviour that depends on an unconfirmed rule.
- Move to `Confirmed` only with a named stakeholder and date, and update the affected
  documents in the same change.
- Closed decisions keep their entry (with the resolution) so the reasoning is auditable.
- Schema-affecting decisions also update `docs/database/DATABASE_SCHEMA.md` §21.

---

## DR-024 — Interim Department Admin policy (implements part of DR-019)

| Field | Content |
| --- | --- |
| **Current understanding** | DR-019's final matrix is still unconfirmed. Phase 2 therefore ships the conservative rule the API contract already described. |
| **Implemented** | A Department Admin may list users, create users, assign memberships and change roles **only within their own department**. They may not create or promote a super admin, cannot act outside their department, and cannot manage devices or credentials. Every such action is audited. |
| **Why this is safe** | It never grants more than the least-privilege reading of DR-019 and is enforced in the service layer, so widening it later is a policy change rather than a security fix. |
| **Status** | Pending (provisional implementation recorded) |
| **Stakeholder** | Product Owner / departmental administrators |

## DR-025 — Provisional attachment policy (implements part of DR-007)

| Field | Content |
| --- | --- |
| **Current understanding** | The contract example requires the original PDF and bottom image and treats the top image as optional; DR-007 is still open. |
| **Implemented** | `REQUIRED_ATTACHMENT_ROLES` (default `report_pdf,bottom_image`) drives finalize. Changing the decision is configuration, not a migration. `top_image` and `other` are accepted but optional. |
| **Status** | Pending (configurable provisional default) |
| **Stakeholder** | Device team + Product Owner |

## DR-026 — Rate limiting is in-process

| Field | Content |
| --- | --- |
| **Current understanding** | Login and device-token throttling exist, but counters live in one process. |
| **Impact** | Multiple API workers would each allow the configured quota; a shared store is required before horizontal scaling. Single-process deployment is the Phase 2 assumption. |
| **Status** | Pending (tied to DR-010 deployment model) |
| **Stakeholder** | Operations / architecture |

## DR-027 — Authentication scope for Phase 2

| Field | Content |
| --- | --- |
| **Current understanding** | Email + password, Argon2id, 15-minute access JWT in memory, rotating refresh cookie (`HttpOnly`, `SameSite=Strict`, `Secure` in production). |
| **Not implemented** | MFA, SSO, and email-based password reset (DR-011). Password change is implemented and revokes other sessions. |
| **Status** | Pending for the production experience; the conservative baseline is implemented |
| **Stakeholder** | Security / Product Owner |
