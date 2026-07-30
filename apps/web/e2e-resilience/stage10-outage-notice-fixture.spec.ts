import { execSync } from "node:child_process";

import { expect, type Page, test } from "@playwright/test";

// Stage 10 final closure: a DIRECT, reproducible UI fixture for the
// "temporary provider outage" state, requested because component-level
// proxy coverage (another screen's Notice instance) was judged insufficient
// for this state specifically. Reuses the exact Stage 9 Delivery Phase 5
// fake-Google-server infrastructure Journey A already proves the retry
// behaviour against (same stack, same ports, same scenario vocabulary) —
// no new test-only bypass is introduced. Unlike Journey A (which proves the
// outage recovers within the retry budget), this fixture deliberately sets
// fail_count above retry_read's max_attempts so the failure survives
// retries and reaches the UI as a real, rendered degraded-sync notice —
// exercised here for its design/accessibility/layout properties, not to
// re-prove the retry mechanism itself (that remains Journey A's job).

const API_URL = "http://localhost:8011";
const FAKE_GOOGLE_URL = "http://localhost:8098";
const MUTATION_HEADERS = { "X-LifeFlow-CSRF": "1" };
const API_DIR = "../api";

const BREAKPOINTS = [
  { width: 1440, height: 900 },
  { width: 1024, height: 800 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
  { width: 320, height: 700 },
];

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
      display_name: "Playwright Stage10 Fixture",
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

test.beforeEach(async ({ page }) => {
  const reset = await page.request.post(`${FAKE_GOOGLE_URL}/__control__/reset`);
  expect(reset.ok()).toBeTruthy();
});

test("Stage 10 fixture — temporary provider outage renders a real, accessible, non-leaking notice", async ({
  page,
}, testInfo) => {
  test.setTimeout(60_000);
  const userId = await signIn(page, "outagefixture");
  support("seed-account", userId);

  // fail_count=5 exceeds retry_read's max_attempts (3): every attempt in
  // the retry budget fails, so the transient error survives retries and
  // reaches the UI as a real GoogleTransientError (retryable=true).
  await setScenario(page, "gmail_list_messages", "transient_then_recover", 5);

  await page.goto("/connections");
  await expect(page.getByTestId("google-connection-status")).toHaveText("active");
  await page.getByTestId("sync-google-now").click();

  const notice = page.getByTestId("sync-degraded-notice");
  await expect(notice).toBeVisible({ timeout: 15_000 });

  // Real message, not a fabricated one: exact backend safe-message copy.
  await expect(notice).toContainText("Google was temporarily unavailable.");
  // Safe manual-retry guidance is present.
  await expect(notice).toContainText("It is safe to try syncing again in a moment.");
  // Reconnection guidance must NOT appear for a transient (not permanent)
  // failure — that copy is reserved for the non-retryable branch.
  await expect(notice).not.toContainText("reconnect Google");

  // Accessible semantics: a non-urgent update stays role="status" /
  // aria-live="polite" (never "alert" — the account is not broken, a retry
  // is safe), per the Notice component's tone/role contract.
  await expect(notice).toHaveAttribute("role", "status");
  await expect(notice).toHaveAttribute("aria-live", "polite");

  // No raw provider detail anywhere on the page: no HTTP status code, no
  // exception class name, no fake credential, no stack trace.
  const bodyText = (await page.textContent("body")) ?? "";
  for (const forbidden of [
    "503",
    "HTTPException",
    "Traceback",
    "fake-access-token-never-a-real-google-credential",
    "transient_then_recover",
  ]) {
    expect(bodyText).not.toContain(forbidden);
  }

  // The error notice never blocks navigation or hides the rest of the page.
  await expect(page.getByTestId("nav-today")).toBeVisible();

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({
    path: testInfo.outputPath("10-connections-temporary-outage.png"),
    fullPage: true,
  });

  // Responsive: no horizontal overflow at any required breakpoint, controls
  // stay reachable, the notice text stays legible.
  for (const bp of BREAKPOINTS) {
    await page.setViewportSize(bp);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `horizontal overflow at ${bp.width}px`).toBeLessThanOrEqual(1);
    await expect(notice).toBeVisible();
    if (bp.width === 390) {
      await page.screenshot({
        path: testInfo.outputPath("10b-connections-temporary-outage-mobile-390.png"),
        fullPage: true,
      });
    }
  }
});
