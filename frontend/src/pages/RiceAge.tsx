import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/auth-context";
import { apiGet } from "@/services/apiClient";

interface AgeResultDetail {
  age_value_months: string | null;
  age_min_months: string | null;
  age_max_months: string | null;
  age_category: string | null;
  proportion_percent: string | null;
  unit: string | null;
  method: string | null;
  model_version: string | null;
  validation_status: string | null;
}

interface RiceAgeScan {
  scan_id: string;
  sample_id: string;
  batch_code: string | null;
  lot_code: string | null;
  age: AgeResultDetail | null;
}

function getAgeStatusClass(
  validation_status: string | null
): string {
  if (!validation_status) return "text-text-muted";
  if (validation_status === "validated")
    return "bg-green-100 text-green-800 text-xs font-medium rounded px-2 py-1";
  if (validation_status === "provisional")
    return "bg-yellow-100 text-yellow-800 text-xs font-medium rounded px-2 py-1";
  if (validation_status === "rejected")
    return "bg-red-100 text-red-800 text-xs font-medium rounded px-2 py-1";
  return "text-text-muted";
}

function ageStatusText(validation_status: string | null): string {
  if (!validation_status) return "—";
  return validation_status;
}

export function RiceAgePage() {
  const { user } = useAuth();

  const { data, isLoading, isError } = useQuery<RiceAgeScan[]>({
    queryKey: ["rice-age"],
    queryFn: async () => {
      const result: { age_results: RiceAgeScan[] } = await apiGet(
        "/scans/analytics/rice-age"
      );
      return result.age_results || [];
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
        <p className="ml-2 text-text-muted">Loading rice age data…</p>
      </div>
    );
  }

  if (isError || !data || data.length === 0) {
    return (
      <div className="p-6 bg-surface rounded-lg">
        <p className="text-text-muted">No age results found</p>
        <p className="text-sm text-text-muted mt-1">
          Rice age results are available for completed scans with age validation.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Age results table */}
      <div className="rounded-xl border border-border-subtle bg-surface p-4">
        <p className="text-sm font-medium text-text-muted">Age Results</p>
        <table className="w-full">
          <thead>
            <tr className="border-b border-border-subtle">
              <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                Sample ID
              </th>
              <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                Age (months)
              </th>
              <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                Category
              </th>
              <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                Proportion
              </th>
              <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                Method
              </th>
              <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {data.map((scan) => {
              const age = scan.age;
              return (
                <tr key={scan.scan_id} className="border-y">
                  <td className="p-3">
                    <a
                      href={`/scans/${scan.scan_id}`}
                      className="text-text hover:text-brand underline"
                    >
                      {scan.sample_id}
                    </a>
                  </td>
                  <td className="p-3">
                    {age && age.age_value_months !== null && age.age_value_months !== "null" ? (
                      <>
                        {age.age_value_months} {age.unit || "months"}
                      </>
                    ) : (
                      <span className="text-text-muted">Not available</span>
                    )}
                  </td>
                  <td className="p-3">
                    {age && age.age_category || "—"}
                  </td>
                  <td className="p-3">
                    {age && age.proportion_percent !== null && age.proportion_percent !== "null" ? (
                      <>
                        {age.proportion_percent}%
                      </>
                    ) : (
                      <span className="text-text-muted">—</span>
                    )}
                  </td>
                  <td className="p-3">{age && age.method || "—"}</td>
                  <td className="p-3"><span className={getAgeStatusClass(age?.validation_status as string | null)}>
                      {ageStatusText(age?.validation_status as string | null)}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Note about nullable age */}
      <div className="rounded-xl border border-border-subtle bg-surface p-4">
        <p className="text-sm text-text-muted">
          Note: Missing rice age is shown as "Not available", never as zero. Age results
          are nullable — a scan without an age result simply has no age data, which is
          different from an age of 0 months.
        </p>
      </div>
    </div>
  );
}