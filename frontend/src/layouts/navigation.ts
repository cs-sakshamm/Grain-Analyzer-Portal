/**
 * Primary portal navigation.
 *
 * All seven departmental modules are read surfaces available to every authenticated
 * portal user (department user, department admin, super admin). The backend scopes and
 * authorizes each request, so the shell never hides a module to fake a permission.
 */
export const navigation = [
  { to: "/", label: "Latest Scan", end: true },
  { to: "/scan-history", label: "Scan History", end: false },
  { to: "/quality-analytics", label: "Quality Analytics", end: false },
  { to: "/rice-age", label: "Rice Age", end: false },
  { to: "/reports", label: "Reports", end: false },
  { to: "/batch-comparison", label: "Batch Comparison", end: false },
  { to: "/alerts", label: "Alerts & Notifications", end: false },
  { to: "/status", label: "System status", end: false },
];
