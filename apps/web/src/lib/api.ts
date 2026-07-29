// Single path to the backend: session cookie included, CSRF header always
// set, shared error shape decoded. All request/response types come from the
// generated contracts package.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8010";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly retryAfterSeconds?: number,
    // Stage 9 Delivery Phase 5 (§17): present only where the API has a
    // genuine, closed-taxonomy answer (e.g. a Google-dependent route) —
    // `undefined` means "not applicable/unknown", never "safe to retry".
    // A caller must never infer retryability from its absence.
    public readonly retryable?: boolean,
    public readonly dependency?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// Stage 9 Delivery Phase 4 (ADR 0005 D64/D81): a 429 carries a bounded
// `retry_after_seconds` in the body and the standard `Retry-After` header —
// the header is the fallback source since some fetch polyfills/proxies can
// still deliver a body-less 429 (e.g. an intermediary rejecting the request).
export class RateLimitError extends ApiError {
  // Narrows the inherited optional field: a RateLimitError always has one.
  public readonly retryAfterSeconds: number;

  constructor(retryAfterSeconds: number, message: string) {
    super(429, "rate_limited", message, retryAfterSeconds);
    this.name = "RateLimitError";
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

function retryAfterFromHeader(response: Response): number | undefined {
  const header = response.headers.get("Retry-After");
  if (header === null) return undefined;
  const parsed = Number.parseInt(header, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-LifeFlow-CSRF": "1",
      ...init?.headers,
    },
  });
  if (response.status === 204) {
    return undefined as T;
  }
  const body = await response.json();
  if (!response.ok) {
    const error = body?.error ?? {};
    const message = error.message ?? "Request failed";
    if (response.status === 429) {
      const retryAfterSeconds =
        typeof error.retry_after_seconds === "number"
          ? error.retry_after_seconds
          : (retryAfterFromHeader(response) ?? 30);
      throw new RateLimitError(retryAfterSeconds, message);
    }
    throw new ApiError(
      response.status,
      error.code ?? "error",
      message,
      undefined,
      typeof error.retryable === "boolean" ? error.retryable : undefined,
      typeof error.dependency === "string" ? error.dependency : undefined,
    );
  }
  return body as T;
}
