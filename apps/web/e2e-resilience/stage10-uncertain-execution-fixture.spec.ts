import { execSync } from "node:child_process";

import { expect, type Page, test } from "@playwright/test";

// Stage 10 final closure: a DIRECT, reproducible UI fixture for the
// "uncertain external execution outcome" state. Reuses the exact Stage 9
// Delivery Phase 5 fake-Google-server mechanism Journey B already proves
// the no-automatic-retry behaviour against (same stack, same scenario) — no
// new test-only bypass. This fixture stops short of Journey B's API-restart
// and replay-call assertions (already proven there); it exists to exercise
// the state's design/accessibility/layout properties: the warning renders,
// no retry control exists, the exact payload stays readable, and nothing
// overflows.

const API_URL = "http://localhost:8011";
const FAKE_GOOGLE_URL = "http://localhost:8098";
const MUTATION_HEADERS = { "X-LifeFlow-CSRF": "1" };
const API_DIR = "../api";
const OUT =
  "/private/tmp/claude-501/-Users-abdulrashidomeni-Desktop-llm-projects-LifeFlow-Chief-of-Staff-Suite/fec180d4-e5cb-4406-8e22-ac725efb238a/scratchpad/screenshots-final";

const BREAKPOINTS = [
  { width: 1440, height: 900 },
  { width: 1024, height: 800 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
  { width: 320, height: 700 },
];

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
      display_name: "Playwright Stage10 Fixture",
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

test("Stage 10 fixture — uncertain execution renders a real, non-retryable, readable warning", async ({
  page,
}) => {
  test.setTimeout(60_000);
  const userId = await signIn(page, "uncertainfixture");
  support("seed-account", userId);
  support("seed-draft-source", userId);

  await page.goto("/today");
  await page.getByTestId("generate-brief").click();
  await expect(page.getByTestId("brief-status")).toContainText(/version 1 · complete/, {
    timeout: 15_000,
  });

  await page.getByTestId("approval-inbox-link").click();
  await expect(page).toHaveURL(/\/approvals/);
  const card = page.getByTestId("proposal-create_gmail_draft");
  await expect(card).toBeVisible();
  await card.getByTestId("approve-create_gmail_draft").click();
  await expect(page.getByTestId("proposal-status-create_gmail_draft")).toHaveText("approved");

  const proposalsBefore = await page.request.get(`${API_URL}/action-proposals`);
  const proposalId = (await proposalsBefore.json()).proposals.find(
    (p: { action_type: string }) => p.action_type === "create_gmail_draft",
  ).id as string;

  // The fake server records the draft (the write really happens), then
  // withholds its response until the API's write timeout gives up first —
  // driven via a direct API call (the same request the UI's own "Execute"
  // button issues), matching Journey B's own documented reason: a live
  // browser tab sitting through the multi-second timeout window is
  // unreliable on a memory-constrained host, independent of the UI
  // behaviour under test here.
  await setScenario(page, "gmail_create_draft", "hang_on_write");
  const execute = await page.request.post(`${API_URL}/action-proposals/${proposalId}/execute`, {
    headers: MUTATION_HEADERS,
  });
  expect(execute.ok()).toBeTruthy();
  expect((await execute.json()).execution.effective_status).toBe("uncertain");

  await page.reload();

  const warning = card.getByTestId("execution-uncertain-warning");
  await expect(warning).toBeVisible();
  await expect(warning).toContainText(
    "We could not confirm this action completed. It has not been retried automatically",
  );
  // Accessible semantics: a genuinely uncertain outcome is a "status" the
  // user must review, not an active in-page error — matches the Notice
  // component's own tone/role contract for this call site.
  await expect(warning).toHaveAttribute("role", "status");

  // No automatic or unsafe retry control: once an execution is uncertain,
  // the execute button is gone entirely — never re-offered, never disabled
  // (a disabled-but-present button would still invite a hopeful click).
  await expect(card.getByTestId("execute-create_gmail_draft")).toHaveCount(0);

  // Exact payload and historical state remain understandable: the original
  // approved payload preview is still shown in full, not collapsed away or
  // replaced by the warning.
  await expect(card.getByText("Exact approval preview")).toBeVisible();
  await expect(card.locator("dd", { hasText: "dana@northgate-consulting.example" })).toBeVisible();
  await expect(page.getByTestId("proposal-status-create_gmail_draft")).toHaveText(
    "Execution outcome uncertain",
  );

  // No raw provider detail anywhere on the page.
  const bodyText = (await page.textContent("body")) ?? "";
  for (const forbidden of ["Traceback", "fake-access-token-never-a-real-google-credential"]) {
    expect(bodyText).not.toContain(forbidden);
  }

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: `${OUT}/11-approvals-uncertain-execution.png`, fullPage: true });

  for (const bp of BREAKPOINTS) {
    await page.setViewportSize(bp);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `horizontal overflow at ${bp.width}px`).toBeLessThanOrEqual(1);
    await expect(warning).toBeVisible();
    if (bp.width === 390) {
      await page.screenshot({
        path: `${OUT}/11b-approvals-uncertain-execution-mobile-390.png`,
        fullPage: true,
      });
    }
  }
});
