import { createBrowserRouter } from "react-router-dom";

import { ProtectedRoute, PublicOnlyRoute } from "@/features/auth/ProtectedRoute";
import { AppShell } from "@/layouts/AppShell";
import { FoundationOverview } from "@/pages/FoundationOverview";
import { LoginPage } from "@/pages/LoginPage";
import { NotFound } from "@/pages/NotFound";
import { UnauthorizedPage } from "@/pages/UnauthorizedPage";

/**
 * Phase 2 route table: public sign-in plus the authenticated shell. Departmental
 * modules and the admin console arrive in later phases.
 */
export const router = createBrowserRouter([
  {
    path: "/login",
    element: (
      <PublicOnlyRoute>
        <LoginPage />
      </PublicOnlyRoute>
    ),
  },
  {
    path: "/",
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <FoundationOverview /> },
          { path: "unauthorized", element: <UnauthorizedPage /> },
          { path: "*", element: <NotFound /> },
        ],
      },
    ],
  },
]);
