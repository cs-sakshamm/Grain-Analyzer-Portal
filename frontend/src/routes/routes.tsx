import { createBrowserRouter } from "react-router-dom";

import { ProtectedRoute, PublicOnlyRoute } from "@/features/auth/ProtectedRoute";
import { AppShell } from "@/layouts/AppShell";
import { FoundationOverview } from "@/pages/FoundationOverview";
import { LoginPage } from "@/pages/LoginPage";
import { NotFound } from "@/pages/NotFound";
import { UnauthorizedPage } from "@/pages/UnauthorizedPage";
import { LatestScanPage } from "@/pages/LatestScan";
import { ScanHistoryPage } from "@/pages/ScanHistory";
import { QualityAnalyticsPage } from "@/pages/QualityAnalytics";
import { RiceAgePage } from "@/pages/RiceAge";
import { ReportsPage } from "@/pages/Reports";
import { BatchComparisonPage } from "@/pages/BatchComparison";
import { AlertsPage } from "@/pages/Alerts";

/** Phase 3 route table: authenticated portal with seven departmental modules. */

/** The root route renders the authenticated shell with department context. */
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
          { path: "latest-scan", element: <LatestScanPage /> },
          { path: "scan-history", element: <ScanHistoryPage /> },
          { path: "quality-analytics", element: <QualityAnalyticsPage /> },
          { path: "rice-age", element: <RiceAgePage /> },
          { path: "reports", element: <ReportsPage /> },
          { path: "batch-comparison", element: <BatchComparisonPage /> },
          { path: "alerts", element: <AlertsPage /> },
          { path: "*", element: <NotFound /> },
        ],
      },
    ],
  },
]);