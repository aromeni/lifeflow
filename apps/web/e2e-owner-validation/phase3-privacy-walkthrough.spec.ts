import { expect, test, type Page } from "@playwright/test";

// Stage 11A Phase 3 (docs/delivery/stage-11a-phase-3-plan.md), scenario
// S11A-P3-025/044: an owner-operated browser-privacy walkthrough. Phase 1's
// and Phase 2's owner walkthroughs already screenshotted the functional UI
// extensively; this spec asks a question neither of them did — what does
// the real browser actually hold in storage, print to console, and receive
// over the network — at every key screen of a real session. Synthetic demo
// data only; runs against the same plain demo stack as the other owner-
// validation walkthroughs (port 8010/3000). Screenshots land in
// test-results/ (already gitignored) and are never committed.

const API_URL = "http://localhost:8010";
const MUTATION_HEADERS = { "X-LifeFlow-CSRF": "1" };

interface StorageSnapshot {
  localStorageKeys: string[];
  sessionStorageKeys: string[];
  documentCookie: string;
  indexedDbNames: string[];
}

async function snapshotStorage(page: Page): Promise<StorageSnapshot> {
  return page.evaluate(async () => {
    let indexedDbNames: string[] = [];
    if ("databases" in indexedDB) {
      const dbs = await (
        indexedDB as IDBFactory & {
          databases: () => Promise<{ name?: string }[]>;
        }
      ).databases();
      indexedDbNames = dbs.map((d) => d.name ?? "").filter(Boolean);
    }
    return {
      localStorageKeys: Object.keys(window.localStorage),
      sessionStorageKeys: Object.keys(window.sessionStorage),
      documentCookie: document.cookie,
      indexedDbNames,
    };
  });
}

// `next dev`'s own HMR/error-overlay tooling writes a random per-session
// channel id under this key — confirmed (by repository-wide grep) to come
// from Next.js's dev-server internals, never LifeFlow application code, and
// confirmed absent from a production build (`next build && next start`
// never runs the dev overlay). Allowlisted here by exact prefix so any
// *other*, unexpected sessionStorage key still fails this assertion.
const NEXT_DEV_INTERNAL_SESSION_STORAGE_PREFIX = "__next_debug_channel:";

function assertStorageIsEmpty(snapshot: StorageSnapshot, label: string): void {
  expect(snapshot.localStorageKeys, `localStorage at ${label}`).toEqual([]);
  const unexpectedSessionKeys = snapshot.sessionStorageKeys.filter(
    (key) => !key.startsWith(NEXT_DEV_INTERNAL_SESSION_STORAGE_PREFIX),
  );
  expect(
    unexpectedSessionKeys,
    `sessionStorage at ${label} (excluding next-dev internals)`,
  ).toEqual([]);
  expect(snapshot.indexedDbNames, `IndexedDB at ${label}`).toEqual([]);
  // The only cookie this app ever sets is `lifeflow_session`, and it is
  // httpOnly — genuinely invisible to JavaScript. An empty `document.cookie`
  // here is not an oversight to fix; it is the expected, correct state,
  // and this assertion is what proves it rather than assumes it.
  expect(snapshot.documentCookie, `document.cookie at ${label}`).toBe("");
}

async function signInAndStartDemo(page: Page): Promise<void> {
  await page.goto("/");
  const login = await page.request.post(`${API_URL}/auth/dev-login`, {
    headers: MUTATION_HEADERS,
    data: {
      email: `privacy-walkthrough-${Date.now()}@lifeflow-owner-validation.example`,
      display_name: "Privacy Walkthrough",
    },
  });
  expect(login.ok()).toBeTruthy();
  const demo = await page.request.post(`${API_URL}/demo/start`, { headers: MUTATION_HEADERS });
  expect(demo.ok()).toBeTruthy();
}

