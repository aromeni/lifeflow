import { execSync } from "node:child_process";

import { expect, test, type Page } from "@playwright/test";

// Stage 9 Delivery Phase 3 browser journey. It uses a fresh synthetic demo
// owner, the real API, a real ARQ worker, and real PostgreSQL, and the
// canonical Privacy & Connections link. No provider credentials or external
// side effects are involved.

const API_URL = "http://localhost:8010";
const MUTATION_HEADERS = { "X-LifeFlow-CSRF": "1" };
const PRIVATE_REJECTION_REASON = "SENTINEL-private-rejection-reason";
// Playwright runs from apps/web; the support script lives in apps/api.
const API_DIR = "../api";
const TERMINAL_TIMEOUT = 120_000; // worker drains on its <=60s cron, then processes

type Proposal = {
  id: string;
  version: number;
  status: string;
};

function support(command: string, userId: string): string {
  return execSync(`uv run python scripts/e2e_deletion_support.py ${command} ${userId}`, {
    cwd: API_DIR,
    encoding: "utf8",
    env: { ...process.env, LIFEFLOW_E2E: "1" },
  });
}

async function prepareHistory(page: Page): Promise<string> {
  await page.goto("/");
  const login = await page.request.post(`${API_URL}/auth/dev-login`, {
    headers: MUTATION_HEADERS,
    data: {
      email: `playwright-audit-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      display_name: "Playwright Audit History",
    },
  });
  expect(login.ok()).toBeTruthy();
  const userId = (await login.json()).user_id as string;

  const demo = await page.request.post(`${API_URL}/demo/start`, {
    headers: MUTATION_HEADERS,
  });
  expect(demo.ok()).toBeTruthy();
  const brief = await page.request.post(`${API_URL}/briefs/generate`, {
    headers: MUTATION_HEADERS,
  });
  expect(brief.ok()).toBeTruthy();

  const proposals = await page.request.get(`${API_URL}/action-proposals`);
  expect(proposals.ok()).toBeTruthy();
  const proposal = ((await proposals.json()).proposals as Proposal[])[0];
  expect(proposal).toBeDefined();
  const rejection = await page.request.post(`${API_URL}/action-proposals/${proposal.id}/reject`, {
    headers: MUTATION_HEADERS,
    data: {
      expected_version: proposal.version,
      reason: PRIVATE_REJECTION_REASON,
    },
  });
  expect(rejection.ok()).toBeTruthy();

  return userId;
}

test("owner reviews privacy-safe audit history from Privacy & Connections", async ({ page }) => {
  test.setTimeout(180_000);
  const userId = await prepareHistory(page);

  // A real, completed imported-data deletion (same synthetic seed/flow as
  // deletion.spec.ts Journey A) so the audit-history timeline has a genuine
  // completed event carrying real, validated aggregate counts to display.
  support("seed-imported", userId); // synthetic google (3 items) + secondary (1 item)
  await page.goto("/connections");
  await expect(page.getByTestId("google-connection-status")).toHaveText("active");
  await page.getByTestId("delete-imported-preview").click();
  await expect(page.getByTestId("delete-imported-preview-counts")).toContainText("3");
  await page.getByTestId("delete-imported-confirm-input").fill("DELETE IMPORTED DATA");
  await page.getByTestId("delete-imported-confirm").click();
  await expect(
    page.getByTestId("delete-imported-control").getByTestId("operation-status"),
  ).toContainText(/Done\. The data has been deleted\./, { timeout: TERMINAL_TIMEOUT });

  await page.goto("/connections");
  await expect(page.getByRole("heading", { name: "Privacy & Connections" })).toBeVisible();
  await page.getByTestId("audit-history-link").click();

  await expect(page).toHaveURL(/\/audit-history$/);
  await expect(page.getByRole("heading", { name: "Audit history", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Action rejected" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Brief generated" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Imported-data deletion completed" }),
  ).toBeVisible();
  await expect(page.getByText(PRIVATE_REJECTION_REASON)).toHaveCount(0);
  await expect(page.getByText(/safe_metadata|correlation_id|entity_id/i)).toHaveCount(0);

  // The rejected proposal carries a safe, closed action-type label alongside
  // its title — never the raw wire-format action type.
  const rejectedItem = page
    .getByRole("heading", { name: "Action rejected" })
    .locator("xpath=ancestor::li[1]");
  await expect(rejectedItem.getByTestId("audit-action-type")).toHaveText(
    /^(Task|Gmail draft|Calendar event)$/,
  );
  await expect(page.getByText(/create_task|create_gmail_draft|create_calendar_event/)).toHaveCount(
    0,
  );

  // The completed deletion shows validated, safe aggregate counts — the
  // exact seeded total (3 google source items) — never a raw category
  // breakdown, operation id, or scope descriptor.
  const deletionItem = page
    .getByRole("heading", { name: "Imported-data deletion completed" })
    .locator("xpath=ancestor::li[1]");
  await expect(deletionItem.getByTestId("audit-counts")).toContainText("3 records deleted");
  await expect(page.getByText(/source_items|deleted_counts|account:/i)).toHaveCount(0);

  // Closed filters replace the visible window without exposing raw event data.
  await page.getByLabel("Activity").selectOption("actions");
  await expect(page.getByRole("heading", { name: "Action rejected" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Brief generated" })).toHaveCount(0);

  await page.getByLabel("Time period").selectOption("30d");
  await expect(page.getByRole("heading", { name: "Action rejected" })).toBeVisible();

  await page.getByTestId("connections-link").click();
  await expect(page).toHaveURL(/\/connections$/);
  await expect(page.getByTestId("audit-history-link")).toBeVisible();
});
