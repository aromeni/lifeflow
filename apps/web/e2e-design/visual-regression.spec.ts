import { expect, type Page, test } from "@playwright/test";

// Stage 10 §16: a deliberately small set of pixel baselines for the highest-
// value screens, not a screenshot for every state — per-state pixel snapshots
// for every permutation would be exactly the "excessive pixel-snapshot
// overhead" the spec warns against, and most regressions (spacing, contrast,
// token drift) are already caught by the manual visual-review passes plus
// the responsive/accessibility suites. `toHaveScreenshot` freezes CSS
// animations/transitions by default; the only remaining non-determinism is
// server-rendered timestamps, which are masked below via their data-testid
// or the semantic <time> element rather than by hiding whole sections, so
// the design (badges, buttons, layout, colour) is still fully covered by the
// pixel diff.
//
// Baselines live in e2e/visual-regression.spec.ts-snapshots/ and were
// generated on this machine (Playwright's Chromium build). Regenerate with
// `npx playwright test e2e/visual-regression.spec.ts --update-snapshots`
// whenever an intentional visual change lands; review the new PNGs as part
// of that change's diff.

const API_URL = "http://localhost:8010";
const MUTATION_HEADERS = { "X-LifeFlow-CSRF": "1" };

// Next.js's own dev-mode overlay button (`pnpm dev`, never present in a
// production build) floats over every page at a fixed corner position and
// its badge/indicator state isn't fully deterministic run-to-run — masked
// on every baseline below since it's build tooling, not product UI, and
// its small pixel churn was intermittently failing baselines that were
// otherwise perfectly stable (see docs/delivery/reports/stage-10.md).
function devtoolsMask(page: Page) {
  return page.getByRole("button", { name: /Next\.js Dev Tools/i });
}

