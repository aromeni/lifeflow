import { expect, test, type Page } from "@playwright/test";

// Stage 9 Delivery Phase 3 browser journey. It uses a fresh synthetic demo
// owner, the real API and PostgreSQL, and the canonical Privacy & Connections
// link. No provider credentials or external side effects are involved.

const API_URL = "http://localhost:8010";
const MUTATION_HEADERS = { "X-LifeFlow-CSRF": "1" };
const PRIVATE_REJECTION_REASON = "SENTINEL-private-rejection-reason";

type Proposal = {
  id: string;
  version: number;
  status: string;
};

async function prepareHistory(page: Page) {
  await page.goto("/");
  const login = await page.request.post(`${API_URL}/auth/dev-login`, {
    headers: MUTATION_HEADERS,
    data: {
      email: `playwright-audit-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      display_name: "Playwright Audit History",
    },
  });
  expect(login.ok()).toBeTruthy();

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
}

test("owner reviews privacy-safe audit history from Privacy & Connections", async ({ page }) => {
  await prepareHistory(page);

  await page.goto("/connections");
  await expect(page.getByRole("heading", { name: "Privacy & Connections" })).toBeVisible();
  await page.getByTestId("audit-history-link").click();

  await expect(page).toHaveURL(/\/audit-history$/);
  await expect(page.getByRole("heading", { name: "Audit history", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Action rejected" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Brief generated" })).toBeVisible();
  await expect(page.getByText(PRIVATE_REJECTION_REASON)).toHaveCount(0);
  await expect(page.getByText(/safe_metadata|correlation_id|entity_id/i)).toHaveCount(0);

  // Closed filters replace the visible window without exposing raw event data.
  await page.getByLabel("Activity").selectOption("actions");
  await expect(page.getByRole("heading", { name: "Action rejected" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Brief generated" })).toHaveCount(0);

  await page.getByLabel("Time period").selectOption("30d");
  await expect(page.getByRole("heading", { name: "Action rejected" })).toBeVisible();

  await page.getByRole("link", { name: "Privacy & Connections" }).click();
  await expect(page).toHaveURL(/\/connections$/);
  await expect(page.getByTestId("audit-history-link")).toBeVisible();
});
