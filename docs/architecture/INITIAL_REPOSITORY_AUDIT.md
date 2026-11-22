# Initial Repository Audit — Phase 1

**Project:** Rice Age — IoT Rice Quality & Age Analysis Portal
**Audit date:** 22 November 2026
**Auditor role:** Architecture / technical lead
**Repository:** `cs-sakshamm/Grain-Analyzer-Portal`

---

## 1. Git and repository state at audit time

| Item | Observed value |
| --- | --- |
| Working directory | Repository root (`Grain Analyzer Portal`) |
| Current branch | `main` |
| Remote | `origin` → `https://github.com/cs-sakshamm/Grain-Analyzer-Portal.git` |
| Upstream | `main` tracks `main`, reported "up to date with origin/main" |
| Working tree | Clean, no uncommitted changes |
| Commit history | 1 commit — `39e40e1 chore: initialize Rice Age project repository` |
| Remote reachability | Verified with `git ls-remote origin` (returned the same `main` SHA) |
| Commit identity configured | `cs-sakshamm <sakshamvarshney57531@outlook.com>` |

No branches other than `main`, no pull requests, no tags. The repository is a
freshly initialised skeleton with a single commit.

### 1.1 Local toolchain observed

| Tool | Version | Notes |
| --- | --- | --- |
| Python | 3.14.7 | Newer than the CI target; see §7 |
| Node.js | 24.18.0 | Compatible with Vite 7 / React 19 |
| npm | 11.16.0 | — |
| Docker CLI | 29.8.2 | **Daemon not running** (Docker Desktop Linux engine pipe unavailable) |
| Git | — | HTTPS credential helper already authorises push/fetch to `origin` |

---

## 2. Existing repository structure

```text
Grain Analyzer Portal/
├── .gitignore
└── references, requirements and documents/
    ├── APSCSCL_Quality_Certificate_Sample-0038.pdf
    ├── Rice_Age_PRD_V5.pdf
    └── Rice_Age_SOR_V5.pdf
```

The only tracked file is `.gitignore`. There is **no application code, no
configuration, no documentation, and no build tooling** at this point.

### 2.1 Existing implementation to preserve

None. There is no source code to preserve, migrate, or reconcile. The existing
`.gitignore` is sound and already covers `.env` files (with an `!.env.example`
exception), Python and Node build artifacts, IDE folders, local databases,
runtime uploads, test artifacts, and Docker runtime data. It is retained and
extended only where the new toolchain requires it.

### 2.2 Supplied reference documents

| Document | Location | Status |
| --- | --- | --- |
| Product Requirements Document V5.0 (review draft, 22 Nov 2026) | `references, requirements and documents/Rice_Age_PRD_V5.pdf` | Inspected in full (11 pp.) |
| Statement of Requirements V5.0 (review draft, 22 Nov 2026) | `references, requirements and documents/Rice_Age_SOR_V5.pdf` | Inspected in full (11 pp.) |
| APSCSCL sample digital rice quality analysis report | `references, requirements and documents/APSCSCL_Quality_Certificate_Sample-0038.pdf` | Inspected in full (1 p.) |

Both specification documents are explicitly labelled **working drafts** with
"design decisions open" and Section 13 / Section 12 respectively listing items
awaiting stakeholder sign-off. They state they are "not a certification of rice
quality or the prototype device".

---

## 3. What the reference documents establish

Confirmed and usable as architecture input:

1. **Product purpose** — a secure central portal where department users see the
   latest *completed* rice scan, historical records, quality analytics, any
   device-supplied rice-age output, batch comparisons, and original PDF reports.
2. **Ingestion contract (direction only)** — structured JSON analysis results,
   the original device-generated PDF, a primary/bottom platen image and a
   secondary/top platen image "where produced".
3. **Actors** — Super Admin, Department Admin, Department User, and a separate
   non-human IoT Device Identity with no human-portal access.
4. **Mapping rule** — one device is assigned to exactly one department at a time;
   assignment history has effective timestamps; scans retain the department
   assigned at acceptance and never migrate on reassignment.
5. **Seven modules** — Latest Scan, Scan History, Quality Analytics, Rice Age,
   Reports, Batch Comparison, Alerts & Notifications, plus Administration.
6. **State separation** — processing states (Received, Awaiting Files, Verifying,
   Completed, Failed) are distinct from quality verdicts (Pass, Flagged,
   Inconclusive, Lab Confirmation Required); a scan may have the former without
   the latter.
7. **Idempotency** — unique `(device_id, client_scan_id)`; identical replay is
   safe, conflicting replay returns `409`.
8. **Measurement integrity** — count percentage, estimated-mass percentage and
   physical mass must never be blended or relabelled.
9. **Nullable rice age** — the portal displays device-supplied age output and
   must never infer age from images or substitute `0` for missing data.
10. **Advisory positioning** — prototype/experimental limitations, optical
    estimates, and "no statutory certification" language must be preserved.
11. **Proposed endpoints** — device ingestion (5 endpoints) and portal reads
    (8 endpoints) are listed in SOR §5.2 as *design proposals*.

---

## 4. Discrepancies and ambiguities found during inspection

These are recorded rather than resolved; each is tracked in
`docs/decisions/DECISION_REGISTER.md`.

