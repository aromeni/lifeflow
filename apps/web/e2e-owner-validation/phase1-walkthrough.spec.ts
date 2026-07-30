import { expect, test, type Page } from "@playwright/test";

// Stage 11A Phase 1 owner-operated walkthrough (docs/delivery/
// stage-11a-phase-1-plan.md). Drives the real running application, exactly
// as an owner would, through every journey required for the manual
// walkthrough evidence — capturing a screenshot at each key state so the
// resulting observations in manual-walkthrough.md are grounded in what was
// actually seen, not assumed. Synthetic demo data only; no real Google
// account. Screenshots land in test-results/ (already gitignored) and are
// never committed — only the written summary is.

const API_URL = "http://localhost:8010";
const MUTATION_HEADERS = { "X-LifeFlow-CSRF": "1" };

async function signInAndStartDemo(page: Page): Promise<string> {
  await page.goto("/");
  const login = await page.request.post(`${API_URL}/auth/dev-login`, {
    headers: MUTATION_HEADERS,
    data: {
      email: `owner-walkthrough-${Date.now()}@lifeflow-owner-validation.example`,
      display_name: "Owner Walkthrough",
    },
  });
  expect(login.ok()).toBeTruthy();
  const demo = await page.request.post(`${API_URL}/demo/start`, { headers: MUTATION_HEADERS });
  expect(demo.ok()).toBeTruthy();
  return (await login.json()).user_id as string;
}

test("Stage 11A Phase 1 — full owner-operated synthetic walkthrough", async ({ page }, testInfo) => {
  test.setTimeout(120_000);

  // 1. Landing page.
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("01-landing.png"), fullPage: true });

  await signInAndStartDemo(page);

  // 2. Onboarding.
  await page.goto("/onboarding");
  await expect(page.getByRole("heading", { name: "Set up your demo" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("02-onboarding-step1.png"), fullPage: true });
  await page.getByRole("button", { name: "Continue" }).click();
  await page.screenshot({ path: testInfo.outputPath("03-onboarding-step2.png"), fullPage: true });
  await page.getByRole("button", { name: "Finish and open Today" }).click();
  await expect(page).toHaveURL(/\/today/);

  // 3. Today — before brief generation.
  await page.screenshot({ path: testInfo.outputPath("04-today-empty.png"), fullPage: true });

  // 4. Generate the brief; every category should render.
  await page.getByTestId("generate-brief").click();
  await expect(page.getByTestId("brief-status")).toContainText(/version 1 · complete/, {
    timeout: 15_000,
  });
  await page.screenshot({ path: testInfo.outputPath("05-today-with-brief.png"), fullPage: true });

  // 5. Evidence inspection.
  const firstDrawer = page.getByText(/Evidence \(\d+ source/).first();
  await firstDrawer.click();
  await expect(page.getByText(/ref (em|ev)-\d+/).first()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("06-evidence-open.png"), fullPage: true });

  // 6. Approvals — open the inbox.
  await page.getByTestId("approval-inbox-link").click();
  await expect(page.getByRole("heading", { name: "Approval inbox" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("07-approvals-inbox.png"), fullPage: true });

  // 7. Gmail draft proposal — inspect exact payload preview.
  const draft = page.getByTestId("proposal-create_gmail_draft");
  await expect(draft).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("08-gmail-proposal.png"), fullPage: true });

  // 8. Task proposal — approve, then execute (simulation).
  const task = page.getByTestId("proposal-create_task");
  await task.getByRole("button", { name: "Approve exact payload" }).click();
  await expect(page.getByTestId("proposal-status-create_task")).toHaveText("approved");
  await page.screenshot({ path: testInfo.outputPath("09-proposal-approved.png"), fullPage: true });
  await task.getByRole("button", { name: "Run approved simulation" }).click();
  await expect(page.getByTestId("proposal-status-create_task")).toHaveText("executed");
  await page.screenshot({ path: testInfo.outputPath("10-proposal-executed.png"), fullPage: true });

  // 9. Calendar proposal — reject.
  const calendar = page.getByTestId("proposal-create_calendar_event");
  await calendar.getByRole("button", { name: "Reject" }).click();
  await expect(page.getByTestId("proposal-status-create_calendar_event")).toHaveText("rejected");
  await page.screenshot({ path: testInfo.outputPath("11-proposal-rejected.png"), fullPage: true });

  // 10. Audit History — wait for real entries (not the loading state) so
  // the screenshot shows the plain-language lifecycle events this proposal
  // sequence just produced, per e2e/audit-history.spec.ts's own pattern.
  await page.goto("/audit-history");
  await expect(page.getByRole("heading", { name: "Audit history", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Action rejected" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("12-audit-history.png"), fullPage: true });

  // 11. Connections. Demo mode connects a "synthetic" provider account, not
  // a "google" one, so the Google card correctly reads "Not connected" (the
  // real-Google connect/sync/execute journey is exercised separately,
  // per e2e/connections.spec.ts and test_google_route_integration.py) and
  // imported-data deletion is correctly unavailable — its own copy says
  // "Connect and sync an account to enable imported-data deletion," which
  // is accurate: there is no real external provider relationship for a
  // synthetic account to separately disconnect-then-clean-up. Full account
  // deletion is unconditional and still available.
  await page.goto("/connections");
  await expect(page.getByTestId("google-connection-card")).toContainText("Not connected");
  await expect(page.getByTestId("delete-imported-unavailable")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("13-connections.png"), fullPage: true });

  const accountControl = page.getByTestId("delete-account-control");
  await accountControl.getByTestId("delete-account-preview").click();
  await expect(page.getByTestId("delete-account-preview-counts")).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("14-account-deletion-preview.png"),
    fullPage: true,
  });
  // Confirm button stays disabled without the exact phrase — never completed
  // in this walkthrough (the automated reset-repeatability harness already
  // proves full completion; ending the session here would truncate the walk).
  await expect(page.getByTestId("delete-account-confirm")).toBeDisabled();

  // 12. Settings — memory/preferences area (expected empty in a fresh demo
  // session: no edited-then-approved draft has occurred yet to infer from).
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("15-settings.png"), fullPage: true });
});
