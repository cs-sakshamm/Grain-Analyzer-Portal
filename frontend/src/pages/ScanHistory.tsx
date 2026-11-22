import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/auth-context";
import { useState } from "react";
import { apiGet } from "@/services/apiClient";

interface ScanHistoryRow {
  id: string;
  sample_id: string;
  batch_code: string | null;
  lot_code: string | null;
  variety: string | null;
  analyzed_at: string;
  received_at: string;
  processing_status: string;
  quality_verdict: string | null;
  device_uid: string | null;
  department_code: string | null;
}

interface ScanHistoryData {
  items: ScanHistoryRow[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

function verdictClassName(status: string | null): string {
  if (!status) return "text-text-muted opacity-50";
  if (status === "pass") return "bg-green-100 text-green-800 text-xs font-medium rounded px-2 py-1";
  if (status === "flagged") return "bg-yellow-100 text-yellow-800 text-xs font-medium rounded px-2 py-1";
  if (status === "inconclusive") return "bg-blue-100 text-blue-800 text-xs font-medium rounded px-2 py-1";
  if (status === "lab_confirmation_required")
    return "bg-purple-100 text-purple-800 text-xs font-medium rounded px-2 py-1";
  return "text-text-muted";
}

function verdictText(status: string | null): string {
  if (!status) return "—";
  return status;
}

function processingClassName(status: string): string {
  if (status === "completed") return "bg-green-100 text-green-800 text-xs font-medium rounded px-2 py-1";
  if (status === "received") return "bg-blue-100 text-blue-800 text-xs font-medium rounded px-2 py-1";
  if (status === "verifying") return "bg-yellow-100 text-yellow-800 text-xs font-medium rounded px-2 py-1";
  if (status === "failed") return "bg-red-100 text-red-800 text-xs font-medium rounded px-2 py-1";
  return "text-text-muted";
}

export function ScanHistoryPage() {
  const { user } = useAuth();
  const [filters, setFilters] = useState({
    batch_code: "",
    device_id: "",
    status: "",
    verdict: "",
    start_date: "",
    end_date: "",
  });

  const { data, isLoading, isError } = useQuery<ScanHistoryData>({
    queryKey: ["scan-history"],
    queryFn: async (): Promise<ScanHistoryData> => {
      const result: ScanHistoryData = await apiGet("/scans/history");
      return result;      return result;
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
        <p className="ml-2 text-text-muted">Loading scan history…</p>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="p-6 bg-surface rounded-lg">
        <p className="text-text-muted">No scans found</p>
      </div>
    );
  }

  const { items, total, page, per_page, pages } = data;

  return (
    <div className="space-y-4">
      {/* Filters panel */}
      <div className="rounded-xl border border-border-subtle bg-surface p-4">
        <p className="text-sm font-medium text-text-muted mb-3">Filters</p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-text-muted uppercase tracked wide block mb-1">Batch / Lot</label>
            <input
              type="text"
              value={filters.batch_code}
              onChange={(e) => setFilters({ ...filters, batch_code: e.target.value })}
              placeholder="Batch code"
              className="w-full rounded-md border border-border-subtle px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand"
            />
          </div>
          <div>
            <label className="text-xs text-text-muted uppercase tracked wide block mb-1">Device</label>
            <input
              type="text"
              value={filters.device_id}
              onChange={(e) => setFilters({ ...filters, device_id: e.target.value })}
              placeholder="Device UID"
              className="w-full rounded-md border border-border-subtle px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand"
            />
          </div>
          <div>
            <label className="text-xs text-text-muted uppercase tracked wide block mb-1">Processing Status</label>
            <select
              value={filters.status}
              onChange={(e) => setFilters({ ...filters, status: e.target.value })}
              className="w-full rounded-md border border-border-subtle px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand"
            >
              <option value="">All</option>
              <option value="received">Received</option>
              <option value="awaiting_files">Awaiting Files</option>
              <option value="verifying">Verifying</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-text-muted uppercase tracked wide block mb-1">Quality Verdict</label>
            <select
              value={filters.verdict}
              onChange={(e) => setFilters({ ...filters, verdict: e.target.value })}
              className="w-full rounded-md border border-border-subtle px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand"
            >
              <option value="">All</option>
              <option value="pass">Pass</option>
              <option value="flagged">Flagged</option>
              <option value="inconclusive">Inconclusive</option>
              <option value="lab_confirmation_required">Lab Confirmation Required</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-text-muted uppercase tracked wide block mb-1">Date Range</label>
            <div className="grid grid-cols-2 gap-2">
              <input
                type="date"
                value={filters.start_date || ""}
                onChange={(e) => setFilters({ ...filters, start_date: e.target.value || "" })}
                className="w-full rounded-md border border-border-subtle px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand"
              />
              <input
                type="date"
                value={filters.end_date || ""}
                onChange={(e) => setFilters({ ...filters, end_date: e.target.value || "" })}
                className="w-full rounded-md border border-border-subtle px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Scan table */}
      {items.length > 0 ? (
        <div className="rounded-xl border border-border-subtle bg-surface overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border-subtle">
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Sample ID
                </th>
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Device
                </th>
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Batch / Lot
                </th>
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Variety
                </th>
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Analyzed
                </th>
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Status
                </th>
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Verdict
                </th>
                <th className="text-right text-xs font-medium text-text-muted uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((scan) => (
                <tr
                  key={scan.id}
                  className="border-y hover:bg-surface-muted/50"
                >
                  <td className="p-3">
                    <a href={`/scans/${scan.id}`} className="text-text hover:text-brand underline">
                      {scan.sample_id}
                    </a>
                  </td>
                  <td className="p-3">{scan.device_uid || "—"}</td>
                  <td className="p-3">
                    {scan.batch_code ? (
                      <>
                        {scan.batch_code}
                        {scan.lot_code && <span className="text-xs ml-2">LOT {scan.lot_code}</span>}
                      </>
                    ) : (
                      <span className="text-text-muted opacity-50">—</span>
                    )}
                  </td>
                  <td className="p-3">{scan.variety || "—"}</td>
                  <td className="p-3">
                    <span className="text-xs text-text">
                      {new Date(scan.analyzed_at).toLocaleDateString()}
                    </span>
                  </td>
                  <td className="p-3">
                    <span className={processingClassName(scan.processing_status)}>
                      {scan.processing_status}
                    </span>
                  </td>
                  <td className="p-3">
                    <span className={verdictClassName(scan.quality_verdict)}>
                      {verdictText(scan.quality_verdict)}
                    </span>
                  </td>
                  <td className="p-3 text-right">
                    <a href={`/scans/${scan.id}`} className="text-sm text-brand underline cursor-pointer">
                      Details
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="p-6 bg-surface rounded-lg text-text-muted">
          <p>No scans match the applied filters.</p>
        </div>
      )}

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex justify-between items-center mt-4">
          <span className="text-sm text-text-muted">
            Showing {page * per_page} of {total} scans
          </span><div className="flex gap-2">
            {['<', '>'].map((dir, i) => (
              <button
                key={i}
                className="px-3 py-1 rounded-md border border-border-subtle hover:bg-surface-hover transition-colors text-sm"
                onClick={() => {}}
                disabled={i === 0 && page <= 1}
              >
                {dir === '<' ? 'Previous' : 'Next'}
              </button>
            ))}</div>
        </div>
      )}
    </div>
  );
}