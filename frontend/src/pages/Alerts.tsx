import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/auth-context";
import { apiGet } from "@/services/apiClient";

interface NotificationItem {
  id: string;
  event_type: string;
  severity: string;
  title: string;
  body: string | null;
  created_at: string;
  scan_id: string | null;
}

export function AlertsPage() {
  const { user } = useAuth();

  const { data, isLoading, isError } = useQuery<NotificationItem[]>({
    queryKey: ["alerts"],
    queryFn: async () => {
      const result: { items: NotificationItem[] } = await apiGet("/scans/notifications?unread_only=false");
      return result.items || [];
    },
    enabled: !!user,
    retry: 1,
  });

  if (!user) {
    return null;
  }

  if (isLoading) {
    return (
      <div className="min-h-[400px] flex items-center justify-center">
        <div className="animate-spin rounded-full size-6 border-b-2 border-border-subtle"></div>
        <p className="ml-2 text-text-muted">Loading alerts…</p>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="p-6 bg-surface rounded-lg">
        <p className="text-text-muted">No alerts found</p>
      </div>
    );
  }

  const notifications = data;

  // Severity colors
  const severityColors = {
    info: "bg-blue-100 text-blue-800",
    warning: "bg-yellow-100 text-yellow-800",
    critical: "bg-red-100 text-red-800",
  };

  return (
    <div className="space-y-4">
      {/* Notifications table */}
      <div className="rounded-xl border border-border-subtle bg-surface p-4">
        <p className="text-sm font-medium text-text-muted mb-3">Notifications</p>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border-subtle">
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider">Severity</th>
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider">Title</th>
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider">Date</th>
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider">Related Scan</th>
                <th className="text-right text-xs font-medium text-text-muted uppercase tracking-wider"></th>
              </tr>
            </thead>
            <tbody>
              {notifications.map((notif) => (
                <tr
                  key={notif.id}
                  className="border-y hover:bg-surface-muted/50"
                >
                  <td className="p-3">
                    <span
                      className={severityColors[notif.severity as keyof typeof severityColors] || severityColors.info}
                    >
                      {notif.severity}
                    </span>
                  </td>
                  <td className="p-3">{notif.title}</td>
                  <td className="p-3">
                    <span className="text-xs text-text-muted">
                      {new Date(notif.created_at).toLocaleDateString()}
                    </span>
                  </td>
                  <td className="p-3">
                    {notif.scan_id ? (
                      <a
                        href={`/scans/${notif.scan_id}`}
                        className="text-sm text-brand underline cursor-pointer"
                      >
                        Scan {notif.scan_id}
                      </a>
                    ) : (
                      <span className="text-text-muted opacity-50">—</span>
                    )}
                  </td>
                  <td className="p-3 text-right">
                    <span className="text-xs text-brand">Mark as read</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Summary */}
      <div className="rounded-xl border border-border-subtle bg-surface p-4">
        <p className="text-sm font-medium text-text-muted">Summary</p>
        <div className="grid grid-cols-3 gap-2">
          {["info", "warning", "critical"].map((severity) => {
            const count = notifications.filter(
              (n) => n.severity === severity
            ).length;
            if (count > 0) {
              return (
                <div
                  key={severity}
                  className="p-2 bg-surface rounded-lg border border-border-subtle text-center"
                >
                  <div className="text-2xl mb-1">{count}</div>
                  <div className="text-xs text-text-muted">{severity}</div>
                </div>
              );
            }
            return null;
          })}
        </div>
      </div>
    </div>
  );
}