import { execSync } from "node:child_process";

import { expect, test, type Page } from "@playwright/test";

// Stage 9 Delivery Phase 5 (§20) Journey A — transient provider-read outage.
// Runs against the dedicated resilience stack (see playwright.resilience.config.ts):
// a real Postgres-backed API on :8011 with GOOGLE_OAUTH_ENABLED=true and its
// Google clients redirected to the fake Google server on :8098, and the real
// web app on :3001. Never the real Google API.

const API_URL = "http://localhost:8011";
const FAKE_GOOGLE_URL = "http://localhost:8098";
const MUTATION_HEADERS = { "X-LifeFlow-CSRF": "1" };
const API_DIR = "../api";

function support(command: string, userId: string): string {
  return execSync(`uv run python scripts/e2e_google_support.py ${command} ${userId}`, {
    cwd: API_DIR,
    encoding: "utf8",
    env: { ...process.env, LIFEFLOW_E2E: "1", PYTHONPATH: "src" },
  });
}

async function signIn(page: Page, marker: string): Promise<string> {
  await page.goto("/");
  const login = await page.request.post(`${API_URL}/auth/dev-login`, {
    headers: MUTATION_HEADERS,
    data: {
      email: `pw-${marker}-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      display_name: "Playwright Resilience",
    },
  });
  expect(login.ok()).toBeTruthy();
  return (await login.json()).user_id as string;
}

async function setScenario(
  page: Page,
  operation: string,
  scenario: string,
  failCount = 0,
): Promise<void> {
  const response = await page.request.post(`${FAKE_GOOGLE_URL}/__control__/scenario`, {
    data: { operation, scenario, fail_count: failCount },
  });
  expect(response.ok()).toBeTruthy();
}

async function fakeGoogleState(page: Page): Promise<{
  draft_count: number;
  event_count: number;
  call_counts: Record<string, number>;
}> {
  const response = await page.request.get(`${FAKE_GOOGLE_URL}/__control__/state`);
  expect(response.ok()).toBeTruthy();
  return response.json();
}

test.beforeEach(async ({ page }) => {
  const reset = await page.request.post(`${FAKE_GOOGLE_URL}/__control__/reset`);
  expect(reset.ok()).toBeTruthy();
});

test("Journey A — transient Gmail read outage recovers within the bounded retry budget", async ({
  page,
}) => {
  test.setTimeout(60_000);
  const userId = await signIn(page, "readoutage");
  support("seed-account", userId);

  // registered transient failures trigger bounded read retries: fail_count=2
  // is inside retry_read's default max_attempts=3 budget for list_messages.
  await setScenario(page, "gmail_list_messages", "transient_then_recover", 2);

  await page.goto("/connections");
  await expect(page.getByTestId("google-connection-status")).toHaveText("active");

  let syncResponseBody = "";
  page.on("response", async (response) => {
    if (response.url() === `${API_URL}/connected-accounts/google/sync`) {
      syncResponseBody = await response.text().catch(() => "");
    }
  });

  await page.getByTestId("sync-google-now").click();

  // provider recovery produces eventual success — the sync completes and
  // imports both fake messages, never surfacing the two transient failures
  // as a user-visible error.
  await expect(page.getByTestId("sync-result")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("sync-result")).toContainText("Imported 2");
  await expect(page.getByTestId("sync-error-notice")).toHaveCount(0);
  await expect(page.getByTestId("sync-degraded-notice")).toHaveCount(0);

  // retry count remains bounded: exactly 3 calls (2 failures + 1 success),
  // never more — retry_read must never retry past its configured budget.
  const state = await fakeGoogleState(page);
  expect(state.call_counts.gmail_list_messages).toBe(3);

  await expect(page.getByTestId("inventory-source_items")).toHaveText("2");

  // SourceItems are not duplicated: a second, healthy sync must not import
  // the same two messages again.
  await setScenario(page, "gmail_list_messages", "healthy");
  await page.getByTestId("sync-google-now").click();
  await expect(page.getByTestId("sync-result")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("inventory-source_items")).toHaveText("2");

  // private/provider sentinels do not appear in the UI or the API response.
  const bodyText = (await page.textContent("body")) ?? "";
  expect(bodyText).not.toContain("fake-access-token-never-a-real-google-credential");
  expect(syncResponseBody).not.toContain("fake-access-token-never-a-real-google-credential");
  expect(syncResponseBody).not.toContain("Traceback");
});
