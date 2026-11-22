# Database Schema — Rice Age Portal

**Engine:** PostgreSQL 16+ (partial unique indexes; `citext` extension; `NULLS NOT
DISTINCT` for the batches unique index requires PostgreSQL 15+).
**Status:** implemented in Phase 2 as migration `0001_initial_schema`. The logical
model below is the reference; the notes at the end record deliberate physical
differences. Open decisions still affect behaviour (attachment policy, verdict
semantics) rather than the core shape, which is deliberately nullable and generic.

Conventions used throughout:

- Snake_case identifiers, plural table names, UUID v4 primary keys
  (`gen_random_uuid()`), `TIMESTAMPTZ` in UTC, `NUMERIC` for any measurement.
- Every table has `created_at`; mutable tables add `updated_at` maintained by the
  application (not by triggers, to keep behaviour explicit).
- `ON DELETE RESTRICT` is the default for organisational references. `CASCADE` is used
  only for values that cannot exist without their parent (measurements, files).
- Enums are PostgreSQL enums with stable lowercase values; new values are added by
  migration and never renamed in place.

---

## 1. Enumerated types

```sql
CREATE TYPE membership_role AS ENUM ('department_admin', 'department_user');

CREATE TYPE device_status AS ENUM ('provisioned', 'active', 'suspended', 'retired');

CREATE TYPE scan_processing_status AS ENUM (
  'received', 'awaiting_files', 'verifying', 'completed', 'failed'
);

CREATE TYPE quality_verdict AS ENUM (
  'pass', 'flagged', 'inconclusive', 'lab_confirmation_required'
);

CREATE TYPE measurement_basis AS ENUM (
  'count_percent',            -- share of kernels counted
  'estimated_mass_percent',   -- optical estimate of mass share
  'physical_mass_percent',    -- physically weighed share
  'physical_mass_grams',      -- physically weighed absolute mass
  'count',                    -- absolute kernel count
  'dimension',                -- length/breadth in millimetres
  'ratio',                    -- dimensionless ratio (e.g. L/B)
  'other'                     -- explicitly supplied basis, described in metadata
);

CREATE TYPE scan_file_role AS ENUM ('report_pdf', 'bottom_image', 'top_image', 'other');

CREATE TYPE upload_status AS ENUM ('pending', 'uploaded', 'verified', 'rejected');

CREATE TYPE age_validation_status AS ENUM (
  'unvalidated', 'provisional', 'validated', 'rejected'
);

CREATE TYPE notification_event_type AS ENUM (
  'scan_completed', 'quality_flagged', 'upload_failed', 'report_available',
  'lab_confirmation_required'
);

CREATE TYPE notification_severity AS ENUM ('info', 'warning', 'critical');

CREATE TYPE audit_actor_type AS ENUM ('user', 'device', 'system');
```

`measurement_basis` deliberately distinguishes `estimated_mass_percent` from
`physical_mass_percent`. The portal must never present one as the other (SOR §5.3,
FR-03).

---

## 2. `departments`

**Purpose:** organisational owner of users, devices (via assignments), batches, scans
and notifications.

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | PK |
| `code` | `varchar(32)` | no | — | Unique, immutable after creation; used in logs and UI |
| `name` | `varchar(200)` | no | — | Display name |
| `location` | `varchar(255)` | yes | `NULL` | Optional per SOR §4.1 |
| `is_active` | `boolean` | no | `true` | Deactivation instead of deletion |
| `created_at` | `timestamptz` | no | `now()` | |
| `updated_at` | `timestamptz` | no | `now()` | |

Constraints and indexes:

- `PRIMARY KEY (id)`
- `UNIQUE (code)`
- `INDEX idx_departments_active (is_active)`

Relationships: 1:N `memberships`, `device_assignments`, `batches`, `scans`,
`notifications`, `audit_logs`.

Retention: departments are **deactivated, never hard-deleted** while any scan,
membership or device assignment references them (`ON DELETE RESTRICT`).

---

## 3. `users`

**Purpose:** human identities. Devices are **not** rows here.

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | PK |
| `email` | `citext` | no | — | Case-insensitive unique login identifier |
| `password_hash` | `text` | no | — | Argon2id encoded string, never a raw password |
| `full_name` | `varchar(200)` | yes | `NULL` | |
| `is_super_admin` | `boolean` | no | `false` | Global privileges; every use is audited |
| `is_active` | `boolean` | no | `true` | Deactivated users cannot authenticate |
| `last_login_at` | `timestamptz` | yes | `NULL` | |
| `created_at` | `timestamptz` | no | `now()` | |
| `updated_at` | `timestamptz` | no | `now()` | |

