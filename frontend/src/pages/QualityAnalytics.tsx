import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/auth-context";
import { apiGet } from "@/services/apiClient";

interface ParameterSummaryEntry {
  count: number;
  min?: number;
  max?: number;
  avg?: number;
}

interface ParameterSummary {
  [metricCode: string]: {
    [basisKey: string]: ParameterSummaryEntry;
  };
}

interface QualityAnalyticsData {
  total_scans: number;
  quality_distribution: Record<string, number>;
  status_distribution: Record<string, number>;
  parameter_summary: ParameterSummary;
}

function verdictColor(verdict: string): string {
  if (verdict === "pass") return "from-green-500 to-green-400";
  if (verdict === "flagged") return "from-yellow-500 to-yellow-400";
  if (verdict === "inconclusive") return "from-blue-500 to-blue-400";
  return "from-purple-500 to-purple-400";
}

function statusColor(status: string): string {
  if (status === "completed") return "from-green-500 to-green-400";
  if (status === "received") return "from-blue-500 to-blue-400";
  if (status === "verifying") return "from-yellow-500 to-yellow-400";
  if (status === "failed") return "from-red-500 to-red-400";
  return "from-gray-500 to-gray-300";
}

export function QualityAnalyticsPage() {
  const { user } = useAuth();

  const { data, isLoading, isError } = useQuery<QualityAnalyticsData>({
    queryKey: ["quality-analytics"],
    queryFn: async (): Promise<QualityAnalyticsData> => {
      const result: QualityAnalyticsData = await apiGet("/scans/analytics/quality");
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
        <p className="ml-2 text-text-muted">Loading quality analytics…</p>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="p-6 bg-surface rounded-lg">
        <p className="text-text-muted">No analytics data available</p>
      </div>
    );
  }

  const { total_scans, quality_distribution, status_distribution, parameter_summary } = data;

  // Get the top parameters for chart display
  const topParameters = Object.entries(parameter_summary)
    .slice(0, 5)
    .map(([code, bases]) => ({
      code,
      bases: Object.entries(bases),
    }));

  // Build quality distribution rows
  const qualityRows: React.ReactNode[] = [];
  ["pass", "flagged", "inconclusive", "lab_confirmation_required"].forEach(
    (verdict) => {
      const count = quality_distribution[verdict] || 0;
      qualityRows.push(
        <div key={verdict} className="mb-2">
          <div className="flex justify-between text-xs mb-1">
            <span>{verdict}</span>
            <span>{count}</span>
          </div>
          <div className="h-4 rounded">
            <div
              style={{
                width: `${(count / total_scans) * 100}%`,
                height: "100%",
                background: `linear-gradient(${verdictColor(verdict)})`,
              }}
            />
          </div>
        </div>
      );
    }
  );

  // Build status distribution rows
  const statusRows: React.ReactNode[] = [];
  Object.entries(status_distribution).forEach(
    ([status, count]) => {
      statusRows.push(
        <div key={status} className="mb-2">
          <div className="flex justify-between text-xs mb-1">
            <span>{status}</span>
            <span>{count}</span>
          </div>
          <div className="h-4 rounded">
            <div
              style={{
                width: `${(count / total_scans) * 100}%`,
                height: "100%",
                background: `${statusColor(status)}`,
              }}
            />
          </div>
        </div>
      );
    }
  );

  // Build parameter rows
  const parameterRows: React.ReactNode[] = [];
  topParameters.forEach((param) => {
    parameterRows.push(
      <div key={param.code} className="p-3 bg-surface rounded-xl border border-border-subtle">
        <p className="text-xs font-medium text-text-muted">{param.code}</p>
        <div className="h-4 rounded mt-1">
          {param.bases.map(([basis, stats]) => {
            const statsEntry = stats as ParameterSummaryEntry;
            const pct = total_scans > 0 ? (statsEntry.count / total_scans) * 100 : 0;
            const color =
              basis.includes("count_percent")
                ? "from-green-400 to-green-200"
                : basis.includes("physical_mass")
                  ? "from-blue-400 to-blue-200"
                  : basis.includes("estimated_mass")
                    ? "from-purple-400 to-purple-200"
                    : "from-gray-400 to-gray-200";

            return (
              <div key={basis} className="mb-1">
                <div className="flex text-xs justify-between mb-0.5">
                  <span>{basis}</span>
                  <span>{statsEntry.count} ({pct.toFixed(1)}%)</span>
                </div><div
                  style={{
                    height: "100%",
                    background: color,
                    width: `${String(pct)}%`,
                  }}
 />
              </div>
            );
          })}
        </div>
      </div>
    );
  });

  return (
    <div className="space-y-4">
      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="rounded-xl border border-border-subtle bg-surface p-4">
          <p className="text-sm text-text-muted">Total Scans</p>
          <p className="text-2xl font-semibold text-text">{total_scans}</p>
        </div>
        <div className="rounded-xl border border-border-subtle bg-surface p-4">
          <p className="text-sm text-text-muted">Quality Distribution</p>
          <p className="text-2xl font-semibold text-text">
            {quality_distribution.pass || 0} Pass /
            {quality_distribution.flagged || 0} Flagged
          </p>
        </div>
        <div className="rounded-xl border border-border-subtle bg-surface p-4">
          <p className="text-sm text-text-muted">Status Distribution</p>
          <p className="text-2xl font-semibold text-text">
            {status_distribution.completed || 0} Completed
          </p>
        </div>
        <div className="rounded-xl border border-border-subtle bg-surface p-4">
          <p className="text-sm text-text-muted">Parameters Tracked</p>
          <p className="text-2xl font-semibold text-text">{topParameters.length}</p>
        </div>
      </div>

      {/* Quality Distribution Chart */}
      <div className="rounded-xl border border-border-subtle bg-surface p-4">
        <p className="text-sm font-medium text-text-muted">Quality Verdict Distribution</p>
        <div className="h-64">{qualityRows}</div>
      </div>

      {/* Status Distribution Chart */}
      <div className="rounded-xl border border-border-subtle bg-surface p-4">
        <p className="text-sm font-medium text-text-muted">Processing Status Distribution</p>
        <div className="h-64">{statusRows}</div>
      </div>

      {/* Parameter-wise trends */}
      {topParameters.length > 0 && (
        <div>
          <p className="text-sm text-text-muted">Parameter Trends</p>
          <div className="grid grid-cols-2 gap-3 mt-3">
            {parameterRows}
          </div>
        </div>
      )}
    </div>
  );
}
