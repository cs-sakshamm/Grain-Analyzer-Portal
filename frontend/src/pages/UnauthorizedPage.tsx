import { Link } from "react-router-dom";

export function UnauthorizedPage() {
  return (
    <div className="rounded-xl border border-border-subtle bg-surface p-8">
      <p className="text-xs font-medium uppercase tracking-wide text-text-muted">403</p>
      <h1 className="mt-2 text-xl font-semibold text-text">Not permitted</h1>
      <p className="mt-2 max-w-2xl text-sm text-text-muted">
        Your account does not have access to this area. Department data is restricted to
        the departments you belong to, and administrative actions require the relevant
        role. If you believe this is wrong, contact a super administrator.
      </p>
      <Link
        to="/"
        className="mt-6 inline-flex rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-strong"
      >
        Return to the portal
      </Link>
    </div>
  );
}