Constraints and indexes:

- `PRIMARY KEY (id)`
- `UNIQUE (email)`
- `INDEX idx_users_active (is_active)`
- `CHECK (is_super_admin IS FALSE OR is_active IS TRUE)` is **not** applied — an
  inactive super admin must remain representable for audit history.

Notes:

- No self-registration path exists; users are created by administrators (PRD §2.1).
- Super-admin status is a user-level flag because the role is system-wide and not tied
  to a single department. Service code treats `is_super_admin = true` as "may act
  across departments with explicit selection and audit".
- Department-level privileges come only from `memberships`.

Retention: users are deactivated; deletion is blocked while audit or membership rows
reference them (`ON DELETE RESTRICT` for memberships, `SET NULL` for audit actors).

---

## 4. `memberships`

**Purpose:** assigns a department-scoped role to a human user.

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | PK |
| `user_id` | `uuid` | no | — | FK → `users(id)` `ON DELETE CASCADE` |
| `department_id` | `uuid` | no | — | FK → `departments(id)` `ON DELETE RESTRICT` |
| `role` | `membership_role` | no | — | `department_admin` \| `department_user` |
| `is_active` | `boolean` | no | `true` | Soft revocation |
| `created_at` | `timestamptz` | no | `now()` | |
| `updated_at` | `timestamptz` | no | `now()` | |

Constraints and indexes:

- `PRIMARY KEY (id)`
- `UNIQUE (user_id, department_id)` — one role per user per department
- `INDEX idx_memberships_department (department_id, role) WHERE is_active`
- `INDEX idx_memberships_user (user_id) WHERE is_active`

Notes: role changes update the row and write an `audit_logs` entry. A user with
memberships in several departments selects an active department per session/request;
the API returns only that department's data.

---

## 5. `user_sessions`

**Purpose:** server-side refresh sessions enabling rotation, revocation and reuse
detection. Human tokens are never stored in plaintext.

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | PK |
| `user_id` | `uuid` | no | — | FK → `users(id)` `ON DELETE CASCADE` |
| `refresh_token_hash` | `char(64)` | no | — | SHA-256 hex of the opaque refresh token |
| `token_family_id` | `uuid` | no | — | Shared by all rotations of one login |
| `issued_at` | `timestamptz` | no | `now()` | |
| `expires_at` | `timestamptz` | no | — | Absolute expiry |
| `revoked_at` | `timestamptz` | yes | `NULL` | Logout, rotation, reuse detection |
| `last_used_at` | `timestamptz` | yes | `NULL` | |
| `ip_address` | `inet` | yes | `NULL` | |
| `user_agent` | `text` | yes | `NULL` | |

Constraints and indexes:

- `PRIMARY KEY (id)`
- `UNIQUE (refresh_token_hash)`
- `INDEX idx_user_sessions_user (user_id, expires_at DESC)`
- `INDEX idx_user_sessions_family (token_family_id)`

Retention: expired or revoked rows are purged after 30 days (provisional).

---

## 6. `devices`

**Purpose:** registry of physical IoT analysers. Credential material lives in
`device_credentials`.

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | PK |
| `device_uid` | `varchar(64)` | no | — | Logical identifier used in payloads, e.g. `RICE-DEVICE-001` |
| `serial_number` | `varchar(128)` | no | — | Physical serial; unique under registration policy |
| `friendly_name` | `varchar(200)` | yes | `NULL` | Optional per SOR §4.2 |
| `model` | `varchar(120)` | yes | `NULL` | |
| `hardware_revision` | `varchar(64)` | yes | `NULL` | |
| `firmware_version` | `varchar(64)` | yes | `NULL` | Recorded as reported; drives payload compatibility |
| `installation_location` | `varchar(255)` | yes | `NULL` | |
| `status` | `device_status` | no | `'provisioned'` | `provisioned` → `active` → `suspended` / `retired` |
| `provisioned_at` | `timestamptz` | yes | `NULL` | |
| `activated_at` | `timestamptz` | yes | `NULL` | |
| `last_seen_at` | `timestamptz` | yes | `NULL` | Updated by authenticated device calls |
| `last_upload_at` | `timestamptz` | yes | `NULL` | Last successful finalized scan |
| `last_error_code` | `varchar(64)` | yes | `NULL` | Operational diagnostics |
| `created_at` | `timestamptz` | no | `now()` | |
| `updated_at` | `timestamptz` | no | `now()` | |

