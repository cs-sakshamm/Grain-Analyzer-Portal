const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

type ErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
    request_id?: string | null;
  };
};

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  auth?: boolean;
  signal?: AbortSignal;
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
 * The access token lives in memory only. The refresh token is an HttpOnly cookie the
 * browser sends automatically; it is never readable by JavaScript or persisted here.
 */
let accessToken: string | null = null;
let unauthorizedHandler: (() => Promise<boolean>) | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function setUnauthorizedHandler(handler: (() => Promise<boolean>) | null): void {
  unauthorizedHandler = handler;
}

async function execute(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (options.auth !== false && accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  return fetch(`${API_BASE}${path}`, {
    method: options.method ?? "GET",
    headers,
    credentials: "include",
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  });
}

/**
 * Single typed request path. A 401 triggers exactly one refresh attempt, then the
 * original request is replayed; the refresh call itself opts out so it cannot recurse.
 */
export async function apiRequest<T = unknown>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  let response = await execute(path, options);

  if (response.status === 401 && options.auth !== false && unauthorizedHandler) {
    const refreshed = await unauthorizedHandler();
    if (refreshed) {
      response = await execute(path, options);
    }
  }

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
    return undefined as T;
  }

  return (await response.json()) as T;
}

export function apiGet<T = unknown>(path: string, signal?: AbortSignal): Promise<T> {
  return apiRequest<T>(path, { signal });
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
