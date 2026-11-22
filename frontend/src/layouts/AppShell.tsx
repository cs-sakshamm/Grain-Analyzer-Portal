import { ShieldCheck } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

const navigation = [{ to: "/", label: "Foundation" }];

export function AppShell() {
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

          <nav aria-label="Primary" className="flex items-center gap-1 md:ml-6">
            {navigation.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  [
                    "rounded-md px-3 py-1.5 text-sm transition-colors",
                    isActive
                      ? "bg-surface-muted font-medium text-brand-strong"
                      : "text-text-muted hover:text-text",
                  ].join(" ")
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <span className="ml-auto rounded-full border border-border-subtle bg-surface-muted px-3 py-1 text-xs font-medium text-text-muted">
            Phase 1 · foundation
          </span>
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
