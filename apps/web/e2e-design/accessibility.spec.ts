import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

const API_URL = "http://localhost:8010";
const MUTATION_HEADERS = { "X-LifeFlow-CSRF": "1" };

// Stage 10 §15: automated coverage using the repository's approved
// lightweight approach (axe-core's Playwright binding — no bespoke rule
// engine, no new CI infrastructure). This is a floor, not a certification:
// axe-core catches a meaningful subset of WCAG 2.2 failures (missing
// labels, contrast, landmark/heading structure, focus-visible regressions)
// but cannot verify genuine screen-reader usability, real keyboard-only
// task completion, or reduced-motion/zoom behaviour — those remain manual
// checks (see docs/delivery/reports/stage-10.md, "Accessibility
// verification"). Do not read a clean run here as WCAG certification.
async function expectNoSeriousViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical",
  );
  if (serious.length > 0) {
    console.log(JSON.stringify(serious, null, 2));
  }
  expect(serious, `Serious/critical accessibility violations on ${page.url()}`).toEqual([]);
}

async function startDemo(page: Page) {
  await page.goto("/");
  const login = await page.request.post(`${API_URL}/auth/dev-login`, {
    headers: MUTATION_HEADERS,
    data: {
      email: `playwright-a11y-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      display_name: "Accessibility User",
    },
  });
  expect(login.ok()).toBeTruthy();
  const demo = await page.request.post(`${API_URL}/demo/start`, { headers: MUTATION_HEADERS });
  expect(demo.ok()).toBeTruthy();
}

test("landing page has no serious accessibility violations", async ({ page }) => {
  await page.goto("/");
  await expectNoSeriousViolations(page);
});

test("onboarding (both steps) has no serious accessibility violations", async ({ page }) => {
  await startDemo(page);
  await page.goto("/onboarding");
  await expectNoSeriousViolations(page);
  await page.getByRole("button", { name: "Continue" }).click();
  await expectNoSeriousViolations(page);
});

test("Today has no serious accessibility violations", async ({ page }) => {
  await startDemo(page);
  await page.goto("/onboarding");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Finish and open Today" }).click();
  await page.waitForURL(/\/today/);
  await page.getByTestId("generate-brief").click();
  await expect(page.getByTestId("brief-status")).toContainText(/version \d+/, {
    timeout: 15_000,
  });
  await expectNoSeriousViolations(page);
});

test("Approvals has no serious accessibility violations", async ({ page }) => {
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
  await expectNoSeriousViolations(page);
});

test("Connections has no serious accessibility violations", async ({ page }) => {
  await startDemo(page);
  await page.goto("/connections");
  await expectNoSeriousViolations(page);
});

test("Audit history has no serious accessibility violations", async ({ page }) => {
  await startDemo(page);
  await page.goto("/audit-history");
  await expectNoSeriousViolations(page);
});

test("Settings has no serious accessibility violations", async ({ page }) => {
  await startDemo(page);
  await page.goto("/settings");
  await expect(page.getByTestId("settings-timezone")).toBeVisible();
  await expectNoSeriousViolations(page);
});

test("keyboard-only: landing page primary action is reachable and activatable by keyboard", async ({
  page,
}) => {
  await page.goto("/");
  // Under load (running after many prior tests in the same suite), the
  // server-rendered button text is paintable before React finishes
  // hydrating its onClick handler — tabbing to it and pressing Enter too
  // early activates nothing, so `waitForURL` below hangs to its full
  // timeout. Waiting for the network to settle first reliably closes that
  // hydration race (reproduced twice running the full suite; never in
  // isolation, which is what mistakenly hid it before).
  await page.waitForLoadState("networkidle");
  // Tab from the top of the document until the demo button is focused —
  // proves it sits in a sane, reachable tab order, not just that it exists.
  let reached = false;
  for (let i = 0; i < 15; i++) {
    await page.keyboard.press("Tab");
    const active = await page.evaluate(() => document.activeElement?.textContent?.trim());
    if (active?.includes("Try demo")) {
      reached = true;
      break;
    }
  }
  expect(reached).toBe(true);
  await page.keyboard.press("Enter");
  await page.waitForURL(/\/onboarding/);
});

test("reduced motion: transitions are disabled when the user prefers reduced motion", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  const duration = await page.evaluate(() => {
    const button = document.querySelector("button");
    if (!button) return null;
    return getComputedStyle(button).transitionDuration;
  });
  // globals.css forces a ~0 transition duration under prefers-reduced-motion.
  // Chromium reports sub-millisecond durations in scientific notation
  // (e.g. "1e-06s"), so parse the number rather than string-matching it.
  expect(duration).not.toBeNull();
  expect(Number.parseFloat(duration as string)).toBeLessThan(0.001);
});
