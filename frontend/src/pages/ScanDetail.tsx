import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { apiDownload, apiGet, errorMessage } from "@/services/apiClient";

interface Measurement {
  metric_code: string;
  metric_label: string | null;
  value: string;
  unit: string;
  basis: string;
  is_estimated: boolean;
}

interface ScanDetailData {
  scan: {
    id: string;
    sample_id: string;
    batch_code: string | null;
    lot_code: string | null;
    variety: string | null;
    analyzed_at: string;
    received_at: string;
    finalized_at: string | null;
    processing_status: string;
    quality_verdict: string | null;
    ruleset_version: string | null;
    certification_status: string | null;
    device: { id: string | null; device_uid: string | null; friendly_name: string | null };
    department: { id: string | null; code: string | null; name: string | null };
    grain_count: number | null;
    measurements: Measurement[];
    age: {
      age_value_months: string | null;
      age_min_months: string | null;
      age_max_months: string | null;
      age_category: string | null;
      proportion_percent: string | null;
      unit: string | null;
      method: string | null;
      validation_status: string | null;
    } | null;
    files: {
      role: string;
      available: boolean;
      filename: string | null;
      size_bytes: number | null;
      mime_type: string | null;
    }[];
    advisory: string;
  };
  as_of: string;
}

/**
 * Scan detail for the deep links used by history, reports, rice age and alerts.
 * Super admins must name the department they are acting for, so the optional
 * `department_id` query parameter is forwarded unchanged.
 */
export function ScanDetailPage() {
  const { scanId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const departmentId = searchParams.get("department_id");
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const path = `/scans/${scanId}${departmentId ? `?department_id=${departmentId}` : ""}`;

  const { data, isLoading, isError, error } = useQuery<ScanDetailData>({
    queryKey: ["scan", scanId, departmentId],
    queryFn: () => apiGet<ScanDetailData>(path),
    enabled: Boolean(scanId),
    retry: 1,
  });

  async function handleDownload() {
    setDownloadError(null);
    setDownloading(true);
    try {
      await apiDownload(
        `/scans/${scanId}/report/download${departmentId ? `?department_id=${departmentId}` : ""}`,
        `${data?.scan.sample_id ?? "scan"}-report.pdf`,
      );
    } catch (downloadFailure) {
      setDownloadError(errorMessage(downloadFailure));
    } finally {
      setDownloading(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center gap-2">
        <div className="size-6 animate-spin rounded-full border-b-2 border-border-subtle" />
        <p className="text-sm text-text-muted">Loading scan…</p>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="space-y-3 rounded-xl border border-border-subtle bg-surface p-6">
        <p className="text-sm text-text-muted">
          {isError ? errorMessage(error) : "This scan is not available."}
        </p>
        <Link to="/scan-history" className="text-sm text-brand underline">
          Back to scan history
        </Link>
      </div>
    );
  }

  const scan = data.scan;
  const report = scan.files.find((file) => file.role === "report_pdf" && file.available);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text">{scan.sample_id}</h1>
          <p className="text-sm text-text-muted">
            {scan.department.name ?? "—"} · {scan.device.friendly_name ?? scan.device.device_uid ?? "—"}
          </p>
        </div>
        <Link to="/scan-history" className="text-sm text-brand underline">
          Back to scan history
        </Link>
      </div>

      <div className="grid gap-3 rounded-xl border border-border-subtle bg-surface p-4 sm:grid-cols-4">
        <div>
          <p className="text-xs uppercase tracking-wider text-text-muted">Status</p>
          <p className="text-sm text-text">{scan.processing_status}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wider text-text-muted">Verdict</p>
          <p className="text-sm text-text">{scan.quality_verdict ?? "—"}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wider text-text-muted">Batch / Lot</p>
          <p className="text-sm text-text">
            {scan.batch_code ?? "—"}
            {scan.lot_code ? ` · LOT ${scan.lot_code}` : ""}
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wider text-text-muted">Analyzed</p>
          <p className="text-sm text-text">{new Date(scan.analyzed_at).toLocaleString()}</p>
        </div>
      </div>

      <div className="rounded-xl border border-border-subtle bg-surface p-4">
        <p className="text-sm font-medium text-text">Measurements</p>
        {scan.measurements.length === 0 ? (
          <p className="mt-2 text-sm text-text-muted">No measurements were supplied for this scan.</p>
        ) : (
          <table className="mt-2 w-full">
            <thead>
              <tr className="border-b border-border-subtle">
                <th className="py-2 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                  Metric
                </th>
                <th className="py-2 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                  Value
                </th>
                <th className="py-2 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                  Unit
                </th>
                <th className="py-2 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                  Basis
                </th>
              </tr>
            </thead>
            <tbody>
              {scan.measurements.map((measurement) => (
                <tr key={`${measurement.metric_code}-${measurement.basis}`} className="border-y">
                  <td className="py-2 text-sm text-text">
                    {measurement.metric_label ?? measurement.metric_code}
                  </td>
                  <td className="py-2 text-sm text-text">{measurement.value}</td>
                  <td className="py-2 text-sm text-text">{measurement.unit}</td>
                  <td className="py-2 text-sm text-text">
                    {measurement.basis}
                    {measurement.is_estimated ? " (estimated)" : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="rounded-xl border border-border-subtle bg-surface p-4">
        <p className="text-sm font-medium text-text">Rice age (device supplied)</p>
        {scan.age && scan.age.age_value_months !== null ? (
          <p className="mt-2 text-sm text-text">
            {scan.age.age_value_months} {scan.age.unit ?? "months"}
            {scan.age.age_category ? ` · ${scan.age.age_category}` : ""}
            {scan.age.method ? ` · ${scan.age.method}` : ""}
          </p>
        ) : (
          <p className="mt-2 text-sm text-text-muted">Not available</p>
        )}
      </div>

      <div className="rounded-xl border border-border-subtle bg-surface p-4">
        <p className="text-sm font-medium text-text">Original report</p>
        {report ? (
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void handleDownload()}
              disabled={downloading}
              className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-brand-strong disabled:opacity-60"
            >
              {downloading ? "Preparing…" : "Download PDF"}
            </button>
            <span className="text-sm text-text-muted">{report.filename}</span>
          </div>
        ) : (
          <p className="mt-2 text-sm text-text-muted">
            No verified report is available for this scan.
          </p>
        )}
        {downloadError ? (
          <p role="alert" className="mt-2 text-sm text-status-flag">
            {downloadError}
          </p>
        ) : null}
      </div>

      <p className="text-xs text-text-muted">{scan.advisory}</p>
    </div>
  );
}
