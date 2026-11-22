import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "@/features/auth/auth-context";

export function SessionLoader() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <p className="text-sm text-text-muted" role="status">
        Checking your session…
      </p>
    </div>
  );
}

/** Route guard for usability only; the backend remains the security boundary. */
export function ProtectedRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return <SessionLoader />;
  }
  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

export function PublicOnlyRoute({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  if (status === "loading") {
    return <SessionLoader />;
  }
  if (status === "authenticated") {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}
