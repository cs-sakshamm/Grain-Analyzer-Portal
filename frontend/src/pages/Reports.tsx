import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth } from "@/features/auth/auth-context";
import { apiDownload, apiGet, errorMessage } from "@/services/apiClient";

interface ReportListingItem {
  scan_id: string;
  sample_id: string;
  batch_code: string | null;
  lot_code: string | null;
  analyzed_at: string;
  has_report: boolean;
  report_filename: string | null;
  age_available: boolean;
  quality_verdict: string | null;
  processing_status: string;
  device_uid: string | null;
}

function qualityVerdictClass(
  verdict: string | null
): string {
  if (!verdict) return "text-text-muted opacity-50";
  if (verdict === "pass") return "bg-green-100 text-green-800 text-xs font-medium rounded px-2 py-1";
  if (verdict === "flagged") return "bg-yellow-100 text-yellow-800 text-xs font-medium rounded px-2 py-1";
  if (verdict === "inconclusive") return "bg-blue-100 text-blue-800 text-xs font-medium rounded px-2 py-1";
  if (verdict === "lab_confirmation_required")
    return "bg-purple-100 text-purple-800 text-xs font-medium rounded px-2 py-1";
  return "text-text-muted";
}

function qualityVerdictText(verdict: string | null): string {
  if (!verdict) return "—";
  return verdict;
}

export function ReportsPage() {
  const { user } = useAuth();
  const [downloading, setDownloading] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  async function handleDownload(scanId: string, sampleId: string) {
    setDownloadError(null);
    setDownloading(scanId);
    try {
      await apiDownload(`/scans/${scanId}/report/download`, `${sampleId}-report.pdf`);
    } catch (downloadFailure) {
      setDownloadError(errorMessage(downloadFailure));
    } finally {
      setDownloading(null);
    }
  }

  const { data, isLoading, isError } = useQuery<ReportListingItem[]>({
    queryKey: ["reports"],
    queryFn: async () => {
      const result: { items: ReportListingItem[] } = await apiGet("/scans/analytics/reports");
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
      <div className="min-h-[500px] flex items-center justify-center">
        <div className="animate-spin rounded-full size-6 border-b-2 border-border-subtle"></div>
        <p className="ml-2 text-text-muted">Loading reports…</p>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="p-6 bg-surface rounded-lg">
        <p className="text-text-muted">No reports found</p>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="p-6 bg-surface rounded-lg">
        <p className="text-text-muted">No scans are available for this department yet.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Report table */}
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
                Report
              </th>
              <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                Age
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
            {data.map((report) => (
              <tr key={report.scan_id} className="border-y hover:bg-surface-muted/50">
                <td className="p-3">
                  <a href={`/scans/${report.scan_id}`} className="text-text hover:text-brand underline">
                    {report.sample_id}
                  </a>
                </td>
                <td className="p-3">{report.device_uid || "—"}</td>
                <td className="p-3">
                  {report.batch_code ? (
                    <>
                      {report.batch_code}
                      {report.lot_code && <span className="text-xs ml-2">LOT {report.lot_code}</span>}
                    </>
                  ) : (
                    <span className="text-text-muted opacity-50">—</span>
                  )}
                </td>
                <td className="p-3">
                  {report.has_report ? (
                    <span className="text-green-600 cursor-pointer">
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="size-3 mr-1"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M4 6h16M4 12h16M4 18h7"
                        />
                      </svg>
                      Available
                    </span>
                  ) : (
                    <span className="text-text-muted">—</span>
                  )}
                </td>
                <td className="p-3">
                  {report.age_available ? (
                    <span className="text-green-600">Yes</span>
                  ) : (
                    <span className="text-text-muted">No</span>
                  )}
                </td>
                <td className="p-3">
                  <span className={qualityVerdictClass(report.quality_verdict)}>
                    {qualityVerdictText(report.quality_verdict)}
                  </span>
                </td>
                <td className="p-3 text-right">
                  {report.has_report ? (
                    <button
                      type="button"
                      onClick={() => void handleDownload(report.scan_id, report.sample_id)}
                      disabled={downloading === report.scan_id}
                      className="text-sm text-brand underline cursor-pointer disabled:opacity-60"
                    >
                      {downloading === report.scan_id ? "Preparing…" : "Download"}
                    </button>
                  ) : (
                    <span className="text-sm text-text-muted">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {downloadError ? (
        <p role="alert" className="text-sm text-status-flag">
          {downloadError}
        </p>
      ) : null}

      {/* Advisory notice */}
      <div className="rounded-xl border border-border-subtle bg-surface p-4">
        <p className="text-sm text-text-muted">
          Advisory: Reports are original device PDFs for pre-inspection purposes only.
          Optical estimates are not statutory procurement measurements and are not a
          certification of rice quality.
        </p>
      </div>
    </div>
  );
}