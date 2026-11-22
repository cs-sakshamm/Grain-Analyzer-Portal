import { LogOut, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "@/features/auth/auth-context";
import { displayName, primaryMembership, roleLabel } from "@/features/auth/guards";
import { navigation } from "@/layouts/navigation";

export function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [signingOut, setSigningOut] = useState(false);
  const membership = primaryMembership(user);

  async function handleLogout() {
    setSigningOut(true);
    try {
      await logout();
      navigate("/login", { replace: true });
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-border-subtle bg-surface">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-4 px-6 py-4">
          <div className="flex items-center gap-3">
            <ShieldCheck aria-hidden="true" className="size-5 text-brand" />
            <div>
              <p className="text-sm font-semibold tracking-wide text-text">RICE AGE</p>
              <p className="text-xs text-text-muted">Departmental quality portal</p>
            </div>
          </div>

          <nav aria-label="Primary" className="flex flex-wrap items-center gap-1 md:ml-6">
            {navigation.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) => [
                  "rounded-md px-3 py-1.5 text-sm transition-colors",
                  isActive
                    ? "bg-surface-muted font-medium text-brand-strong"
                    : "text-text-muted hover:text-text",
                ].join(" ")}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-4">
            <div className="text-right">
              <p className="text-sm font-medium text-text">{displayName(user)}</p>
              <p className="text-xs text-text-muted">
                {user?.is_super_admin
                  ? "Super admin"
                  : membership
                    ? `${membership.department_code} · ${roleLabel(membership)}`
                    : "No department"}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void handleLogout()}
              disabled={signingOut}
              className="inline-flex items-center gap-1.5 rounded-md border border-border-subtle px-3 py-1.5 text-sm text-text-muted transition-colors hover:text-text disabled:opacity-60"
            >
              <LogOut aria-hidden="true" className="size-4" />
              {signingOut ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
        <Outlet />
      </main>

      <footer className="border-t border-border-subtle bg-surface">
        <p className="mx-auto w-full max-w-6xl px-6 py-4 text-xs text-text-muted">
          Advisory prototype. Optical results are estimates and are not statutory
          procurement measurements or a certification of rice quality.
        </p>
      </footer>
    </div>
  );
}