Constraints and indexes:

- `PRIMARY KEY (id)`
- `UNIQUE (device_uid)`
- `UNIQUE (serial_number)`
- `INDEX idx_devices_status (status)`
- `INDEX idx_devices_last_seen (last_seen_at DESC)` — stale-device reporting

Notes: a device may submit only while `status = 'active'` **and** it has an active
assignment. Suspension blocks authentication and ingestion immediately.

Retention: devices are retired, never deleted while scans exist.

---

## 7. `device_credentials`

**Purpose:** per-device machine credentials with rotation history. No shared secret
exists (SOR §9.1).

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | PK |
| `device_id` | `uuid` | no | — | FK → `devices(id)` `ON DELETE RESTRICT` |
| `client_id` | `varchar(64)` | no | — | Public identifier used at token request |
| `secret_hash` | `text` | no | — | Argon2id of the generated device secret |
| `version` | `integer` | no | — | Monotonic per device |
| `created_by_user_id` | `uuid` | yes | `NULL` | FK → `users(id)` `ON DELETE SET NULL` |
| `created_at` | `timestamptz` | no | `now()` | |
| `expires_at` | `timestamptz` | yes | `NULL` | Optional hard expiry |
| `revoked_at` | `timestamptz` | yes | `NULL` | Rotation or compromise |
| `revoked_reason` | `varchar(120)` | yes | `NULL` | |

Constraints and indexes:

- `PRIMARY KEY (id)`
- `UNIQUE (client_id)`
- `UNIQUE (device_id, version)`
- `CREATE UNIQUE INDEX uq_device_credentials_active ON device_credentials (device_id) WHERE revoked_at IS NULL;`
- `INDEX idx_device_credentials_device (device_id, created_at DESC)`

Notes: rotation inserts the new credential and revokes the previous one in a single
transaction; a short overlap window is a policy decision, not a schema feature. Only
a hash is stored, so a lost device secret is re-provisioned, never recovered.

Retention: revoked rows are retained for audit.

---

## 8. `device_assignments`

**Purpose:** department ownership of a device over time. This is the only source of
truth for "which department does this device currently belong to".

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | PK |
| `device_id` | `uuid` | no | — | FK → `devices(id)` `ON DELETE RESTRICT` |
| `department_id` | `uuid` | no | — | FK → `departments(id)` `ON DELETE RESTRICT` |
| `effective_from` | `timestamptz` | no | `now()` | Start of ownership |
| `effective_to` | `timestamptz` | yes | `NULL` | `NULL` means **active** |
| `assigned_by_user_id` | `uuid` | yes | `NULL` | FK → `users(id)` `ON DELETE SET NULL`; must be a super admin at write time |
| `reason` | `text` | yes | `NULL` | Free-text rationale, audited |
| `created_at` | `timestamptz` | no | `now()` | |

Constraints and indexes:

- `PRIMARY KEY (id)`
- `CHECK (effective_to IS NULL OR effective_to > effective_from)`
- `CREATE UNIQUE INDEX uq_device_assignments_active ON device_assignments (device_id) WHERE effective_to IS NULL;`
- `INDEX idx_device_assignments_device (device_id, effective_from DESC)`
- `INDEX idx_device_assignments_department (department_id, effective_from DESC)`

Rules:

1. Reassignment runs in one transaction: `UPDATE ... SET effective_to = now() WHERE
   device_id = :id AND effective_to IS NULL` then `INSERT` the new row. The partial
   unique index makes double-active states impossible.
2. No assignment row is ever updated except to close it; no row is deleted.
3. Scans read this table only at acceptance time, then store the result in
   `scans.department_id`.

---

## 9. `batches`

**Purpose:** department-scoped batch/lot identity supplied by the device or created by
users for comparison.

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | PK |
| `department_id` | `uuid` | no | — | FK → `departments(id)` `ON DELETE RESTRICT` |
| `batch_code` | `varchar(64)` | no | — | As supplied, e.g. `BATCH-2026-001` |
| `lot_code` | `varchar(64)` | yes | `NULL` | Optional lot, e.g. `LOT-A` |
| `variety` | `varchar(120)` | yes | `NULL` | Pending decision on whether variety is required |
| `created_at` | `timestamptz` | no | `now()` | |

