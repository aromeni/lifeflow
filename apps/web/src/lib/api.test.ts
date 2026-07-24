import { afterEach, expect, test, vi } from "vitest";

import { api, ApiError, RateLimitError } from "./api";

function mockFetch(status: number, body: unknown, headers: Record<string, string> = {}) {
  const fn = vi.fn().mockResolvedValue({
    status,
    ok: status < 400,
    json: () => Promise.resolve(body),
    headers: { get: (name: string) => headers[name] ?? null },
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

test("every request carries credentials and the CSRF header", async () => {
  const fetchMock = mockFetch(200, { ok: true });
  await api("/me");
  const [url, init] = fetchMock.mock.calls[0];
  expect(String(url)).toContain("/me");
  expect(init.credentials).toBe("include");
  expect(init.headers["X-LifeFlow-CSRF"]).toBe("1");
});

test("API errors surface the shared error shape", async () => {
  mockFetch(401, { error: { code: "unauthenticated", message: "Not signed in." } });
  const error = await api("/me").catch((e: unknown) => e);
  expect(error).toBeInstanceOf(ApiError);
  const apiError = error as ApiError;
  expect(apiError.status).toBe(401);
  expect(apiError.code).toBe("unauthenticated");
});

test("204 responses resolve without parsing a body", async () => {
  mockFetch(204, undefined);
  await expect(api("/auth/logout", { method: "POST" })).resolves.toBeUndefined();
});

test("a 429 with a body retry_after_seconds surfaces a RateLimitError", async () => {
  mockFetch(429, {
    error: {
      code: "rate_limited",
      message: "Too many requests. Try again later.",
      correlation_id: "c1",
      retry_after_seconds: 42,
    },
  });
  const error = await api("/briefs/generate", { method: "POST" }).catch((e: unknown) => e);
  expect(error).toBeInstanceOf(RateLimitError);
  const rateLimitError = error as RateLimitError;
  expect(rateLimitError.status).toBe(429);
  expect(rateLimitError.retryAfterSeconds).toBe(42);
});

test("a 429 without a body value falls back to the Retry-After header", async () => {
  mockFetch(
    429,
    { error: { code: "rate_limited", message: "Too many requests." } },
    { "Retry-After": "17" },
  );
  const error = await api("/briefs/generate", { method: "POST" }).catch((e: unknown) => e);
  expect(error).toBeInstanceOf(RateLimitError);
  expect((error as RateLimitError).retryAfterSeconds).toBe(17);
});

test("a 429 with neither source falls back to a safe default", async () => {
  mockFetch(429, { error: { code: "rate_limited", message: "Too many requests." } });
  const error = await api("/briefs/generate", { method: "POST" }).catch((e: unknown) => e);
  expect((error as RateLimitError).retryAfterSeconds).toBe(30);
});
