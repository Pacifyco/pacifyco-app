import { config } from "../config";
import { getAccessToken } from "./supabase";

// Mirrors the API's error format: {"error": {"code", "message", "details"}} (api/app/errors.py).
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isClientError(): boolean {
    return this.status >= 400 && this.status < 500;
  }
}

const NETWORK_MESSAGE = "We couldn't reach Pacify. Check your connection and try again.";
const GENERIC_MESSAGE = "Something went wrong on our side. Please try again.";

type ErrorBody = { error?: { code?: unknown; message?: unknown; details?: unknown } };

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as ErrorBody;
    const { code, message, details } = body.error ?? {};
    if (typeof code === "string" && typeof message === "string") {
      return new ApiError(response.status, code, message, details ?? null);
    }
  } catch {
    // Not JSON (e.g. a proxy error page): fall through to the generic error.
  }
  return new ApiError(response.status, "unexpected_response", GENERIC_MESSAGE);
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  // Signed-in requests carry the Supabase access token; the API verifies it (api/app/auth.py).
  const token = await getAccessToken();
  if (token && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${config.apiUrl}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "network_error", NETWORK_MESSAGE);
  }

  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
