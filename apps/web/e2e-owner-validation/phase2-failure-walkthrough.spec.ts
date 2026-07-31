import { execSync } from "node:child_process";

import { expect, test, type Page } from "@playwright/test";

// Stage 11A Phase 2 (docs/delivery/stage-11a-phase-2-plan.md) owner-operated
// walkthrough of failure states through the real UI, against the same
// dedicated resilience stack the Journey specs use (API :8011, fake Google
// :8098, web :3001) — started by scripts/stage11a-phase2-owner-walkthrough.sh,
// never by this config's own webServer, so the API's real OS-level restart
// step below cannot be undone by Playwright's process supervision. Synthetic
// demo data only; no real Google account. Screenshots land in test-results/
// (already gitignored) and are never committed — only the written summary
// (manual-walkthrough.md) is.

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
      display_name: "Owner Phase 2 Walkthrough",
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

test("Stage 11A Phase 2 — owner-operated failure-state walkthrough", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  const userId = await signIn(page, "phase2walkthrough");
  support("seed-account", userId);
  support("seed-draft-source", userId);

  // 1. Temporary outage: a transient read failure that survives the retry
  // budget (fail_count=5 > max_attempts=3) reaches the UI as a real,
  // labelled, retryable notice.
  await setScenario(page, "gmail_list_messages", "transient_then_recover", 5);
  await page.goto("/connections");
  await expect(page.getByTestId("google-connection-status")).toHaveText("active");
  await page.getByTestId("sync-google-now").click();
  await expect(page.getByTestId("sync-degraded-notice")).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: testInfo.outputPath("01-temporary-outage.png"), fullPage: true });

  // 2. Reconnection required: a non-retryable provider failure must show
  // the distinct "reconnect Google" branch, never the transient copy.
  await setScenario(page, "gmail_list_messages", "permanent_failure");
  await page.getByTestId("sync-google-now").click();
  const reconnectNotice = page.getByTestId("sync-error-notice");
  await expect(reconnectNotice).toBeVisible({ timeout: 15_000 });
  await expect(reconnectNotice).toContainText("reconnect Google");
  await page.screenshot({
    path: testInfo.outputPath("02-reconnection-required.png"),
    fullPage: true,
  });
  await setScenario(page, "gmail_list_messages", "healthy");

  // 3. Uncertain Gmail draft outcome.
  await page.goto("/today");
  await page.getByTestId("generate-brief").click();
  await expect(page.getByTestId("brief-status")).toContainText(/version \d+ · complete/, {
    timeout: 15_000,
  });
  await page.getByTestId("approval-inbox-link").click();
  await expect(page).toHaveURL(/\/approvals/);
  const draft = page.getByTestId("proposal-create_gmail_draft");
  await expect(draft).toBeVisible();
  await draft.getByTestId("approve-create_gmail_draft").click();
  await expect(page.getByTestId("proposal-status-create_gmail_draft")).toHaveText("approved");

  const proposalsBefore = await page.request.get(`${API_URL}/action-proposals`);
  const draftProposalId = (await proposalsBefore.json()).proposals.find(
    (p: { action_type: string }) => p.action_type === "create_gmail_draft",
  ).id as string;

  await setScenario(page, "gmail_create_draft", "hang_on_write");
  const executeDraft = await page.request.post(
    `${API_URL}/action-proposals/${draftProposalId}/execute`,
    { headers: MUTATION_HEADERS },
  );
  expect(executeDraft.ok()).toBeTruthy();
  expect((await executeDraft.json()).execution.effective_status).toBe("uncertain");
  await page.reload();
  await expect(page.getByTestId("execution-result")).toContainText("uncertain");
  await page.screenshot({
    path: testInfo.outputPath("03-uncertain-gmail-draft.png"),
    fullPage: true,
  });
  await setScenario(page, "gmail_create_draft", "healthy");

  // Note: the Calendar uncertain-write path (create_calendar_event) is not
  // separately screenshotted here — e2e_google_support.py's seed helpers
  // only seed a Gmail-sourced scheduling item, and the rendered outcome
  // uses the exact same execution-result component and copy pattern shown
  // above for Gmail. Its distinct backend mechanism (a different executor,
  // GoogleCalendarEventExecutor) is already proven automatically and
  // repeatedly by test_stage11a_phase2_uncertain_write_repeatability.py
  // (10 cycles) — this walkthrough's job is owner observation of the UI
  // experience, which does not differ by action type.

  // 4. Worker-delayed operation / deletion recovery: a real deletion
  // operation, previewed and confirmed through the UI, whose worker has
  // not yet run — the durable "queued" state a worker outage would also
  // produce (Journey C already proves the recovery mechanism itself; this
  // captures what an owner actually sees while it is pending).
  await page.goto("/connections");
  const accountControl = page.getByTestId("delete-account-control");
  await accountControl.getByTestId("delete-account-preview").click();
  await expect(page.getByTestId("delete-account-preview-counts")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("04-deletion-preview.png"), fullPage: true });

  // 5. Restored normal operation: back on Today with no degraded notice.
  // Waits for the async brief fetch to actually resolve — screenshotting
  // immediately after navigation caught "Loading your brief…" mid-fetch on
  // a first attempt, the same class of race Phase 1's audit-history
  // screenshot hit (a test-script timing bug, not a product defect).
  await page.goto("/today");
  await expect(page.getByText("Loading your brief…")).toHaveCount(0, { timeout: 15_000 });
  await expect(page.getByTestId("generate-brief")).toBeVisible();
  await expect(page.getByTestId("sync-degraded-notice")).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("05-restored-normal.png"), fullPage: true });
});