Constraints and indexes:

- `PRIMARY KEY (id)`
- `CREATE UNIQUE INDEX uq_batches_dept_code_lot
   ON batches (department_id, batch_code, lot_code) NULLS NOT DISTINCT;`
  (PostgreSQL 15+; on older servers use two partial unique indexes — one `WHERE
  lot_code IS NULL`, one `WHERE lot_code IS NOT NULL`.)
- `INDEX idx_batches_department (department_id, batch_code)`

Notes: the same batch code may exist in two departments as separate rows — that is
intentional, since comparison and analytics never cross departments. Device
reassignment does not move batches.

---

## 10. `scans`

**Purpose:** one accepted device analysis submission and its lifecycle.

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | PK; used as the server scan ID |
| `device_id` | `uuid` | no | — | FK → `devices(id)` `ON DELETE RESTRICT`; from the authenticated token |
| `department_id` | `uuid` | no | — | FK → `departments(id)` `ON DELETE RESTRICT`; **acceptance snapshot** |
| `client_scan_id` | `varchar(128)` | no | — | Device-generated stable ID |
| `schema_version` | `varchar(16)` | no | — | Payload schema version accepted at ingest |
| `sample_id` | `varchar(128)` | no | — | As supplied, e.g. `Sample-0038` |
| `batch_id` | `uuid` | yes | `NULL` | FK → `batches(id)` `ON DELETE SET NULL` |
| `batch_code` | `varchar(64)` | yes | `NULL` | Snapshot for display if the batch row changes |
| `lot_code` | `varchar(64)` | yes | `NULL` | Snapshot |
| `variety` | `varchar(120)` | yes | `NULL` | Snapshot |
| `analyzed_at` | `timestamptz` | no | — | Device-reported analysis time |
| `received_at` | `timestamptz` | no | `now()` | Server acceptance time |
| `finalized_at` | `timestamptz` | yes | `NULL` | Set on transition to `completed` |
| `processing_status` | `scan_processing_status` | no | `'received'` | See state machine |
| `quality_verdict` | `quality_verdict` | yes | `NULL` | Supplied by device; never derived |
| `ruleset_version` | `varchar(64)` | yes | `NULL` | e.g. `demo-v1`; never inferred |
| `certification_status` | `varchar(32)` | yes | `NULL` | e.g. `advisory_only`; display-only |
| `raw_payload` | `jsonb` | no | — | Exact accepted payload for traceability |
| `payload_sha256` | `char(64)` | no | — | Canonical hash for conflict detection |
| `failure_code` | `varchar(64)` | yes | `NULL` | Technical diagnostic |
| `failure_detail` | `text` | yes | `NULL` | Sanitised technical detail; never rendered raw to users |
| `created_at` | `timestamptz` | no | `now()` | |
| `updated_at` | `timestamptz` | no | `now()` | |

Constraints and indexes:

- `PRIMARY KEY (id)`
- `UNIQUE (device_id, client_scan_id)` — idempotency key
- `CHECK (processing_status <> 'completed' OR finalized_at IS NOT NULL)`
- `CHECK (quality_verdict IS NULL OR quality_verdict IN (...))` — implicit via enum
- `CHECK (analyzed_at <= received_at + interval '1 hour')` — sanity guard against a
  device clock far in the future (threshold provisional)
- `CREATE INDEX idx_scans_department_completed
   ON scans (department_id, analyzed_at DESC) WHERE processing_status = 'completed';`
  — the latest-scan and history index
- `CREATE INDEX idx_scans_department_received ON scans (department_id, received_at DESC);`
- `CREATE INDEX idx_scans_batch ON scans (department_id, batch_id) WHERE batch_id IS NOT NULL;`
- `CREATE INDEX idx_scans_device ON scans (device_id, received_at DESC);`
- `CREATE INDEX idx_scans_status ON scans (processing_status) WHERE processing_status <> 'completed';`
- Optional `GIN (raw_payload jsonb_path_ops)` only if payload queries are required
  later; not created by default.

Rules:

- `department_id` is written once from the active assignment and is never updated.
  Any code that tries to change it is a defect.