async function startDemo(page: Page) {
  await page.goto("/");
  const login = await page.request.post(`${API_URL}/auth/dev-login`, {
    headers: MUTATION_HEADERS,
    data: {
      email: `playwright-visual-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      display_name: "Visual Regression User",
    },
  });
  expect(login.ok()).toBeTruthy();
  const demo = await page.request.post(`${API_URL}/demo/start`, { headers: MUTATION_HEADERS });
  expect(demo.ok()).toBeTruthy();
}

test.use({ viewport: { width: 1440, height: 900 } });

test("landing page visual baseline", async ({ page }) => {
  // The landing page fails closed (no Google button) until an async
  // GET /config resolves (ADR 0003 D23) — wait for it so the CTA row's
  // real, settled layout is captured instead of racing the fetch.
  const configLoaded = page.waitForResponse((r) => r.url().includes("/config"));
  await page.goto("/");
  await configLoaded;
  await expect(
    page.getByTestId("sign-in-with-google").or(page.getByTestId("google-sign-in-unavailable")),
  ).toBeVisible();
  await expect(page).toHaveScreenshot("landing.png", {
    fullPage: true,
    mask: [devtoolsMask(page)],
  });
});

test("onboarding step 1 visual baseline", async ({ page }) => {
  await startDemo(page);
  await page.goto("/onboarding");
  await expect(page).toHaveScreenshot("onboarding-step1.png", {
    fullPage: true,
    mask: [devtoolsMask(page)],
  });
});

test("onboarding step 2 visual baseline", async ({ page }) => {
  await startDemo(page);
  await page.goto("/onboarding");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveScreenshot("onboarding-step2.png", {
    fullPage: true,
    mask: [devtoolsMask(page)],
  });
});

test("Today with a generated brief visual baseline", async ({ page }) => {
  await startDemo(page);
  await page.goto("/onboarding");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Finish and open Today" }).click();
  await page.waitForURL(/\/today/);
  await page.getByTestId("generate-brief").click();
  await expect(page.getByTestId("brief-status")).toContainText(/version \d+/, {
    timeout: 15_000,
  });
  // Viewport-only (not fullPage): a full capture of this page is ~5500px
  // tall, which produced a >500KB PNG (repo's large-file limit) and was
  // also the one baseline sensitive to real time passing during a long
  // session (an item crossing out of "Today and upcoming" as its start
  // time arrives). The viewport already covers the header, summary strip,
  // and the top of "Needs attention" — enough to catch a badge/token/
  // layout regression — without either problem.
  await expect(page).toHaveScreenshot("today.png", {
    mask: [
      page.getByTestId("brief-status"),
      page.getByTestId("brief-item-due"),
      devtoolsMask(page),
    ],
    // Sub-pixel font-rendering jitter across this much text; a small
    // tolerance absorbs it without hiding a real layout/colour regression.
    maxDiffPixelRatio: 0.01,
  });
});

test("Approvals: a single proposal card visual baseline", async ({ page }) => {
  // The full approvals list is intentionally not screenshotted: demo
  // proposals are seeded in one batch and can tie on created_at, so their
  // relative order is not guaranteed run-to-run (repositories.py orders by
  // created_at desc, id — a fair, stable order for real usage where
  // proposals arrive at different times, but not for a same-instant seed).
  // A single, deterministically-selected card still exercises every visual
  // element that matters here: risk/status badges, notices, and the
  // Approve/Edit/Reject button hierarchy.
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
  const card = page.getByTestId("proposal-create_gmail_draft");
  await expect(card).toBeVisible();
  await expect(card).toHaveScreenshot("approvals-gmail-draft-card.png", {
    mask: [card.getByTestId("proposal-expires"), devtoolsMask(page)],
    // The masked "Expires:" text has a variable-width bounding box (the
    // rendered date string isn't always the same number of characters),
    // which shifts the mask edge by a pixel or two run-to-run.
    maxDiffPixelRatio: 0.005,
  });
});

// Named "no real Google", not "not connected": demo mode creates its own
// synthetic ConnectedAccount (provider="synthetic") to represent the
// fictional dataset, so the "Data stored by LifeFlow" and "Evidence
// freshness" sections are never empty here — only the top "Connected
// accounts" card (which filters to provider="google" specifically) reads
// "Not connected". Confirmed via a direct, unmediated GET /privacy/summary
// call for a fresh dev-login + demo user: inventory counts are correctly
// scoped to that one user, not leaked from another (see
// docs/delivery/reports/stage-10.md, "Investigation note"). The inventory
// counts and last-synced freshness text are masked below because they can
// drift by small amounts run-to-run (e.g. incidental extra audit events).
test("Connections (no real Google connected) visual baseline", async ({ page }) => {
  await startDemo(page);
  await page.goto("/connections");
  // The privacy summary loads asynchronously ("Loading your privacy
  // summary…" is the transient state) — wait for it to resolve so the
  // inventory/freshness sections have their real height before capturing,
  // rather than sometimes snapshotting mid-fetch.
  await expect(page.getByText("Loading your privacy summary…")).toHaveCount(0);
  await expect(page.getByTestId("data-inventory")).toBeVisible();
  await expect(page).toHaveScreenshot("connections.png", {
    fullPage: true,
    mask: [
      page.getByTestId("data-inventory"),
      page.getByTestId("evidence-freshness"),
      devtoolsMask(page),
    ],
  });
});

test("Audit history visual baseline", async ({ page }) => {
  await startDemo(page);
  await page.goto("/audit-history");
  await expect(page).toHaveScreenshot("audit-history.png", {
    fullPage: true,
    mask: [page.locator("time"), devtoolsMask(page)],
    // Same variable-width mask-edge effect as the Approvals card baseline.
    maxDiffPixelRatio: 0.005,
  });
});

test("Settings visual baseline", async ({ page }) => {
  await startDemo(page);
  await page.goto("/settings");
  await expect(page.getByTestId("settings-timezone")).toBeVisible();
  await expect(page).toHaveScreenshot("settings.png", {
    fullPage: true,
    // "last synced <relative time>" ticks forward every run.
    mask: [page.getByTestId("settings-evidence-freshness"), devtoolsMask(page)],
  });
});
