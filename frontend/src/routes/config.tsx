import { Navigate } from "react-router-dom";

import { ProtectedRoute, PublicOnlyRoute } from "@/features/auth/ProtectedRoute";
import { AppShell } from "@/layouts/AppShell";
import { AlertsPage } from "@/pages/Alerts";
import { BatchComparisonPage } from "@/pages/BatchComparison";
import { LatestScanPage } from "@/pages/LatestScan";
import { LoginPage } from "@/pages/LoginPage";
import { NotFound } from "@/pages/NotFound";
import { QualityAnalyticsPage } from "@/pages/QualityAnalytics";
import { ReportsPage } from "@/pages/Reports";
import { RiceAgePage } from "@/pages/RiceAge";
import { ScanDetailPage } from "@/pages/ScanDetail";
import { ScanHistoryPage } from "@/pages/ScanHistory";
import { SystemStatusPage } from "@/pages/SystemStatus";
import { UnauthorizedPage } from "@/pages/UnauthorizedPage";

/**
 * Portal route table.
 *
 * `/` is the departmental application — the Latest Scan module — not a placeholder.
 * Every module has its own path so direct navigation and refresh both work once the
 * SPA fallback serves index.html (Vite in development, nginx in production).
 *
 * Kept free of router construction so the configuration can be verified in tests
 * without a DOM.
 */
export const portalRoutes = [
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
          { index: true, element: <LatestScanPage /> },
          { path: "latest-scan", element: <Navigate to="/" replace /> },
          { path: "scan-history", element: <ScanHistoryPage /> },
          { path: "quality-analytics", element: <QualityAnalyticsPage /> },
          { path: "rice-age", element: <RiceAgePage /> },
          { path: "reports", element: <ReportsPage /> },
          { path: "batch-comparison", element: <BatchComparisonPage /> },
          { path: "alerts", element: <AlertsPage /> },
          { path: "scans/:scanId", element: <ScanDetailPage /> },
          { path: "status", element: <SystemStatusPage /> },
          { path: "unauthorized", element: <UnauthorizedPage /> },
          { path: "*", element: <NotFound /> },
        ],
      },
    ],
  },
];