- `raw_payload` is immutable; a correction creates a new scan, not an edit.
- `quality_verdict` is populated from the device's evaluation on finalize and is not
  recalculated by the portal (SOR §8).
- Only `processing_status = 'completed'` scans are eligible for latest/history/
  analytics/comparison/report access.

Retention: retained per DR-013. Never cascade-deleted from device or department
deletion while referenced.

---

## 11. `measurements`

**Purpose:** normalised, queryable measurement values with their basis.

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | PK |
| `scan_id` | `uuid` | no | — | FK → `scans(id)` `ON DELETE CASCADE` |
| `metric_code` | `varchar(64)` | no | — | Stable code, e.g. `head_rice`, `big_broken`, `avg_length_mm` |
| `metric_label` | `varchar(120)` | yes | `NULL` | Device-supplied display name |
| `value` | `numeric(14,4)` | no | — | Never stored as float |
| `unit` | `varchar(24)` | no | — | `percent`, `mm`, `ratio`, `count`, `gram` |
| `basis` | `measurement_basis` | no | — | See enum |
| `is_estimated` | `boolean` | no | — | `true` for optical estimates; must agree with basis |
| `source_path` | `text` | yes | `NULL` | JSON path in `raw_payload`, e.g. `analysis.head_rice.estimated_mass_percent` |
| `created_at` | `timestamptz` | no | `now()` | |

Constraints and indexes:

- `PRIMARY KEY (id)`
- `UNIQUE (scan_id, metric_code, basis)` — count and estimated-mass rows coexist
- `CHECK (value >= 0)`
- `CHECK (is_estimated = true) OR basis IN ('physical_mass_percent','physical_mass_grams','count')`
  — an unestimated value cannot be an optical percentage; refine with the device team
- `CHECK (basis <> 'count_percent' OR unit = 'percent')`
- `CHECK (basis <> 'estimated_mass_percent' OR (unit = 'percent' AND is_estimated))`
- `CHECK (basis <> 'physical_mass_percent' OR unit = 'percent')`
- `CHECK (basis <> 'physical_mass_grams' OR unit = 'gram')`
- `CHECK (basis <> 'dimension' OR unit = 'mm')`
- `INDEX idx_measurements_scan (scan_id)`
- `INDEX idx_measurements_metric (metric_code, basis)`

Notes: unknown device metrics are stored with `basis = 'other'` and a descriptive
`metric_label`; the schema does not need a migration per new metric. Aggregations must
group by `metric_code` **and** `basis`.

---

## 12. `quality_evaluations`

**Purpose:** the device's per-parameter evaluation, stored verbatim for display.

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | PK |
| `scan_id` | `uuid` | no | — | FK → `scans(id)` `ON DELETE CASCADE` |
| `parameter_code` | `varchar(64)` | no | — | e.g. `head_rice` |
| `basis` | `measurement_basis` | no | — | The basis the verdict was evaluated against |
| `measured_value` | `numeric(14,4)` | yes | `NULL` | Null when the device supplied only a status |
| `threshold_value` | `numeric(14,4)` | yes | `NULL` | As supplied; not interpreted |
| `comparison_operator` | `varchar(8)` | yes | `NULL` | Stored token: `gte`,`lte`,`gt`,`lt`,`eq` |
| `source_limit_text` | `varchar(120)` | yes | `NULL` | Verbatim, e.g. `Min 75.00%` / `Max 15.00%` |
| `status` | `quality_verdict` | no | — | Source verdict for this parameter |
| `ruleset_version` | `varchar(64)` | yes | `NULL` | |
| `created_at` | `timestamptz` | no | `now()` | |

Constraints and indexes:

- `PRIMARY KEY (id)`
- `UNIQUE (scan_id, parameter_code, basis)`
- `INDEX idx_quality_evaluations_scan (scan_id)`
- `INDEX idx_quality_evaluations_status (status)`

Notes: the portal never evaluates `measured_value` against `threshold_value`. These
columns exist so the UI can show what the device reported and against what stated
limit, without claiming statutory meaning.

---

## 13. `age_results`

