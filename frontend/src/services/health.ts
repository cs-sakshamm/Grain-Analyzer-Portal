import { apiGet } from "@/services/apiClient";
import { healthSchema, readinessSchema } from "@/types/api";

export async function fetchHealth() {
  return healthSchema.parse(await apiGet("/health"));
}

export async function fetchReadiness() {
  return readinessSchema.parse(await apiGet("/health/ready"));
}
