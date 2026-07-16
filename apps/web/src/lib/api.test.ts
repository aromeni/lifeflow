import { afterEach, expect, test, vi } from "vitest";

import { api, ApiError } from "./api";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue({
    status,
    ok: status < 400,
    json: () => Promise.resolve(body),
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
