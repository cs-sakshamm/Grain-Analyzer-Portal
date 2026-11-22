# Frontend Architecture — Rice Age Portal

**Status:** Phase 1 conventions. Only an application shell is implemented; the seven
departmental modules are Phase 2+ work.

References: PRD §3 (information architecture), §4 (Latest Scan UX), §9 (UX
standards), SOR §8 (dashboard and interface requirements), and the APSCSCL sample
report for data density and terminology.

---

## 1. Principles

1. **Data-first, institutional, calm.** Neutral surfaces, restrained colour, monospace
   for identifiers, tabular numbers for measurements. Colour never carries meaning
   alone.
2. **Bases and provenance are always visible.** Every percentage sits next to its
   basis (`count %`, `est. mass %`, `physical mass %`); every age value carries its
   unit/model where supplied.
3. **Advisory framing is permanent.** Prototype/advisory disclaimers ship with the
   data, not in a dismissible toast.
4. **Never fabricate state.** Missing age → "Not available". Missing file → explicit
   unavailable state. Processing scan → activity indicator, never a fake latest result.
5. **Server is the access boundary.** Role-aware routing is UX only.

---

## 2. Directory structure and responsibilities

```text
frontend/
├── src/
│   ├── app/                 App composition: providers, router, error boundary
│   ├── components/          Cross-feature primitives (Button, Card, MetricCard,
│   │                        StatusBadge, DataTable, EmptyState, ErrorState, Skeleton)
│   ├── features/
│   │   ├── auth/            Login form, session context, guards
│   │   ├── scans/           Latest scan, history, scan detail, evidence viewer
│   │   ├── analytics/       Quality analytics charts and filters
│   │   ├── age/             Rice age views and unavailable state
│   │   ├── reports/         Report list, preview, download actions
│   │   ├── batches/         Batch comparison table and comparability warnings
│   │   ├── notifications/   Alert inbox, unread badge
│   │   └── admin/           Departments, users, devices, assignments, audit
│   ├── layouts/             AppShell, AdminLayout, AuthLayout
│   ├── pages/               Thin route entry points composing features
│   ├── hooks/               Shared hooks (useDepartment, usePagination, useDebounce)
│   ├── services/            Typed API client, per-domain query modules
│   ├── lib/                 Formatting, basis labels, guards, design tokens, cn()
│   ├── types/               Generated/shared API types
│   └── routes/              Route definitions and lazy loading
├── public/
└── package.json
```

Feature folder contract: `components/`, `hooks/`, `api.ts`, `types.ts`, `schemas.ts`.
A feature may import from `components/`, `lib/`, `services/`, `types/` — never from
another feature's internals. Cross-feature reuse is promoted to `components/`.

---

## 3. Routing

| Path | Route | Access |
| --- | --- | --- |
| `/login` | Login | Public (authenticated users redirect to `/`) |
| `/` | Dashboard / Latest Scan | Any authenticated user |
| `/scans` | Scan History | Any authenticated user |
| `/scans/:scanId` | Scan Detail | Any authenticated user (scoped) |
| `/analytics` | Quality Analytics | Any authenticated user |
| `/rice-age` | Rice Age | Any authenticated user |
| `/reports` | Reports | Any authenticated user |
| `/batches/compare` | Batch Comparison | Any authenticated user |
| `/notifications` | Notifications | Any authenticated user |
| `/admin` | Admin overview | `super_admin`, `department_admin` |
| `/admin/departments` | Departments | `super_admin` |
| `/admin/users` | Users & memberships | `super_admin`, `department_admin` (own department) |
| `/admin/devices` | Devices & assignments | `super_admin` (full), `department_admin` (read-only own department) |
| `/admin/audit` | Audit log | `super_admin` |
| `/403` | Forbidden | Any |
| `*` | Not Found | Any |

Implementation notes:

- Route definitions live in `src/routes/`; each route is lazy-loaded and wrapped by
  `AppShell` or `AdminLayout`.
- Guards (`RequireAuth`, `RequireRole`) redirect unauthenticated users to `/login`
  with a safe return path, and render the forbidden state without flashing protected
  content.
- Admin navigation items are filtered by role, but the API still authorizes.
- The department context is always visible in the header for multi-membership and
  super-admin users.

---

## 4. Authentication flow

