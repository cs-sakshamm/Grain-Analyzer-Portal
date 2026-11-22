import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";

import { fetchHealth, fetchReadiness } from "@/services/health";

const modules = [
  { to: "/", label: "Latest Scan / Live View" },
  { to: "/scan-history", label: "Scan History" },
  { to: "/quality-analytics", label: "Quality Analytics" },
  { to: "/rice-age", label: "Rice Age" },
  { to: "/reports", label: "Reports" },
  { to: "/batch-comparison", label: "Batch Comparison" },
  { to: "/alerts", label: "Alerts & Notifications" },
];

function StatusPill({ state }: { state: "ok" | "pending" | "error" }) {
  const styles =
    state === "ok"
      ? "border-status-pass/30 bg-status-pass/10 text-status-pass"
      : state === "error"
        ? "border-status-flag/30 bg-status-flag/10 text-status-flag"
        : "border-border-subtle bg-surface-muted text-text-muted";

  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${styles}`}>
      {state === "ok" ? "Reachable" : state === "error" ? "Unavailable" : "Checking…"}
    </span>
  );
}

/**
 * Operational status view. The departmental modules live at their own routes; this page
 * keeps the live liveness/readiness checks reachable for operators and developers.
 */
export function SystemStatusPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, retry: 1 });
  const readiness = useQuery({
    queryKey: ["health", "ready"],
    queryFn: fetchReadiness,
    retry: false,
  });

  return (
    <div className="space-y-8">
      <section className="rounded-xl border border-border-subtle bg-surface p-6 shadow-card">
        <h1 className="text-xl font-semibold text-text">System status</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-text-muted">
          Live status of the running backend services. Departmental results are available
          from the modules below; this page only reports service reachability.
        </p>
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg border border-border-subtle p-4">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs font-medium uppercase tracking-wide text-text-muted">
                Backend API
              </p>
              <StatusPill
                state={health.isSuccess ? "ok" : health.isError ? "error" : "pending"}
              />
            </div>
            <p className="mt-2 text-sm text-text">
              {health.data
                ? `${health.data.service} · ${health.data.environment ?? "production"}`
                : "—"}
            </p>
          </div>
          <div className="rounded-lg border border-border-subtle p-4">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs font-medium uppercase tracking-wide text-text-muted">
                Database readiness
              </p>
              <StatusPill
                state={readiness.isSuccess ? "ok" : readiness.isError ? "error" : "pending"}
              />
            </div>
            <p className="mt-2 text-sm text-text">
              {readiness.isSuccess
                ? "PostgreSQL reachable"
                : readiness.isError
                  ? "Requires the database service"
                  : "—"}
            </p>
          </div>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="rounded-xl border border-border-subtle bg-surface p-6">
          <h2 className="text-base font-semibold text-text">Departmental modules</h2>
          <p className="mt-1 text-sm text-text-muted">
            Each module is a live, department-scoped view backed by the portal API.
          </p>
          <ul className="mt-4 divide-y divide-border-subtle">
            {modules.map((module) => (
              <li key={module.to} className="flex items-center justify-between gap-4 py-2.5">
                <NavLink to={module.to} className="text-sm text-text hover:text-brand">
                  {module.label}
                </NavLink>
                <span className="text-xs font-medium text-text-muted">Open</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-xl border border-border-subtle bg-surface p-6">
          <h2 className="text-base font-semibold text-text">Non-negotiable rules</h2>
          <ul className="mt-4 space-y-3 text-sm text-text-muted">
            <li>Department scope is enforced by the backend on every request.</li>
            <li>Device ownership comes from the authenticated assignment, never the payload.</li>
            <li>Only completed scans appear as the latest result.</li>
            <li>Missing rice age is shown as “Not available”, never as zero.</li>
            <li>Count and estimated-mass percentages are never blended.</li>
            <li>Reports remain the original device PDF, advisory only.</li>
          </ul>
        </div>
      </section>
    </div>
  );
}
