const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

type ErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
    request_id?: string | null;
  };
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;

  constructor(status: number, code: string, message: string, requestId: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

/**
 * Minimal JSON client. Feature modules add typed wrappers and parse responses with Zod;
 * components never call fetch directly.
 */
export async function apiGet(path: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    headers: { Accept: "application/json" },
    credentials: "include",
    signal,
  });

  if (!response.ok) {
    let envelope: ErrorEnvelope = {};
    try {
      envelope = (await response.json()) as ErrorEnvelope;
    } catch {
      // Non-JSON error bodies are normalised below.
    }
    throw new ApiError(
      response.status,
      envelope.error?.code ?? "unknown_error",
      envelope.error?.message ?? `Request failed with status ${response.status}`,
      envelope.error?.request_id ?? null,
    );
  }

  if (response.status === 204) {
    return undefined;
  }

  return (await response.json()) as unknown;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.requestId ? `${error.message} (request ${error.requestId})` : error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "An unexpected error occurred.";
}