```text
Login form (React Hook Form + Zod)
  → POST /api/v1/auth/login
  → access token kept in memory (never localStorage)
  → refresh token in HttpOnly, Secure, SameSite=Strict cookie
  → session context: { user, roles, memberships, activeDepartment }
App boot
  → attempt refresh (cookie) → hydrate session or land on /login
401 handling
  → single-flight refresh → retry original request once
  → refresh failure → clear session, redirect to /login, preserve intended path
Logout
  → POST /api/v1/auth/logout (revokes session) → clear memory + redirect
```

Invariants:

- No token in `localStorage`/`sessionStorage`; no token in URLs.
- Role/scope changes invalidate cached queries (`queryClient.clear()`).
- The UI never trusts a cached `user` object for authorization decisions that the API
  would reject; a 403 renders the forbidden state, it does not retry blindly.
- Public self-registration is excluded; accounts are created by administrators.

---

## 5. Role-aware layout and navigation

- **AppShell**: brand + department indicator, primary navigation, notification badge,
  account menu, refresh/staleness indicator for the latest scan.
- **AdminLayout**: secondary navigation for departments, users, devices, audit.
- Roles:
  - `department_user` — dashboard, history, analytics, rice age, reports, batches,
    notifications.
  - `department_admin` — the above plus own-department user management and read-only
    device visibility (final permission policy pending DR-019).
  - `super_admin` — all of the above plus departments, device registry, assignments,
    credential rotation, audit.
- Navigation is generated from a single route metadata table, so adding a module adds
  one entry with its permitted roles.

---

## 6. API service layer

```text
src/services/apiClient.ts      fetch wrapper: base URL, auth header, 401 refresh,
                               error envelope → ApiError, request IDs
src/services/queryKeys.ts      central query-key factory (scope-aware)
src/features/<f>/api.ts        typed calls for that feature
src/types/api.ts               response types mirroring docs/api/API_CONTRACT.md
```

Rules:

- Components never call `fetch` directly; they call feature API functions through
  TanStack Query hooks.
- Every external payload is parsed with a Zod schema at the boundary; parse failures
  surface as a controlled "unexpected response" error, not a render crash.
- Query keys include the department/scope so switching department cannot serve cached
  another-department data.
- Latest scan uses `refetchInterval` (baseline 10 s) with `refetchIntervalInBackground:
  false`; upgrade to SSE only if freshness targets require it.
- Mutations use `useMutation` with explicit invalidation of affected keys.

Recommended keys:

```ts
['scans', 'latest', departmentId]
['scans', 'list', departmentId, filters, page]
['scans', 'detail', scanId]
['analytics', 'quality', departmentId, filters]
['analytics', 'age', departmentId, filters]
['batches', 'compare', departmentId, batchIds]
['notifications', departmentId, { unreadOnly }]
['admin', 'devices', departmentId]
```

---

## 7. State management

| State | Owner |
| --- | --- |
| Server data (scans, analytics, admin lists) | TanStack Query cache |
| Session/user/roles | Auth context (react context) |
| URL-addressable filters, pagination, tabs | Router search params |
| Form state | React Hook Form |
| Transient UI (modals, image zoom) | Local component state |

No Redux/Zustand until a concrete need is demonstrated.

---

## 8. Forms and validation

- React Hook Form + Zod resolver; schemas in `schemas.ts` beside the feature.
- Server-side 422 detail maps onto field errors; unknown fields surface in a form-level
  alert.
- Admin mutations (create department, register device, reassign device, rotate
  credential) require explicit confirmation and show the audited consequence.
- File pickers validate declared type and size client-side as a convenience; the
  server remains authoritative.

---

## 9. Error, loading and empty states

| Situation | UI behaviour |
| --- | --- |
| Initial load | Skeletons matching final layout (no spinners over blank pages) |
| No completed scans | Descriptive empty state with next-step guidance; department context shown |
| Scan processing | Latest completed scan stays; separate "new scan processing" indicator |
| Upload/processing failure | Technical alert with device + submission reference; never styled as a quality rejection |
| No age result | "Not available" with method/model context; no zero-month value |
| Missing attachment | Explicit "not provided" per role; no broken image or public URL |
| Stale data | Last successful sync time + retry; dashboard copy distinguishes stale from empty |
| 403 / 404 | Non-disclosing forbidden/not-found page; no metadata leak |
| 5xx | Retry action with request ID for support |
| Session expiry | Re-authenticate without losing the intended in-portal destination |