| ID | Observation | Implication |
| --- | --- | --- |
| A-01 | The phase brief, PRD §1.2 and SOR §1 refer to a **Sample-0034** report that "does not include a rice-age estimate". The PDF actually present in the repository is **Sample-0038**, and it *does* contain `Biochemical Age: 8-10 Months (100%)` plus a colour-reference age table. | The rice-age contract is demonstrably non-empty in the newest artifact. Age storage must support a **range + category + confidence**, not only a scalar. Which artifact is authoritative is pending stakeholder confirmation (DR-001, DR-002). |
| A-02 | PRD wireframe for Sample-0034 shows `Big broken 9.90% PASS`; the Sample-0038 certificate shows `Big Broken 30.68% FLAG`. The SOR §8 itself flags this "prototype consistency check". | The portal must display source values and per-parameter status as supplied. It must not recompute or "correct" a verdict. No grading rule may be implemented until the quality team confirms authority (DR-008, DR-009). |
| A-03 | Certificate rows appear internally inconsistent: `Small Broken` shows mass `0.00%` with count `50.69%` and status `PASS` while checking against `Max 1.00%`; the `Foreign Matter` row carries count `50.69%` and `0 k (0.000 g)`; the `Damaged` row carries `184 k (2.721 g)`. Kernel counts in the stub columns are offset from their labels. | Values, labels and bases must be stored exactly as received, keyed by metric code and basis, never inferred from column position. Report rendering must not silently re-derive verdicts. Needs quality-team clarification. |
| A-04 | PRD/SOR text says "does not provide a rice-age estimate" while the certificate prints a biochemical *range* with a 100% share and a freshness rating. | Age schema must support: `age_min_months`, `age_max_months`, `age_category`, `proportion_percent`, free-text `raw_value`, `method`, `model_version`, `confidence`, `validation_status`. |
| A-05 | SOR §5.4 illustrative JSON includes `device_id` in the payload, while §5.5 says the payload device ID is validated against the token and "never authorizes a different device". | Design: the payload `device_id` is optional and, if present, must equal the authenticated device; department is **never** taken from the payload. |
| A-06 | SOR §5.3 lists `grain_count`, `average length/breadth`, `ratio` as flat fields, while §5.1 requires an extensible named-parameter form (value + unit + basis). | The device contract carries **both** a small set of standard grain fields and a generic `measurements[]` array. The final shape is provisional (DR-004). |
| A-07 | Sample certificate includes `Sample Mass (Est.) 8.87 g`, `Total Grains Counted 363`, `L 5.25 mm / W 2.61 mm`; the SOR JSON example uses `364`, `5.44`, `2.70`. | Demonstrates that example JSON must not be treated as fixture truth; fixtures come from real device payloads. |
| A-08 | Devices may or may not emit a top platen image and may or may not emit a PDF ("where required by device capability"). | Attachment roles must be modelled individually with per-scan presence and a configurable mandatory/optional policy (DR-007). |
| A-09 | The certificate is branded as an "Official Certificate" / "DIGITALLY VERIFIED" APSCSCL document, while the requirement set forbids implying statutory certification. | The portal displays the original PDF unmodified and adds advisory framing outside it; no portal-generated certificate is produced in Phase 1 or later without explicit authority. |

---

## 5. Missing components

Everything application-related is missing:

- Frontend application, build configuration, design system.
- Backend service, API layer, persistence layer, migrations.
- Database and any migration baseline.
- Device simulator / integration harness.
- Storage abstraction and upload flow.
- Authentication, authorization, department-scope enforcement.
- Observability, CI, Docker development environment.
- Architecture, database, API, security, and development documentation.
- Agent instruction file (`AGENTS.md`).

---

## 6. Existing technical debt

None inherited. The debt to avoid is prospective:

1. **Verdict recomputation** — a tempting shortcut that would contradict SOR §8.
2. **Department ID from the IoT payload** — explicitly forbidden; would create a
   cross-department write path.
3. **Non-nullable or zero-filled age values** — forbidden by PRD PR-04 and SOR
   FR-04.
4. **Blending measurement bases into single averages** — forbidden by SOR FR-03
   and PRD §7.
5. **Storing public file URLs** — forbidden; private keys plus authorised,
   short-lived access are required.
6. **Hard-coded thresholds or grading rules** — no validated authority exists.

---

## 7. Environment risks observed

| Risk | Detail | Mitigation recorded in Phase 1 |
| --- | --- | --- |
| Local Python 3.14.7 | Very new; some binary wheels (notably database drivers) may lag. | Pin dependency ranges, verify installation locally, and standardise CI on a conservative interpreter version. |
| Docker daemon not running | `docker compose up` cannot be executed in this audit environment. | Compose/Dockerfile configuration is written and syntax-validated with `docker compose config`; runtime bring-up remains an operator step, documented in the setup guide. |
| Guarded push access | Push works through the existing HTTPS credential helper; no SSH key present. | Use the existing remote; never force-push. |

---

## 8. Recommended next steps (Phase 1)

1. Establish repository foundation: `README.md`, `AGENTS.md`, extended `.gitignore`.
2. Finalise and document the technology stack and system architecture.
3. Document the logical database design and ER model.
4. Document the device and portal API contracts plus the device payload schema.
5. Document the security architecture and threat model.
6. Build a reproducible development foundation (backend, frontend, Compose,
   environment template, migrations wiring, foundation tests, CI).
7. Maintain the decision register of open stakeholder questions.
8. Commit and push each unit separately, verifying every push.

Out of scope for Phase 1: the seven departmental UIs, production authentication
experience, admin console, live device integration, camera streaming, statutory
certification logic, and any image-based age inference.
