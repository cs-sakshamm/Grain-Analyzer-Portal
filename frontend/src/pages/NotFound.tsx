import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <div className="rounded-xl border border-border-subtle bg-surface p-8">
      <p className="text-xs font-medium uppercase tracking-wide text-text-muted">404</p>
      <h1 className="mt-2 text-xl font-semibold text-text">Page not found</h1>
      <p className="mt-2 text-sm text-text-muted">
        The page does not exist, or you do not have access to it.
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
