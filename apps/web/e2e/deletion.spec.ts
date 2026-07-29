import { execSync } from "node:child_process";

import { expect, test, type Page } from "@playwright/test";

// Stage 9 Delivery Phase 2 focused closure: real-browser proof of the two
// destructive journeys through the normal Privacy & Connections UI, against a
// real API, a real ARQ worker (started by scripts/e2e.sh), real PostgreSQL and
// Redis. The API and worker are never mocked; only synthetic fixtures are seeded
// (via the owner-scoped support script). Fresh unique dev-login users each run;
// never the real Google-connected account.

const API_URL = "http://localhost:8010";
const MUTATION_HEADERS = { "X-LifeFlow-CSRF": "1" };
// Playwright runs from apps/web; the support script lives in apps/api.
const API_DIR = "../api";
const TERMINAL_TIMEOUT = 120_000; // worker drains on its ≤60s cron, then processes

function support(command: string, userId: string): string {
  // The support script refuses to run without the explicit E2E marker and a
  // local/test database; declare the marker here so the spec is self-contained.
  return execSync(`uv run python scripts/e2e_deletion_support.py ${command} ${userId}`, {
    cwd: API_DIR,
    encoding: "utf8",
    env: { ...process.env, LIFEFLOW_E2E: "1" },
  });
}

async function signIn(page: Page, marker: string): Promise<string> {
  await page.goto("/");
  const login = await page.request.post(`${API_URL}/auth/dev-login`, {
    headers: MUTATION_HEADERS,
    data: {
      email: `pw-${marker}-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      display_name: "Playwright Deletion",
    },
  });
  expect(login.ok()).toBeTruthy();
  return (await login.json()).user_id as string;
}

test("Journey A — imported-data deletion through the real UI and worker", async ({ page }) => {
  test.setTimeout(180_000);
  const userId = await signIn(page, "impdel");
  support("seed-imported", userId); // synthetic google (3 items) + secondary (1 item)

  await page.goto("/connections");
  await expect(page.getByTestId("google-connection-status")).toHaveText("active");

  const control = page.getByTestId("delete-imported-control");

  // 3. Preview.
  await page.getByTestId("delete-imported-preview").click();
  // 4. Counts render (3 imported google source items).
  await expect(page.getByTestId("delete-imported-preview-counts")).toContainText("3");
  // 5. Provider content is described as untouched.
  await expect(page.getByTestId("delete-imported-warnings")).toContainText(
    /Gmail and Google\s+Calendar content is never touched|never deletes anything in your Gmail/i,
  );

  // 6. Wrong phrase cannot submit.
  const confirmButton = page.getByTestId("delete-imported-confirm");
  await expect(confirmButton).toBeDisabled();
  await page.getByTestId("delete-imported-confirm-input").fill("delete imported data");
  await expect(confirmButton).toBeDisabled();

  // 7. Exact phrase enables submit.
  await page.getByTestId("delete-imported-confirm-input").fill("DELETE IMPORTED DATA");
  await expect(confirmButton).toBeEnabled();

  // 8. Submit once, with a double-click guard: the button disables on the first
  // click (busy), so a rapid second click cannot create a second operation.
  let confirmRequests = 0;
  page.on("request", (r) => {
    if (/\/deletion-operations\/.*\/confirm/.test(r.url()) && r.method() === "POST")
      confirmRequests += 1;
  });
  await confirmButton.click();
  await confirmButton.click({ force: true, timeout: 2000 }).catch(() => undefined);

  // 9. Pending/running state is shown.
  const status = control.getByTestId("operation-status");
  await expect(status).toBeVisible();
  // 10-11. The real worker processes it to a terminal succeeded result.
  await expect(status).toContainText(/Done\. The data has been deleted\./, {
    timeout: TERMINAL_TIMEOUT,
  });
  expect(confirmRequests).toBe(1); // exactly one operation, despite the double-click

  // 14. Disconnect and delete controls remain distinct.
  await expect(page.getByTestId("control-disconnect")).toBeVisible();
  await expect(control).toBeVisible();

  // 12-13. Database: the selected google account's data is gone; the other
  // account's data remains (scoping proven against real PostgreSQL).
  const counts = JSON.parse(support("counts", userId));
  expect(counts.google_sources).toBe(0);
  expect(counts.secondary_sources).toBe(1);
});

test("Journey B — LifeFlow account deletion through the real UI and worker", async ({ page }) => {
  test.setTimeout(180_000);
  const userId = await signIn(page, "accdel");
  support("seed-account", userId);
  const before = JSON.parse(support("user-state", userId));
  expect(before.account_state).toBe("active");
  const originalEmail = before.email as string;

  await page.goto("/connections");
  const control = page.getByTestId("delete-account-control");

  // 1-2. Open the high-risk section and preview.
  await control.getByTestId("delete-account-preview").click();
  await expect(page.getByTestId("delete-account-preview-counts")).toBeVisible();

  // 3. Wrong phrase cannot submit.
  const confirmButton = page.getByTestId("delete-account-confirm");
  await expect(confirmButton).toBeDisabled();
  await page.getByTestId("delete-account-confirm-input").fill("delete my account");
  await expect(confirmButton).toBeDisabled();

  // 4-5. Exact phrase; submit once.
  await page.getByTestId("delete-account-confirm-input").fill("DELETE MY LIFEFLOW ACCOUNT");
  await expect(confirmButton).toBeEnabled();
  await confirmButton.click();

  // 6. Pending/running while the session is still valid.
  await expect(control.getByTestId("operation-status")).toBeVisible();

  // 7-8-10. The worker completes deletion; the client reaches the signed-out
  // experience (redirected to "/"), with no infinite polling or 401 loop.
  await page.waitForURL("http://localhost:3000/", { timeout: TERMINAL_TIMEOUT });

  // 11. The deleted session cannot reopen an authenticated page.
  const afterAuth = await page.request.get(`${API_URL}/privacy/summary`);
  expect(afterAuth.status()).toBe(401);

  // Post-deletion database verification.
  const state = JSON.parse(support("user-state", userId));
  expect(state.account_state).toBe("deleted");
  expect(state.google_subject).toBeNull();
  expect(state.deletion_subject_id).not.toBeNull();
  // Identity fields contain none of the original identity; the retained
  // placeholder email is random (derived from the deletion subject), unique,
  // non-deliverable, and not the original.
  expect(state.email).not.toBe(originalEmail);
  expect(state.email).toContain("@deleted.invalid");
  expect(state.email).toContain(String(state.deletion_subject_id));
  // Tokens/cursors + personal product data gone.
  expect(state.connected_accounts).toBe(0);
  expect(state.source_items).toBe(0);
  // Retained tombstones exist and contain no prohibited content.
  expect(state.audit_events).toBeGreaterThan(0);
  expect(state.audit_metadata_blob).not.toContain(originalEmail);
  expect(state.audit_metadata_blob).not.toContain("@");
});
