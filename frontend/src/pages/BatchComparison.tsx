import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/auth-context";
import { apiGet } from "@/services/apiClient";

interface MeasurementValue {
  metric_code: string;
  value: string;
  unit: string;
  basis: string;
}

interface ScanMeasurement {
  [basis: string]: MeasurementValue[];
}

interface BatchComparisonData {
  batches: Record<string, Array<{
    scan_id: string;
    sample_id: string;
    measurements: ScanMeasurement;
  }>>;
}

export function BatchComparisonPage() {
  const { user } = useAuth();

  const { data, isLoading, isError } = useQuery<BatchComparisonData>({
    queryKey: ["batch-comparison"],
    queryFn: async () => {
      const result: any = await apiGet("/scans/analytics/batch-comparison");
      return result.batches || {};
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
        <p className="ml-2 text-text-muted">Loading batch comparison…</p>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="p-6 bg-surface rounded-lg">
        <p className="text-text-muted">No batch data available</p>
      </div>
    );
  }

  const batches = data;

  return (
    <div className="space-y-4">
      {/* Batch selection */}
      <div className="rounded-xl border border-border-subtle bg-surface p-4">
        <p className="text-sm font-medium text-text-muted mb-3">Select Batches</p>
        <div className="grid grid-cols-2 gap-2">
          {Object.entries(batches).map(([batchKey, scans]) => {
            const isUnbatched = batchKey === "unbatched";
            const batchDisplayName = isUnbatched ? "Unbatched" : `Batch: ${batchKey}`;
            const batchBg = isUnbatched
              ? "border-red-300 bg-red-50/50"
              : "border-blue-300 bg-blue-50/50";
            const onClick = isUnbatched
              ? () => window.alert("No batch code")
              : () => { window.location.hash = batchKey; };

            return (
              <div
                key={batchKey}
                className={
                  `p-3 rounded-md border ${batchBg} ${
                    !isUnbatched && scans.length > 0
                      ? "cursor-pointer hover:bg-surface-hover"
                      : ""
                  }`
                }
                onClick={onClick}
                title={isUnbatched ? "No batch code" : `Compare ${batchKey}`}
              >
                <span className="font-medium text-text">
                  {batchDisplayName}
                </span>
                <span className="text-xs text-text-muted ml-2">
                  ({scans.length} scans)
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Comparison tables per batch */}
      {Object.keys(batches).length > 0 && (
        <div>
          {Object.entries(batches).map(([batchKey, scans]) => {
            if (batchKey === "unbatched" && scans.length === 0) {
              return null;
            }

            // Collect all metric codes across scans in this batch
            const allMetrics = new Set<string>();
            scans.forEach((scan: any) => {
              Object.keys(scan.measurements).forEach((basis) => {
                scan.measurements[basis].forEach((m: any) => allMetrics.add(m.metric_code));
              });
            });

            // Group by compatible basis
            const compatibleMeasurements: Array<{
              metric_code: string;
              values: Array<{ basis: string; value: string; unit: string }>;
            }> = [];

            allMetrics.forEach((metricCode) => {
              const valuesByBasis: Array<{ basis: string; value: string; unit: string }> = [];
              scans.forEach((scan: any) => {
                Object.keys(scan.measurements).forEach((basis) => {
                  if (basis === "count_percent") {
                    const m: any = scan.measurements[basis].find(
                      (m: any) => m.metric_code === metricCode
                    );
                    if (m) valuesByBasis.push({ basis, value: m.value, unit: m.unit });
                  } else if (basis === "estimated_mass_percent") {
                    const m = scan.measurements[basis].find(
                      (m: any) => m.metric_code === metricCode
                    );
                    if (m) valuesByBasis.push({ basis, value: m.value, unit: m.unit });
                  } else {
                    const m = scan.measurements[basis].find(
                      (m: any) => m.metric_code === metricCode
                    );
                    if (m) valuesByBasis.push({ basis, value: m.value, unit: m.unit });
                  }
                });
              });
              if (valuesByBasis.length > 0) {
                compatibleMeasurements.push({
                  metric_code: metricCode,
                  values: valuesByBasis,
                });
              }
            });

            return (
              <div key={batchKey} className="rounded-xl border border-border-subtle bg-surface p-4 mb-3">
                <p className="text-sm font-medium text-text">
                  {batchKey === "unbatched" ? "Unbatched scans" : `Batch: ${batchKey}`}
                </p>
                <p className="text-xs text-text-muted">
                  {scans.length} scans
                </p>
                {compatibleMeasurements.length > 0 ? (
                  <div className="mt-3 space-y-2">
                    {compatibleMeasurements.map((metric) => (
                      <div
                        key={metric.metric_code}
                        className="p-3 bg-surface rounded-xl border border-border-subtle"
                      >
                        <p className="text-xs font-medium text-text-muted">{metric.metric_code}</p>
                        <div className="grid grid-cols-2 gap-2">
                          {metric.values.map((v, i) => (
                            <div
                              key={i}
                              className="flex items-center justify-between text-sm"
                            >
                              <span>
                                {v.value}
                                {v.unit && <span className="text-xs ml-1">({v.unit})</span>}
                              </span>
                              <span className="text-xs text-text-muted">
                                {v.basis}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-text-muted mt-2">
                    No compatible measurements found. Count percent and
                    estimated-mass percent are kept separate per DR-020.
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}