test("Stage 11A Phase 3 — owner-operated browser-privacy walkthrough", async ({
  page,
}, testInfo) => {
  test.setTimeout(120_000);

  const consoleMessages: string[] = [];
  page.on("console", (msg) => consoleMessages.push(msg.text()));
  const pageErrors: string[] = [];
  page.on("pageerror", (err) => pageErrors.push(err.message));

  // 1. Landing page — before any session exists.
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  assertStorageIsEmpty(await snapshotStorage(page), "landing (no session)");

  await signInAndStartDemo(page);

  // 2. Onboarding.
  await page.goto("/onboarding");
  await expect(page.getByRole("heading", { name: "Set up your demo" })).toBeVisible();
  assertStorageIsEmpty(await snapshotStorage(page), "onboarding");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Finish and open Today" }).click();
  await expect(page).toHaveURL(/\/today/);

  // 3. Today — generate the real brief, inspect storage after real data
  // exists (the highest-risk moment for anything to have been cached
  // client-side).
  await page.getByTestId("generate-brief").click();
  await expect(page.getByTestId("brief-status")).toContainText(/version 1 · complete/, {
    timeout: 15_000,
  });
  assertStorageIsEmpty(await snapshotStorage(page), "Today (brief generated)");
  await page.screenshot({ path: testInfo.outputPath("01-today-privacy-checked.png") });

  // 4. Approvals inbox — the screen most likely to hold sensitive draft
  // content (Gmail draft body, calendar attendees) if anything leaked into
  // client storage.
  await page.getByTestId("approval-inbox-link").click();
  await expect(page.getByRole("heading", { name: "Approval inbox" })).toBeVisible();
  assertStorageIsEmpty(await snapshotStorage(page), "Approvals inbox");
  await page.screenshot({ path: testInfo.outputPath("02-approvals-privacy-checked.png") });

  // 5. Audit History.
  await page.goto("/audit-history");
  await expect(page.getByRole("heading", { name: "Audit history", exact: true })).toBeVisible();
  assertStorageIsEmpty(await snapshotStorage(page), "Audit History");

  // 6. Connections — the screen's own `load()` fetches `GET /privacy/summary`
  // (confirmed by reading connections/page.tsx; it never calls
  // `/connected-accounts` directly), already proven token-field-free at the
  // API level (test_stage11a_phase3_api_minimisation.py); spot-check the
  // same property through a real browser network response.
  const privacySummaryResponse = page.waitForResponse(
    (resp) => resp.url().includes("/privacy/summary") && resp.request().method() === "GET",
  );
  await page.goto("/connections");
  const response = await privacySummaryResponse;
  const body = await response.text();
  expect(body).not.toContain("encrypted_access_token");
  expect(body).not.toContain("encrypted_refresh_token");
  expect(body).not.toContain("authorisation_revision");
  assertStorageIsEmpty(await snapshotStorage(page), "Connections");
  await page.screenshot({ path: testInfo.outputPath("03-connections-privacy-checked.png") });

  // 7. Settings.
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  assertStorageIsEmpty(await snapshotStorage(page), "Settings");

  // 8. Logout, then revisit a protected route — confirm the session is
  // truly gone (no stale client-side cache lets a protected page render
  // without the server's own authentication check).
  const logoutResponse = await page.request.post(`${API_URL}/auth/logout`, {
    headers: MUTATION_HEADERS,
  });
  expect(logoutResponse.ok()).toBeTruthy();
  await page.goto("/today");
  assertStorageIsEmpty(await snapshotStorage(page), "post-logout revisit");
  await page.screenshot({ path: testInfo.outputPath("04-post-logout-privacy-checked.png") });

  // 9. Console/error hygiene across the entire walkthrough.
  const sensitivePatterns = ["access_token", "refresh_token", "encrypted_", "session=", "Bearer "];
  for (const message of consoleMessages) {
    for (const pattern of sensitivePatterns) {
      expect(message, `console message contained "${pattern}"`).not.toContain(pattern);
    }
  }
  expect(pageErrors, "uncaught page errors during the walkthrough").toEqual([]);
});