**Purpose:** device-supplied rice-age output with full provenance. Optional per scan.

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | PK |
| `scan_id` | `uuid` | no | — | FK → `scans(id)` `ON DELETE CASCADE`; **UNIQUE** |
| `age_value_months` | `numeric(6,2)` | yes | `NULL` | Scalar age, when supplied |
| `age_min_months` | `numeric(6,2)` | yes | `NULL` | Lower bound of a range (e.g. 8 for "8-10 Months") |
| `age_max_months` | `numeric(6,2)` | yes | `NULL` | Upper bound (e.g. 10) |
| `age_category` | `varchar(64)` | yes | `NULL` | Category/label as supplied, e.g. `8-10 Months`, `Above 1 Year` |
| `proportion_percent` | `numeric(5,2)` | yes | `NULL` | Share of sample in this bucket (certificate shows `100%`) |
| `unit` | `varchar(24)` | yes | `NULL` | `months` when a numeric range is present |
| `method` | `varchar(64)` | yes | `NULL` | As reported, e.g. `biochemical_colour` |
| `model_version` | `varchar(64)` | yes | `NULL` | Required for comparisons; pending decision |
| `confidence` | `numeric(5,2)` | yes | `NULL` | Only when the device defines its semantics |
| `validation_status` | `age_validation_status` | yes | `NULL` | Provenance of validation |
| `raw_value` | `text` | yes | `NULL` | Verbatim device string for traceability |
| `created_at` | `timestamptz` | no | `now()` | |

Constraints and indexes:

- `PRIMARY KEY (id)`
- `UNIQUE (scan_id)` — at most one age result per scan
- `CHECK (age_min_months IS NULL OR age_min_months >= 0)`
- `CHECK (age_max_months IS NULL OR age_max_months >= 0)`
- `CHECK (age_min_months IS NULL OR age_max_months IS NULL OR age_max_months >= age_min_months)`
- `CHECK (age_value_months IS NOT NULL OR age_min_months IS NOT NULL
          OR age_max_months IS NOT NULL OR age_category IS NOT NULL)`
  — a row must carry real information; `0` is never a placeholder
- `CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 100))`

Notes:

- **No row** means "no age result supplied" and is rendered as "Not available". This
  is preferred over a row full of nulls; both are readable, but absence is clearer.
- A range and a scalar can coexist when the device supplies both; the UI prefers the
  scalar and shows the range as context.
- `proportion_percent` supports the certificate's "8-10 Months (100%)" form.
- Comparisons must group by `method` + `model_version`; mixing is a UI/comparison
  warning, enforced in the service layer.

---

## 14. `scan_files`

**Purpose:** metadata for private stored attachments.

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | PK |
| `scan_id` | `uuid` | no | — | FK → `scans(id)` `ON DELETE CASCADE` |
| `role` | `scan_file_role` | no | — | `report_pdf` \| `bottom_image` \| `top_image` \| `other` |
| `storage_backend` | `varchar(16)` | no | — | `local` \| `s3` |
| `storage_key` | `text` | no | — | Opaque key; never a URL |
| `original_filename` | `varchar(255)` | no | — | Sanitised for display only |
| `mime_type` | `varchar(127)` | no | — | Validated from magic bytes |
| `size_bytes` | `bigint` | no | — | `CHECK (size_bytes > 0)` |
| `sha256` | `char(64)` | no | — | Integrity + duplicate detection |
| `width_px` | `integer` | yes | `NULL` | Images only |
| `height_px` | `integer` | yes | `NULL` | Images only |
| `upload_status` | `upload_status` | no | `'pending'` | `pending` → `uploaded` → `verified` \| `rejected` |
| `verified_at` | `timestamptz` | yes | `NULL` | |
| `created_at` | `timestamptz` | no | `now()` | |
| `updated_at` | `timestamptz` | no | `now()` | |

Constraints and indexes:

- `PRIMARY KEY (id)`
- `UNIQUE (storage_key)`
- `CREATE UNIQUE INDEX uq_scan_files_fixed_role
   ON scan_files (scan_id, role) WHERE role <> 'other';`
- `INDEX idx_scan_files_scan (scan_id)`
- `INDEX idx_scan_files_status (upload_status) WHERE upload_status <> 'verified';`
- `CHECK (role IN ('report_pdf') OR mime_type <> 'application/pdf')` is **not**
  applied — role↔MIME pairing is validated in the service layer where the allowlist
  lives (still pending DR-006).

Notes: no public URLs are stored anywhere in this table. Access always flows through
the API after a department check.

---

## 15. `upload_attempts`