Error surfaces use the backend envelope (`code`, `message`, `details`, `request_id`);
raw stack traces and internal identifiers are never rendered.

---

## 10. Dashboard and chart conventions

- **Metric cards**: value + unit + basis label + as-of timestamp. Basis is never
  omitted for percentages.
- **Verdict badges**: text plus icon plus colour, with the advisory label adjacent.
  `FLAG`, `PASS`, `INCONCLUSIVE`, `LAB CONFIRMATION` are distinct from processing
  states (`RECEIVED`, `AWAITING FILES`, `VERIFYING`, `COMPLETED`, `FAILED`).
- **Charts (Recharts)**:
  - One measurement basis per chart or series; incompatible bases are split into
    separate series/panels with an explicit note.
  - Axis labels include unit; the chart subtitle states filters and `n` (record count).
  - Age charts only include compatible model versions; mismatches are excluded and
    reported.
  - Trend lines over sparse data show points; no smoothing that implies precision.
  - Empty series render a no-data message rather than an empty grid.
  - Provide an accessible summary table or `aria-label` describing the trend.
- **Platen evidence**: bottom/primary and top/verification panels, each with label,
  capture timestamp where available, zoom, and an unavailable fallback. Alt text
  describes the panel, not the quality conclusion.
- **Report actions**: Preview (inline PDF), Download (signed, short-lived), Print
  (browser print of the original PDF). The UI states that the PDF is the original
  device output.

---

## 11. Responsive behaviour

| Breakpoint | Layout |
| --- | --- |
| ≥ 1280 px | Latest scan: metric cards row, evidence and parameter grid side by side |
| 768–1279 px | Evidence above parameter table; cards wrap to two columns |
| < 768 px | Single column, sticky verdict banner, report actions in a bottom bar, tables become horizontally scrollable with sticky first column |

Tables keep numeric alignment and never truncate units. Long identifiers wrap rather
than clip.

---

## 12. Design tokens

Defined once in `src/styles/index.css` as CSS custom properties and consumed through
Tailwind theme mappings:

| Token group | Intent |
| --- | --- |
| `--color-surface`, `--color-surface-muted`, `--color-border` | Neutral institutional surfaces |
| `--color-text`, `--color-text-muted` | Body and secondary text with AA contrast |
| `--color-brand`, `--color-brand-strong` | Institutional accent (headings, primary actions) |
| `--status-pass`, `--status-flag`, `--status-inconclusive`, `--status-lab` | Verdict colours, always paired with text |
| `--status-info`, `--status-danger` | Processing/technical states, distinct from quality |
| `--radius-sm/md/lg`, `--shadow-card` | Consistent card geometry |
| Typography scale | 12/14/16/20/24/30 px; identifiers in a mono stack |

Rules: no hex values in components; dark mode is not required in Phase 1 but tokens
must not assume a single theme; contrast is checked for text on tinted backgrounds.

---

## 13. Accessibility

- Target WCAG 2.2 AA for the portal shell and all Phase 2 views.
- Keyboard: all navigation, filters, image zoom, notifications and dialogs operable;
  visible focus rings; focus trapped in dialogs and restored on close.
- Semantic landmarks (`header`, `nav`, `main`), one `h1` per page, table headers with
  scopes.
- Status changes use `aria-live="polite"`; global errors use `role="alert"`.
- Images: descriptive alt text; decorative icons `aria-hidden`.
- Charts: adjacent summary text or data table.
- Colour never the sole signal (verdict text + icon + colour).
- Page titles reflect department and module.

---

## 14. Frontend testing

| Layer | Tool | Scope |
| --- | --- | --- |
| Pure logic | Vitest | Formatting, basis labels, comparability checks, guard predicates |
| Components | Vitest + Testing Library | States: loading, empty, error, unavailable age, verdict labels |
| Contract | Zod schema tests | Reject malformed API payloads |
| E2E (Phase 3+) | Playwright | Login, latest scan, download authorization, department isolation |

Phase 1 implements the pure-logic layer only; component and E2E suites are added as
the modules land.
