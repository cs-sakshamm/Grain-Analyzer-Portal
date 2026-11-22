/**
 * Presentation helpers that keep measurement provenance visible.
 *
 * These functions never convert between measurement bases and never substitute a value
 * for missing data: an absent age or measurement renders as "Not available".
 */

export type MeasurementBasis =
  | "count_percent"
  | "estimated_mass_percent"
  | "physical_mass_percent"
  | "physical_mass_grams"
  | "count"
  | "dimension"
  | "ratio"
  | "other";

const BASIS_LABELS: Record<MeasurementBasis, string> = {
  count_percent: "count %",
  estimated_mass_percent: "est. mass %",
  physical_mass_percent: "physical mass %",
  physical_mass_grams: "physical mass",
  count: "kernel count",
  dimension: "dimension",
  ratio: "ratio",
  other: "other basis",
};

const NUMBER_FORMAT = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

export function basisLabel(basis: string): string {
  return BASIS_LABELS[basis as MeasurementBasis] ?? "basis not stated";
}

export function formatMeasurement(
  value: number | null | undefined,
  unit: string,
  basis?: string | null,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Not available";
  }

  const formatted = NUMBER_FORMAT.format(value);

  switch (unit) {
    case "percent":
      return basis ? `${formatted}% (${basisLabel(basis)})` : `${formatted}%`;
    case "mm":
      return `${formatted} mm`;
    case "gram":
      return `${formatted} g`;
    case "count":
      return `${formatted} kernels`;
    case "months":
      return `${formatted} months`;
    case "ratio":
      return formatted;
    default:
      return `${formatted} ${unit}`.trim();
  }
}

export type AgeResultInput = {
  age_value_months?: number | null;
  age_min_months?: number | null;
  age_max_months?: number | null;
  age_category?: string | null;
} | null;

/**
 * Render a device-supplied age result. A missing or empty result is explicitly
 * "Not available"; a supplied zero is a real value and is preserved.
 */
export function formatAgeResult(age: AgeResultInput): string {
  if (!age) {
    return "Not available";
  }

  if (age.age_category) {
    return age.age_category;
  }

  if (age.age_value_months !== null && age.age_value_months !== undefined) {
    return `${NUMBER_FORMAT.format(age.age_value_months)} months`;
  }

  const hasMin = age.age_min_months !== null && age.age_min_months !== undefined;
  const hasMax = age.age_max_months !== null && age.age_max_months !== undefined;

  if (hasMin && hasMax) {
    return `${NUMBER_FORMAT.format(age.age_min_months as number)}-${NUMBER_FORMAT.format(
      age.age_max_months as number,
    )} months`;
  }
  if (hasMin) {
    return `From ${NUMBER_FORMAT.format(age.age_min_months as number)} months`;
  }
  if (hasMax) {
    return `Up to ${NUMBER_FORMAT.format(age.age_max_months as number)} months`;
  }

  return "Not available";
}
