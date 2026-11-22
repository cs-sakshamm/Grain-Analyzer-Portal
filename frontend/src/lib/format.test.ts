import { describe, expect, it } from "vitest";

import { basisLabel, formatAgeResult, formatMeasurement } from "@/lib/format";

describe("formatMeasurement", () => {
  it("labels percentages with their measurement basis", () => {
    expect(formatMeasurement(50.68, "percent", "estimated_mass_percent")).toBe(
      "50.68% (est. mass %)",
    );
    expect(formatMeasurement(39.94, "percent", "count_percent")).toBe("39.94% (count %)");
  });

  it("keeps count and estimated-mass percentages visibly distinct", () => {
    const estimated = formatMeasurement(71.91, "percent", "estimated_mass_percent");
    const counted = formatMeasurement(76.92, "percent", "count_percent");

    expect(estimated).not.toBe(counted);
  });

  it("renders a missing value as not available instead of zero", () => {
    expect(formatMeasurement(null, "percent", "count_percent")).toBe("Not available");
    expect(formatMeasurement(undefined, "mm")).toBe("Not available");
    expect(formatMeasurement(Number.NaN, "ratio")).toBe("Not available");
  });

  it("preserves a genuine zero value", () => {
    expect(formatMeasurement(0, "percent", "estimated_mass_percent")).toBe(
      "0% (est. mass %)",
    );
  });

  it("formats dimensions, counts and mass with units", () => {
    expect(formatMeasurement(5.25, "mm")).toBe("5.25 mm");
    expect(formatMeasurement(363, "count")).toBe("363 kernels");
    expect(formatMeasurement(8.87, "gram")).toBe("8.87 g");
  });

  it("states when the basis is unknown rather than guessing", () => {
    expect(basisLabel("mystery_basis")).toBe("basis not stated");
    expect(formatMeasurement(12, "percent", "other")).toBe("12% (other basis)");
  });
});

describe("formatAgeResult", () => {
  it("returns not available when the device supplied no age", () => {
    expect(formatAgeResult(null)).toBe("Not available");
    expect(formatAgeResult({})).toBe("Not available");
  });

  it("prefers the supplied category and preserves a range", () => {
    expect(formatAgeResult({ age_category: "8-10 Months", age_min_months: 8, age_max_months: 10 })).toBe(
      "8-10 Months",
    );
    expect(formatAgeResult({ age_min_months: 8, age_max_months: 10 })).toBe("8-10 months");
  });

  it("renders a scalar age and keeps zero as a real value", () => {
    expect(formatAgeResult({ age_value_months: 6 })).toBe("6 months");
    expect(formatAgeResult({ age_value_months: 0 })).toBe("0 months");
  });

  it("handles a one-sided range", () => {
    expect(formatAgeResult({ age_min_months: 12 })).toBe("From 12 months");
    expect(formatAgeResult({ age_max_months: 3 })).toBe("Up to 3 months");
  });
});
