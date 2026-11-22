import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/auth-context";
import { apiGet } from "@/services/apiClient";

interface Measurement {
  metric_code: string;
  metric_label: string | null;
  value: string;
  unit: string;
  basis: string;
  is_estimated: boolean;
}

interface AgeResult {
  age_value_months: string | null;
  age_min_months: string | null;
  age_max_months: string | null;
  age_category: string | null;
  proportion_percent: string | null;
  unit: string | null;
  method: string | null;
  validation_status: string | null;
}

interface LatestScanData {
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
    device: {
      id: string | null;
      device_uid: string | null;
      friendly_name: string | null;
    };
    department: {
      id: string | null;
      code: string | null;
      name: string | null;
    };
    grain_count: number | null;
    measurements: Measurement[];
    age: AgeResult | null;
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

export function LatestScanPage() {
  const { user } = useAuth();

  const { data, isLoading, isError } = useQuery<LatestScanData>({
    queryKey: ["latest-scan"],
    queryFn: async (): Promise<LatestScanData> => {
      const result: LatestScanData = await apiGet("/scans/latest");
      return result;
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
        <p className="ml-2 text-text-muted">Loading latest scan…</p>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="p-6 bg-surface rounded-lg">
        <p className="text-text-muted">No scan data available</p>
      </div>
    );
  }

  const scan = data.scan;

  // Processing status badges
  const statusBadges: Record<string, string> = {
    received: "bg-blue-100 text-blue-800 text-xs font-medium rounded px-2 py-1 Received",
    awaiting_files: "bg-blue-100 text-blue-800 text-xs font-medium rounded px-2 py-1 Awaiting Files",
    verifying: "bg-yellow-100 text-yellow-800 text-xs font-medium rounded px-2 py-1 Verifying",
    completed: "bg-green-100 text-green-800 text-xs font-medium rounded px-2 py-1 Completed",
    failed: "bg-red-100 text-red-800 text-xs font-medium rounded px-2 py-1 Failed",
  };

  // Quality verdict badges
  const verdictBadges: Record<string, string> = {
    pass: "bg-green-100 text-green-800 text-xs font-medium rounded px-2 py-1 Pass",
    flagged: "bg-yellow-100 text-yellow-800 text-xs font-medium rounded px-2 py-1 Flagged",
    inconclusive: "bg-blue-100 text-blue-800 text-xs font-medium rounded px-2 py-1 Inconclusive",
    "lab_confirmation_required": "bg-purple-100 text-purple-800 text-xs font-medium rounded px-2 py-1 Lab Confirmation Required",
  };

  return (
    <div className="space-y-4">
      {/* Scan metadata */}
      <div className="rounded-xl border border-border-subtle bg-surface p-4">
        <p className="text-sm font-medium text-text-muted">Scan Details</p>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <p className="text-xs text-text-muted uppercase tracking-wider">Sample ID</p>
            <p className="text-text">{scan.sample_id}</p>
          </div>
          <div>
            <p className="text-xs text-text-muted uppercase tracking-wider">Device</p>
            <p className="text-text">{scan.device?.friendly_name || "—"}</p>
          </div>
          <div>
            <p className="text-xs text-text-muted uppercase tracking-wider">Department</p>
            <p className="text-text">{scan.department?.name || "—"}</p>
          </div>
          <div>
            <p className="text-xs text-text-muted uppercase tracking-wider">Grain Count</p>
            <p className="text-text">{scan.grain_count || "—"}</p>
          </div>
        </div>
      </div>

      {/* Rice Age Result */}
      {scan.age && scan.age.age_value_months !== null && (
        <div className="mt-4 p-4 bg-surface rounded-xl border border-border-subtle">
          <p className="text-sm text-text-muted">Rice Age</p>
          <p className="text-2xl font-semibold text-text">
            {scan.age.age_value_months} {scan.age.unit || "months"}
          </p>
          {scan.age.age_category && (
            <p className="text-sm text-text-muted">Category: {scan.age.age_category}</p>
          )}
          {scan.age.proportion_percent && (
            <p className="text-sm text-text-muted">Proportion: {scan.age.proportion_percent}%</p>
          )}
          <p className="text-xs text-text-muted">{scan.age.method || "—"}</p>
        </div>
      )}

      {/* Processing Status and Quality Verdict */}
      <div className="grid grid-cols-1 gap-2 md:grid-cols-4">
        <div>
          <p className="text-xs text-text-muted">Status</p>
          <div className={statusBadges[scan.processing_status] || "text-text-muted"}>
            {scan.processing_status}
          </div>
        </div>
        <div>
          <p className="text-xs text-text-muted">Verdict</p>
          {scan.quality_verdict && (
            <div className={verdictBadges[scan.quality_verdict] || "text-text-muted opacity-50"}>
              {scan.quality_verdict}
            </div>
          ) || (
            <span className="text-text-muted opacity-50">—</span>
          )}
        </div>
        <div>
          <p className="text-xs text-text-muted">Analyzed</p>
          <p className="text-sm text-text">{new Date(scan.analyzed_at).toLocaleString()}</p>
        </div>
        <div>
          <p className="text-xs text-text-muted">Received</p>
          <p className="text-sm text-text">{new Date(scan.received_at).toLocaleString()}</p>
        </div>
      </div>

      {/* Parameter-wise measurements table */}
      {scan.measurements.length > 0 && (
        <div className="mt-4">
          <p className="text-sm text-text-muted">Parameter Results</p>
          <table className="w-full bordered border-border-subtle rounded-md overflow-hidden">
            <thead>
              <tr className="border-b border-border-subtle bg-surface-muted/50">
                <th className="text-left py-2 px-4 text-xs font-medium text-text-muted">Metric</th>
                <th className="text-left py-2 px-4 text-xs font-medium text-text-muted">Value</th>
                <th className="text-left py-2 px-4 text-xs font-medium text-text-muted">Unit</th>
                <th className="text-left py-2 px-4 text-xs font-medium text-text-muted">Basis</th>
              </tr>
            </thead>
            <tbody>
              {scan.measurements.map((m) => (
                <tr key={m.metric_code} className="border-y hover:bg-surface-muted/50">
                  <td className="py-2 px-4">{m.metric_label || m.metric_code}</td>
                  <td className="py-2 px-4">{m.value}</td>
                  <td className="py-2 px-4">{m.unit}</td>
                  <td className="py-2 px-4">{m.basis}</td>
                  <td className="py-2 px-4">
                    {m.is_estimated && (
                      <span className="text-xs bg-yellow-100 text-yellow-800 rounded px-1 py-0.5">
                        estimated
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Files */}
      {scan.files && scan.files.length > 0 && (
        <div className="mt-4">
          <p className="text-sm text-text-muted">Files</p>
          <ul className="list-disc pl-5 space-y-1">
            {scan.files.map((f) => (
              <li key={f.filename} className="text-sm text-text">
                {f.available ? (
                  <a
                    href={`/scans/${scan.id}/report/download`}
                    className="text-brand underline cursor-pointer"
                    target="_blank"
                  >
                    {f.filename}
                  </a>
                ) : (
                  <span>{f.filename} (not available)</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}