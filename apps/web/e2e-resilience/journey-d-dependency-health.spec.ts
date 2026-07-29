import { execSync } from "node:child_process";

import { expect, test } from "@playwright/test";

// Stage 9 Delivery Phase 5 (§20) Journey D — dependency health. Stops and
// starts the REAL Postgres/Redis containers the dedicated resilience API
// (port 8011) depends on — this is why this whole suite runs in its own
// invocation, never alongside scripts/e2e.sh (see playwright.resilience.config.ts).

const API_URL = "http://localhost:8011";
const FAKE_GOOGLE_URL = "http://localhost:8098";
const REPO_ROOT = "../..";

function compose(args: string): string {
  return execSync(`docker compose ${args}`, { cwd: REPO_ROOT, encoding: "utf8" });
}

async function waitForDbHealthy(): Promise<void> {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    const health = compose("ps db --format {{.Health}}").trim();
    if (health === "healthy") return;
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }
  throw new Error("db did not become healthy again in time");
}

async function waitForReady(request: import("@playwright/test").APIRequestContext): Promise<void> {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    const response = await request.get(`${API_URL}/ready`);
    if (response.status() === 200) {
      const body = await response.json();
      if (body.degraded_dependencies.length === 0) return;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("/ready did not fully recover in time");
}

test.afterEach(async () => {
  // Belt-and-braces: whatever this test stopped, make sure it's running
  // again before the next test (or the suite ending) regardless of outcome.
  compose("start db redis");
  await waitForDbHealthy();
});

test("Journey D — dependency health reflects real Postgres/Redis state without ever failing liveness", async ({
  request,
}) => {
  test.setTimeout(120_000);

  // Healthy baseline.
  const healthBefore = await request.get(`${API_URL}/health`);
  expect(healthBefore.status()).toBe(200);
  expect(await healthBefore.json()).toEqual({ status: "ok" });
  const readyBefore = await request.get(`${API_URL}/ready`);
  expect(readyBefore.status()).toBe(200);
  expect(await readyBefore.json()).toEqual({ status: "ok", degraded_dependencies: [] });
  const metricsBefore = await request.get(`${API_URL}/metrics`);
  expect(metricsBefore.status()).toBe(200);

  // Redis outage -> documented degraded (non-blocking) response.
  compose("stop redis");
  let redisDegraded = false;
  const redisDeadline = Date.now() + 15_000;
  while (Date.now() < redisDeadline && !redisDegraded) {
    const ready = await request.get(`${API_URL}/ready`);
    const body = await ready.json();
    if (ready.status() === 200 && body.degraded_dependencies.includes("redis")) {
      redisDegraded = true;
    } else {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  expect(redisDegraded).toBeTruthy();
  // Ordinary routes stay unaffected by Redis being down.
  const healthDuringRedisOutage = await request.get(`${API_URL}/health`);
  expect(healthDuringRedisOutage.status()).toBe(200);

  // Redis recovery -> readiness restored.
  compose("start redis");
  await waitForReady(request);

  // PostgreSQL outage -> safe readiness failure (503), liveness unaffected.
  compose("stop db");
  let dbUnavailable = false;
  const dbDeadline = Date.now() + 15_000;
  while (Date.now() < dbDeadline && !dbUnavailable) {
    const ready = await request.get(`${API_URL}/ready`);
    if (ready.status() === 503) {
      dbUnavailable = true;
      expect(await ready.json()).toEqual({ status: "unavailable" });
    } else {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  expect(dbUnavailable).toBeTruthy();
  const healthDuringDbOutage = await request.get(`${API_URL}/health`);
  expect(healthDuringDbOutage.status()).toBe(200);
  expect(await healthDuringDbOutage.json()).toEqual({ status: "ok" });

  // PostgreSQL recovery -> readiness restored.
  compose("start db");
  await waitForDbHealthy();
  await waitForReady(request);

  // A simulated Google outage must never make liveness fail — Google is
  // never checked by /health or /ready at all (see
  // docs/delivery/runbooks/health-readiness.md).
  const scenario = await request.post(`${FAKE_GOOGLE_URL}/__control__/scenario`, {
    data: { operation: "gmail_list_messages", scenario: "permanent_failure" },
  });
  expect(scenario.ok()).toBeTruthy();
  const healthWithGoogleDown = await request.get(`${API_URL}/health`);
  expect(healthWithGoogleDown.status()).toBe(200);
  const readyWithGoogleDown = await request.get(`${API_URL}/ready`);
  expect(readyWithGoogleDown.status()).toBe(200);
  await request.post(`${FAKE_GOOGLE_URL}/__control__/reset`);

  // No connection strings, hosts, credentials, stack traces, or private
  // sentinels ever appear in any of these responses.
  for (const url of [`${API_URL}/health`, `${API_URL}/ready`, `${API_URL}/metrics`]) {
    const response = await request.get(url);
    const text = await response.text();
    expect(text).not.toMatch(/postgresql:\/\//i);
    expect(text).not.toMatch(/redis:\/\//i);
    expect(text.toLowerCase()).not.toContain("lifeflow:lifeflow");
    expect(text).not.toContain("Traceback");
    expect(text.toLowerCase()).not.toContain("password");
  }
});