**Purpose:** operational trace of prepare/upload/verify steps for diagnostics and
retry reasoning.

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | PK |
| `scan_id` | `uuid` | no | — | FK → `scans(id)` `ON DELETE CASCADE` |
| `scan_file_id` | `uuid` | yes | `NULL` | FK → `scan_files(id)` `ON DELETE SET NULL` |
| `role` | `scan_file_role` | no | — | |
| `stage` | `varchar(16)` | no | — | `prepare` \| `upload` \| `verify` |
| `status` | `varchar(16)` | no | — | `started` \| `succeeded` \| `failed` |
| `diagnostic_code` | `varchar(64)` | yes | `NULL` | Machine-readable cause |
| `detail` | `text` | yes | `NULL` | Sanitised technical detail |
| `created_at` | `timestamptz` | no | `now()` | |

Constraints and indexes:

- `PRIMARY KEY (id)`
- `INDEX idx_upload_attempts_scan (scan_id, created_at DESC)`

Retention: 90 days (provisional); not a business record.

---

## 16. `notifications`

**Purpose:** in-portal events, deduplicated per scan/event.

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | PK |
| `department_id` | `uuid` | no | — | FK → `departments(id)` `ON DELETE RESTRICT`; recipient scope |
| `scan_id` | `uuid` | yes | `NULL` | FK → `scans(id)` `ON DELETE SET NULL` |
| `event_type` | `notification_event_type` | no | — | |
| `event_key` | `varchar(160)` | no | — | Deterministic, e.g. `scan_completed:{scan_id}` |
| `severity` | `notification_severity` | no | `'info'` | |
| `title` | `varchar(200)` | no | — | |
| `body` | `text` | yes | `NULL` | Advisory wording preserved |
| `created_at` | `timestamptz` | no | `now()` | |

Constraints and indexes:

- `PRIMARY KEY (id)`
- `UNIQUE (event_key)` — retries cannot duplicate an alert
- `INDEX idx_notifications_department (department_id, created_at DESC)`
- `INDEX idx_notifications_scan (scan_id)`

Notes: `event_key` is built from stable identifiers, never from timestamps or random
values. A quality flag never uses the same key as a completion event.

---

## 17. `notification_recipients`

**Purpose:** per-user delivery and read state.

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | PK |
| `notification_id` | `uuid` | no | — | FK → `notifications(id)` `ON DELETE CASCADE` |
| `user_id` | `uuid` | no | — | FK → `users(id)` `ON DELETE CASCADE` |
| `read_at` | `timestamptz` | yes | `NULL` | `NULL` = unread |
| `created_at` | `timestamptz` | no | `now()` | |

Constraints and indexes:

- `PRIMARY KEY (id)`
- `UNIQUE (notification_id, user_id)`
- `INDEX idx_notification_recipients_unread
   ON notification_recipients (user_id, created_at DESC) WHERE read_at IS NULL;`

Notes: recipients are resolved at event creation from active memberships of the
notification's department; adding a user later does not retroactively deliver old
alerts (documented behaviour, not an oversight).

---

## 18. `audit_logs`

**Purpose:** append-only record of administrative and security-sensitive actions.

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | PK |
| `occurred_at` | `timestamptz` | no | `now()` | |
| `actor_type` | `audit_actor_type` | no | — | |
| `actor_user_id` | `uuid` | yes | `NULL` | FK → `users(id)` `ON DELETE SET NULL` |
| `actor_device_id` | `uuid` | yes | `NULL` | FK → `devices(id)` `ON DELETE SET NULL` |
| `department_id` | `uuid` | yes | `NULL` | FK → `departments(id)` `ON DELETE SET NULL`; scope at action time |
| `action` | `varchar(64)` | no | — | Namespaced, e.g. `device.reassigned`, `auth.login_failed` |
| `target_type` | `varchar(64)` | yes | `NULL` | e.g. `scan`, `user`, `device` |
| `target_id` | `uuid` | yes | `NULL` | |
| `ip_address` | `inet` | yes | `NULL` | |
| `user_agent` | `text` | yes | `NULL` | |
| `request_id` | `varchar(64)` | yes | `NULL` | Correlates with application logs |
| `metadata` | `jsonb` | no | `'{}'::jsonb` | Structured before/after, reason, department IDs |

Constraints and indexes:

- `PRIMARY KEY (id)`
- `CHECK (actor_type <> 'user' OR actor_user_id IS NOT NULL)`
- `CHECK (actor_type <> 'device' OR actor_device_id IS NOT NULL)`
- `INDEX idx_audit_logs_occurred (occurred_at DESC)`
- `INDEX idx_audit_logs_department (department_id, occurred_at DESC)`
- `INDEX idx_audit_logs_actor (actor_user_id, occurred_at DESC)`
- `INDEX idx_audit_logs_target (target_type, target_id)`

Rules: the application database role has `INSERT`/`SELECT` only on this table (no
`UPDATE`/`DELETE`). No FK cascades remove audit rows. Retention is a policy decision
(DR-013), expected to be longer than scan retention.

Minimum audited actions: login success/failure, logout, session revocation, user
create/update/deactivate, membership change, department create/update/deactivate,
device register/suspend/retire, credential issue/rotate/revoke, device reassignment,
super-admin cross-department read, report download, verdict correction.

---

## 19. Cross-cutting queries and index justification

| Query | Index used |
| --- | --- |
| Latest completed scan for a department | `idx_scans_department_completed (department_id, analyzed_at DESC) WHERE completed` |
| Paginated history with filters | Same index; batch filter narrows with `idx_scans_batch` |
| Scan detail by ID with department check | PK + `WHERE department_id = :caller` |
| Analytics over a period | `idx_scans_department_completed` then `measurements` by `scan_id` |
| Device list for a department | `uq_device_assignments_active` + `idx_device_assignments_department` |
| Assignment history | `idx_device_assignments_device` |
| Unread notification count | `idx_notification_recipients_unread` |
| Scan status polling | PK lookup (device already knows the scan ID) |
| Audit review | `idx_audit_logs_occurred` / `idx_audit_logs_department` |

---

## 20. Retention summary

| Table | Proposed retention | Status |
| --- | --- | --- |
| `scans`, `measurements`, `quality_evaluations`, `age_results`, `scan_files` | Per stakeholder policy | Pending DR-013 |
| `raw_payload` | Same as scan | Pending DR-013 |
| `notifications`, `notification_recipients` | 12 months | Provisional |
| `upload_attempts` | 90 days | Provisional |
| `user_sessions` | 30 days past expiry | Provisional |
| `audit_logs` | Minimum 24 months, likely longer | Pending DR-013 |
| `device_assignments`, `device_credentials` | Life of device + audit period | Provisional |

No automatic deletion is implemented until the retention decision is signed off.

---

## 21. Open schema-affecting decisions

| Decision | Effect if changed |
| --- | --- |
| DR-001/002/003 — age shape, unit, confidence semantics | `age_results` columns may be simplified or extended |
| DR-004 — final device payload | Which metrics are standardised in `measurements` |
| DR-005/006 — size/format limits | Validation only, not schema |
| DR-007 — mandatory attachments | Service-level policy; no schema change |
| DR-008/009 — verdict rules and priority | `quality_evaluations` may need a `priority`/`rule_ref` column |
| DR-013 — retention | Lifecycle jobs only |
| DR-019 — Department Admin user management | Nothing in schema; authorization only |
| DR-020 — comparison rules | Possibly a persisted comparison snapshot; not needed for MVP |

---

## 22. Physical implementation notes (Phase 2)

The initial migration is `backend/migrations/versions/0001_initial_schema.py`. Deliberate
differences from the logical text above:

1. **Case-insensitive email/code without `citext`.** `users` and `departments` use
   `lower(...)` expression unique indexes instead of the `citext` extension, so the
   schema does not require an extension the deployment role may not be allowed to
   create. Application code still normalises email to lowercase for lookup.
2. **Batch uniqueness.** `NULLS NOT DISTINCT` is replaced by two partial unique indexes
   (`... WHERE lot_code IS NULL` and `... WHERE lot_code IS NOT NULL`), which behave
   identically and work on PostgreSQL 13+.
3. **Enums are created explicitly** at the top of the migration (`CREATE TYPE`) and
   dropped after the tables on downgrade, so the cycle is deterministic.
4. **`audit_logs.metadata`** keeps its documented column name; the ORM attribute is
   `AuditLog.meta` because `metadata` is reserved on declarative classes.
5. **UUID defaults.** The application generates UUIDv4 values; the migration also sets
   `gen_random_uuid()` (built into PostgreSQL 13+) as a database-side fallback.
6. **Audit immutability** is enforced by convention and the service layer (insert-only,
   no update/delete endpoints). The runtime role restriction described in §18 remains a
   deployment task, because development uses a single owner role.
