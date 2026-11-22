import { createBrowserRouter } from "react-router-dom";

import { AppShell } from "@/layouts/AppShell";
import { FoundationOverview } from "@/pages/FoundationOverview";
import { NotFound } from "@/pages/NotFound";

/**
 * Phase 1 route table. The seven departmental modules and the admin area are added in
 * Phase 2 following docs/architecture/FRONTEND_ARCHITECTURE.md §3.
 */
export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <FoundationOverview /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
