import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";

import { navigation } from "@/layouts/navigation";
import { AlertsPage } from "@/pages/Alerts";
import { BatchComparisonPage } from "@/pages/BatchComparison";
import { LatestScanPage } from "@/pages/LatestScan";
import { QualityAnalyticsPage } from "@/pages/QualityAnalytics";
import { ReportsPage } from "@/pages/Reports";
import { RiceAgePage } from "@/pages/RiceAge";
import { ScanHistoryPage } from "@/pages/ScanHistory";
import { portalRoutes } from "@/routes/config";

type RouteEntry = {
  index?: boolean;
  path?: string;
  element?: ReactElement;
  children?: RouteEntry[];
};

const rootRoute = portalRoutes[1] as unknown as RouteEntry;
const shell = (rootRoute.children ?? [])[0];
const childRoutes = shell?.children ?? [];

function childByPath(path: string): RouteEntry | undefined {
  return childRoutes.find((route) => route.path === path);
}

describe("portal route table", () => {
  it("renders the Latest Scan module at the authenticated index", () => {
    const indexRoute = childRoutes.find((route) => route.index);
    expect(indexRoute).toBeDefined();
    expect(indexRoute?.element?.type).toBe(LatestScanPage);
  });

  it("exposes all seven departmental modules as their own paths", () => {
    const expected: Array<[string, unknown]> = [
      ["scan-history", ScanHistoryPage],
      ["quality-analytics", QualityAnalyticsPage],
      ["rice-age", RiceAgePage],
      ["reports", ReportsPage],
      ["batch-comparison", BatchComparisonPage],
      ["alerts", AlertsPage],
    ];

    for (const [path, component] of expected) {
      expect(childByPath(path)?.element?.type, `${path} route`).toBe(component);
    }
  });

  it("keeps the legacy latest-scan path as a redirect to the index", () => {
    const legacy = childByPath("latest-scan");
    expect(legacy).toBeDefined();
  });

  it("links every module in the primary navigation", () => {
    const targets = navigation.map((item) => item.to);
    expect(targets).toEqual([
      "/",
      "/scan-history",
      "/quality-analytics",
      "/rice-age",
      "/reports",
      "/batch-comparison",
      "/alerts",
      "/status",
    ]);
  });
});
