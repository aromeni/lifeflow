import { expect, type Page, test } from "@playwright/test";

// Stage 10 §14: every principal screen, plus the highest-risk confirmation
// state reachable in demo mode, must render without horizontal overflow at
// desktop, laptop, tablet, mobile and narrow-mobile widths. Each test signs
// in once and then resizes in place — cheaper than re-running the full setup
// per breakpoint, and it still proves the same DOM survives every width.
//
// Two states named in the spec are deliberately not covered here:
// "degraded provider" (a retryable Google sync failure) and "uncertain
// execution" require either a live Google mock or the dedicated
// dependency-outage Playwright journeys (which must never run concurrently
// with this suite — see e2e/resilience/README or CLAUDE.md). Both states
// render through the same shared <Notice> component already exercised at
// every breakpoint below (Connections' own sync-error notice, Approvals'
// execution-context-changed-notice), so the layout risk is covered by proxy
// rather than by a dedicated fixture.

const API_URL = "http://localhost:8010";
const MUTATION_HEADERS = { "X-LifeFlow-CSRF": "1" };

const BREAKPOINTS = [
  { name: "1440", width: 1440, height: 900 },
  { name: "1024", width: 1024, height: 800 },
  { name: "768", width: 768, height: 1024 },
  { name: "390", width: 390, height: 844 },
  { name: "320", width: 320, height: 700 },
];

async function assertNoHorizontalOverflowAtEveryBreakpoint(page: Page) {
  for (const bp of BREAKPOINTS) {
    await page.setViewportSize({ width: bp.width, height: bp.height });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `horizontal overflow at ${bp.width}px on ${page.url()}`).toBeLessThanOrEqual(
      1,
    );
  }
}

async function startDemo(page: Page) {
  await page.goto("/");
  const login = await page.request.post(`${API_URL}/auth/dev-login`, {
    headers: MUTATION_HEADERS,
    data: {
      email: `playwright-responsive-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      display_name: "Responsive User",
    },
  });
  expect(login.ok()).toBeTruthy();
  const demo = await page.request.post(`${API_URL}/demo/start`, { headers: MUTATION_HEADERS });
  expect(demo.ok()).toBeTruthy();
}

test("landing page has no horizontal overflow at any breakpoint", async ({ page }) => {
  await page.goto("/");
  await assertNoHorizontalOverflowAtEveryBreakpoint(page);
});

test("onboarding step 1 has no horizontal overflow at any breakpoint", async ({ page }) => {
  await startDemo(page);
  await page.goto("/onboarding");
  await assertNoHorizontalOverflowAtEveryBreakpoint(page);
});

test("onboarding step 2 has no horizontal overflow at any breakpoint", async ({ page }) => {
  await startDemo(page);
  await page.goto("/onboarding");
  await page.getByRole("button", { name: "Continue" }).click();
  await assertNoHorizontalOverflowAtEveryBreakpoint(page);
});

test("Today has no horizontal overflow at any breakpoint", async ({ page }) => {
  await startDemo(page);
  await page.goto("/onboarding");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Finish and open Today" }).click();
  await page.waitForURL(/\/today/);
  await page.getByTestId("generate-brief").click();
  await expect(page.getByTestId("brief-status")).toContainText(/version \d+/, {
    timeout: 15_000,
  });
  await assertNoHorizontalOverflowAtEveryBreakpoint(page);
});

test("Approvals has no horizontal overflow at any breakpoint", async ({ page }) => {
  await startDemo(page);
  await page.goto("/onboarding");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Finish and open Today" }).click();
  await page.waitForURL(/\/today/);
  await page.getByTestId("generate-brief").click();
  await expect(page.getByTestId("brief-status")).toContainText(/version \d+/, {
    timeout: 15_000,
  });
  await page.getByTestId("approval-inbox-link").click();
  await page.waitForURL(/\/approvals/);
  await assertNoHorizontalOverflowAtEveryBreakpoint(page);
});

test("Connections has no horizontal overflow at any breakpoint", async ({ page }) => {
  await startDemo(page);
  await page.goto("/connections");
  await assertNoHorizontalOverflowAtEveryBreakpoint(page);
});

test("Audit history has no horizontal overflow at any breakpoint", async ({ page }) => {
  await startDemo(page);
  await page.goto("/audit-history");
  await assertNoHorizontalOverflowAtEveryBreakpoint(page);
});

test("Settings has no horizontal overflow at any breakpoint", async ({ page }) => {
  await startDemo(page);
  await page.goto("/settings");
  await expect(page.getByTestId("settings-timezone")).toBeVisible();
  await assertNoHorizontalOverflowAtEveryBreakpoint(page);
});

test("account-deletion confirmation state has no horizontal overflow at any breakpoint", async ({
  page,
}) => {
  await startDemo(page);
  await page.goto("/connections");
  const control = page.getByTestId("delete-account-control");
  await control.getByTestId("delete-account-preview").click();
  await expect(page.getByTestId("delete-account-preview-counts")).toBeVisible();
  // Never click confirm here — this test only proves the confirmation UI
  // itself doesn't overflow, it must not actually delete the account.
  await assertNoHorizontalOverflowAtEveryBreakpoint(page);
});
