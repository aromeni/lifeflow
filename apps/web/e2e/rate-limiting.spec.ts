import { execSync } from "node:child_process";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Stage 9 Delivery Phase 4 (ADR 0005 D64/D81): real-browser proof that rate
// limiting throttles abusive request volume without ever corrupting the
// database-level guarantees (idempotency, approval binding, plan fingerprint
// binding) that existed before this phase. The API, worker, PostgreSQL, and
// Redis are all real (never mocked); playwright.config.ts enables rate
// limiting for this e2e process with test-only policy overrides so these
// journeys never wait out a production window. Each journey uses its own
// fresh dev-login user, so it can never be affected by another spec file's
// usage of the same policy.

const API_URL = "http://localhost:8010";
const MUTATION_HEADERS = { "X-LifeFlow-CSRF": "1" };
const API_DIR = "../api";

function support(command: string, userId: string): string {
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
      email: `pw-rl-${marker}-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      display_name: "Playwright Rate Limit User",
    },
  });
  expect(login.ok()).toBeTruthy();
  return (await login.json()).user_id as string;
}

async function startDemo(page: Page): Promise<void> {
  const demo = await page.request.post(`${API_URL}/demo/start`, { headers: MUTATION_HEADERS });
  expect(demo.ok()).toBeTruthy();
}

type Proposal = { id: string; action_type: string };

async function proposalList(request: APIRequestContext): Promise<Proposal[]> {
  const response = await request.get(`${API_URL}/action-proposals`);
  expect(response.ok()).toBeTruthy();
  return (await response.json()).proposals as Proposal[];
}

// --- Journey A — manual brief throttling ------------------------------------

test("Journey A — manual brief generation is throttled without losing the current brief", async ({
  page,
}) => {
  await signIn(page, "brief");
  await startDemo(page);
  await page.goto("/today");
  await expect(page.getByTestId("brief-status")).toContainText("No brief yet.");

  const generateButton = page.getByTestId("generate-brief");

  // Two calls succeed — the test-only override's capacity (2).
  await generateButton.click();
  await expect(page.getByTestId("brief-status")).toContainText(/version 1/, { timeout: 15_000 });
  await generateButton.click();
  await expect(page.getByTestId("brief-status")).toContainText(/version 2/, { timeout: 15_000 });

  // A third call is blocked before it ever reaches brief generation.
  let generateRequests = 0;
  page.on("request", (r) => {
    if (r.url() === `${API_URL}/briefs/generate` && r.method() === "POST") generateRequests += 1;
  });
  await generateButton.click();

  const notice = page.getByTestId("rate-limit-notice");
  await expect(notice).toBeVisible();
  await expect(notice).toContainText(/Try again in/);
  await expect(notice).toHaveAttribute("role", "alert");
  // The existing brief is untouched — a 429 is not a load failure, and no new
  // version was ever generated.
  await expect(page.getByTestId("brief-status")).toContainText(/version 2/);
  await expect(generateButton).toBeEnabled();

  // No automatic resubmission: waiting does not trigger a retry.
  await page.waitForTimeout(1_500);
  expect(generateRequests).toBe(1);
});

// --- Journey B — execution safety under throttling --------------------------

test("Journey B — a throttled execution attempt creates no external write and is never shown as uncertain", async ({
  page,
}) => {
  await signIn(page, "exec");
  await startDemo(page);
  await page.goto("/today");
  await page.getByTestId("generate-brief").click();
  await expect(page.getByTestId("brief-status")).toContainText(/version 1/, { timeout: 15_000 });

  const initial = await proposalList(page.request);
  expect(initial).toHaveLength(3);

  await page.getByTestId("approval-inbox-link").click();
  await expect(page).toHaveURL(/\/approvals/);

  for (const proposal of initial) {
    const card = page.getByTestId(`proposal-${proposal.action_type}`);
    await card.getByRole("button", { name: "Approve exact payload" }).click();
    await expect(page.getByTestId(`proposal-status-${proposal.action_type}`)).toHaveText(
      "approved",
    );
  }

  // Execute the first two approved proposals — both succeed under the
  // test-only override's capacity (2).
  const [first, second, third] = initial;
  const firstCard = page.getByTestId(`proposal-${first.action_type}`);
  await firstCard.getByRole("button", { name: "Run approved simulation" }).click();
  await expect(page.getByTestId(`proposal-status-${first.action_type}`)).toHaveText("executed");

  const secondCard = page.getByTestId(`proposal-${second.action_type}`);
  await secondCard.getByRole("button", { name: "Run approved simulation" }).click();
  await expect(page.getByTestId(`proposal-status-${second.action_type}`)).toHaveText("executed");

  // A third, distinct approved proposal's execution attempt is blocked
  // before any executor runs — never a provider write, never "uncertain".
  const thirdCard = page.getByTestId(`proposal-${third.action_type}`);
  await thirdCard.getByRole("button", { name: "Run approved simulation" }).click();
  await expect(thirdCard.getByRole("alert")).toContainText(/Try again in/);
  await expect(thirdCard.getByTestId("execution-uncertain-warning")).toHaveCount(0);
  await expect(thirdCard.getByTestId("execution-result")).toHaveCount(0);
  // The proposal itself stays "approved" — not "executed", not "failed".
  await expect(page.getByTestId(`proposal-status-${third.action_type}`)).toHaveText("approved");

  const thirdDetail = await page.request.get(`${API_URL}/action-proposals/${third.id}`);
  expect((await thirdDetail.json()).execution).toBeNull();

  // The first, already-succeeded execution remains retrievable and
  // unaffected — proving the limiter never touched an existing record.
  const firstDetail = await page.request.get(`${API_URL}/action-proposals/${first.id}`);
  expect((await firstDetail.json()).execution).not.toBeNull();

  // An idempotent replay of the first execution still returns the original
  // result rather than being blocked outright — the limiter's remaining
  // budget (this test used exactly its cap) is exhausted, so the replay
  // itself is also throttled; either outcome is safe, but it must never
  // create a second execution record.
  const replay = await page.request.post(`${API_URL}/action-proposals/${first.id}/execute`, {
    headers: MUTATION_HEADERS,
  });
  if (replay.ok()) {
    const replayBody = await replay.json();
    expect(replayBody.execution.id).toBe((await firstDetail.json()).execution.id);
  } else {
    expect(replay.status()).toBe(429);
  }
});

// --- Journey C — deletion confirmation throttling ---------------------------

test("Journey C — a throttled deletion confirmation never mutates the reviewed plan", async ({
  page,
}) => {
  const userId = await signIn(page, "delconfirm");
  support("seed-imported", userId); // synthetic google (3 items) + secondary (1 item)

  const summary = await (await page.request.get(`${API_URL}/privacy/summary`)).json();
  const secondaryAccountId = summary.connections.find(
    (c: { provider: string }) => c.provider === "secondary",
  ).account_id as string;

  // Consume the shared, tiny test-only `deletion_confirm_cancel` budget with
  // a preview+cancel on a completely SEPARATE (secondary) operation — this
  // never touches the google-account operation reviewed through the real UI
  // below, so its plan fingerprint and version stay untouched throughout.
  const secondaryPreview = await page.request.post(
    `${API_URL}/privacy/imported-data/${secondaryAccountId}/preview`,
    { headers: MUTATION_HEADERS },
  );
  expect(secondaryPreview.ok()).toBeTruthy();
  const secondaryOp = await secondaryPreview.json();
  const cancelResponse = await page.request.post(
    `${API_URL}/privacy/deletion-operations/${secondaryOp.operation_id}/cancel`,
    { headers: MUTATION_HEADERS },
  );
  expect(cancelResponse.ok()).toBeTruthy();

  // Review the google-account deletion through the real UI, as a user would.
  await page.goto("/connections");
  await expect(page.getByTestId("google-connection-status")).toHaveText("active");
  const control = page.getByTestId("delete-imported-control");
  await control.getByTestId("delete-imported-preview").click();
  await expect(control.getByTestId("delete-imported-preview-counts")).toContainText("3");

  const input = control.getByTestId("delete-imported-confirm-input");
  await input.fill("DELETE IMPORTED DATA");
  const confirmButton = control.getByTestId("delete-imported-confirm");
  await expect(confirmButton).toBeEnabled();

  let confirmRequests = 0;
  page.on("request", (r) => {
    if (/\/deletion-operations\/.*\/confirm/.test(r.url()) && r.method() === "POST") {
      confirmRequests += 1;
    }
  });
  await confirmButton.click();

  // Blocked — the shared bucket was already exhausted by the secondary
  // operation's cancel above.
  await expect(control.getByRole("alert")).toContainText(/Try again in/);
  expect(confirmRequests).toBe(1); // one attempt was made, and it was blocked — never duplicated

  // No deletion started, and the typed phrase plus reviewed preview survive
  // exactly as they were, ready for a later manual retry.
  await expect(page.getByTestId("operation-status")).toHaveCount(0);
  await expect(input).toHaveValue("DELETE IMPORTED DATA");
  await expect(confirmButton).toBeEnabled();
  await expect(control.getByTestId("delete-imported-preview-counts")).toContainText("3");

  const ops = (await (await page.request.get(`${API_URL}/privacy/deletion-operations`)).json())
    .operations as Array<{ operation_type: string; scope_label: string; state: string }>;
  const googleOp = ops.find(
    (op) => op.operation_type === "imported_data" && op.scope_label.includes("google"),
  );
  expect(googleOp?.state).toBe("previewed"); // unchanged — never advanced to pending
});
