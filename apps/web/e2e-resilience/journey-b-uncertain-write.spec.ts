import { execSync, spawn } from "node:child_process";

import { expect, test, type Page } from "@playwright/test";

// Stage 9 Delivery Phase 5 (§20) Journey B — uncertain external write.
// Approves and executes a real create_gmail_draft proposal against a Google
// account whose transport is redirected to the fake Google server. The fake
// server records the draft (assigns a real id) but withholds its HTTP
// response until the API's short write timeout gives up first — proving
// the write genuinely happened, LifeFlow just cannot confirm it, and that
// this uncertain outcome is never retried automatically, by the UI, by an
// API restart, or by a direct replay call.

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
      display_name: "Playwright Resilience",
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

async function fakeGoogleDraftCount(page: Page): Promise<number> {
  const response = await page.request.get(`${FAKE_GOOGLE_URL}/__control__/state`);
  expect(response.ok()).toBeTruthy();
  return (await response.json()).draft_count as number;
}

/** Kills whatever is listening on :8011 and respawns the exact same
 * process from `scripts/resilience-api-env.sh` — a real OS-level API
 * restart, not a simulation, so this genuinely proves the uncertain
 * outcome survives a process restart rather than living only in memory. */
async function restartApi(): Promise<void> {
  try {
    // `-sTCP:LISTEN` is essential, not cosmetic: a plain `lsof -ti:8011`
    // matches ANY socket naming port 8011 on either end, including this
    // very test process's own outbound keep-alive connections to the API
    // (from earlier `fetch`/`page.request` calls) — killing that would
    // SIGKILL the Playwright worker itself. Restricting to the
    // LISTEN-state socket targets only the actual server process.
    execSync("lsof -ti tcp:8011 -sTCP:LISTEN | xargs kill -9");
  } catch {
    // Nothing was listening — proceed to (re)start it regardless.
  }
  const child = spawn(
    "bash",
    [
      "-c",
      "source ../../scripts/resilience-api-env.sh && exec uv run uvicorn --app-dir src " +
        'lifeflow_api.main:app --port 8011 --forwarded-allow-ips=""',
    ],
    { cwd: API_DIR, detached: true, stdio: "ignore" },
  );
  child.unref();
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${API_URL}/health`);
      if (response.ok) return;
    } catch {
      // Not up yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("API did not become healthy again after restart");
}

test.beforeEach(async ({ page }) => {
  const reset = await page.request.post(`${FAKE_GOOGLE_URL}/__control__/reset`);
  expect(reset.ok()).toBeTruthy();
});

test("Journey B — an uncertain Gmail draft write is never retried, including across an API restart", async ({
  page,
}) => {
  test.setTimeout(90_000);
  const userId = await signIn(page, "uncertainwrite");
  support("seed-account", userId);
  support("seed-draft-source", userId);

  await page.goto("/today");
  await page.getByTestId("generate-brief").click();
  await expect(page.getByTestId("brief-status")).toContainText(/version 1 · complete/, {
    timeout: 15_000,
  });

  await page.getByTestId("approval-inbox-link").click();
  await expect(page).toHaveURL(/\/approvals/);
  const draft = page.getByTestId("proposal-create_gmail_draft");
  await expect(draft).toBeVisible();
  await draft.getByTestId("approve-create_gmail_draft").click();
  await expect(page.getByTestId("proposal-status-create_gmail_draft")).toHaveText("approved");
  // The UI genuinely offers execution at this point — proven before the
  // uncertain outcome removes it below.
  await expect(draft.getByTestId("execute-create_gmail_draft")).toBeVisible();

  const proposalsBefore = await page.request.get(`${API_URL}/action-proposals`);
  const proposalId = (await proposalsBefore.json()).proposals.find(
    (p: { action_type: string }) => p.action_type === "create_gmail_draft",
  ).id as string;

  // 1-2. The fake server will record the draft, then withhold its response
  // until the API's 2s write timeout gives up first. Triggered via a
  // direct API call (the same request the UI's "Execute approved action"
  // button issues) rather than a UI click: leaving a real browser tab
  // sitting through this multi-second server-side timeout window proved
  // unreliable on this memory-constrained host, independent of and
  // unrelated to the resilience behaviour itself, which is proven
  // end-to-end here exactly as the UI would trigger it.
  await setScenario(page, "gmail_create_draft", "hang_on_write");
  const execute = await page.request.post(`${API_URL}/action-proposals/${proposalId}/execute`, {
    headers: MUTATION_HEADERS,
  });
  expect(execute.ok()).toBeTruthy();
  const executeJson = await execute.json();
  expect(executeJson.execution.effective_status).toBe("uncertain");
  const executionIdBefore = executeJson.execution.id as string;

  await page.reload();
  await expect(page.getByTestId("execution-result")).toBeVisible();
  await expect(page.getByTestId("execution-result")).toContainText("uncertain");
  await expect(page.getByTestId("execution-uncertain-warning")).toBeVisible();

  // 3. Exactly one provider object exists — the write really happened.
  expect(await fakeGoogleDraftCount(page)).toBe(1);

  // 6-7. No automatic or suggested unsafe retry exists: the execute button
  // is gone entirely once a proposal has a terminal/uncertain execution.
  await expect(draft.getByTestId("execute-create_gmail_draft")).toHaveCount(0);

  // 4. API restart does not trigger a retry: kill and respawn the real
  // process, then reload and confirm nothing changed.
  await restartApi();
  await page.reload();
  await expect(page.getByTestId("proposal-status-create_gmail_draft")).toHaveText(
    "Execution outcome uncertain",
  );
  await expect(page.getByTestId("execution-uncertain-warning")).toBeVisible();
  await expect(draft.getByTestId("execute-create_gmail_draft")).toHaveCount(0);
  expect(await fakeGoogleDraftCount(page)).toBe(1);

  // A direct replay call (bypassing the UI, which no longer offers the
  // button at all) is answered idempotently with the SAME already-uncertain
  // execution record (by design — see `execute()`'s own re-entry guard,
  // `action_proposal_service.py`) rather than re-invoking the executor: it
  // must never create a second provider object.
  const replay = await page.request.post(`${API_URL}/action-proposals/${proposalId}/execute`, {
    headers: MUTATION_HEADERS,
  });
  expect(replay.ok()).toBeTruthy();
  const replayJson = await replay.json();
  expect(replayJson.execution.id).toBe(executionIdBefore);
  expect(replayJson.execution.effective_status).toBe("uncertain");
  expect(await fakeGoogleDraftCount(page)).toBe(1);

  // 8. Worker restart does not apply here at all: Google draft execution is
  // synchronous within the approval request — no ARQ job is ever involved
  // for this action type (see docs/delivery/reports/stage-09-phase-5.md,
  // "Known limitations"), so there is nothing for a worker restart to
  // retry in the first place.
});
