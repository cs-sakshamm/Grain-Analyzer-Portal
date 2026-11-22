import { apiRequest } from "@/services/apiClient";
import {
  meResponseSchema,
  tokenResponseSchema,
  type TokenResponse,
  type User,
} from "@/types/auth";

export async function loginRequest(email: string, password: string): Promise<TokenResponse> {
  const data = await apiRequest<unknown>("/auth/login", {
    method: "POST",
    auth: false,
    body: { email, password },
  });
  return tokenResponseSchema.parse(data);
}

let refreshInFlight: Promise<TokenResponse> | null = null;

/**
 * Coalesces concurrent refreshes (for example React StrictMode double effects) into one
 * rotation; rotating twice with the same cookie would trip reuse detection.
 */
export function refreshRequest(): Promise<TokenResponse> {
  refreshInFlight ??= apiRequest<unknown>("/auth/refresh", {
    method: "POST",
    auth: false,
  })
    .then((data) => tokenResponseSchema.parse(data))
    .finally(() => {
      refreshInFlight = null;
    });
  return refreshInFlight;
}

export async function logoutRequest(): Promise<void> {
  await apiRequest<void>("/auth/logout", { method: "POST", auth: false });
}

export async function meRequest(): Promise<User> {
  const data = await apiRequest<unknown>("/auth/me");
  return meResponseSchema.parse(data).user;
}
