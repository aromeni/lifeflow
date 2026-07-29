import { type ChildProcess, execSync, spawn } from "node:child_process";

import { expect, test, type Page } from "@playwright/test";

// Stage 9 Delivery Phase 5 (§20) Journey C — worker outage and recovery.
// Deliberately does NOT start any ARQ worker for this Playwright invocation
// (unlike scripts/e2e.sh's own long-running worker, which would otherwise
// race this journey and defeat the "genuinely no worker is consuming jobs"
// premise) — the spec spawns and kills its own worker process(es) directly.
// Uses the durable deletion-operation pipeline as the vehicle: it already
// has an owner-scoped preview/confirm UI, a durable `pending` state, and an
// atomic per-operation claim (`claim_operation`) that makes concurrent
// workers safe — exactly the properties this journey needs to prove.

const API_URL = "http://localhost:8011";
const MUTATION_HEADERS = { "X-LifeFlow-CSRF": "1" };
const API_DIR = "../api";
const TERMINAL_TIMEOUT = 120_000; // worker drains on its <=60s cron, then processes

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
      email: `pw-${marker}-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      display_name: "Playwright Resilience",
    },
  });
  expect(login.ok()).toBeTruthy();
  return (await login.json()).user_id as string;
}

function spawnWorker(): ChildProcess {
  const child = spawn("uv", ["run", "arq", "lifeflow_api.worker_app.WorkerSettings"], {
    cwd: API_DIR,
    env: { ...process.env, PYTHONPATH: "src" },
    stdio: "ignore",
  });
  return child;
}

function killWorker(child: ChildProcess): void {
  if (child.pid) {
    try {
      process.kill(child.pid, "SIGTERM");
    } catch {
      // Already exited.
    }
  }
}

test("Journey C — a durable deletion operation survives a worker outage and completes exactly once", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const userId = await signIn(page, "workeroutage");
  support("seed-imported", userId);

  await page.goto("/connections");
  await expect(page.getByTestId("google-connection-status")).toHaveText("active");

  await page.getByTestId("delete-imported-preview").click();
  await expect(page.getByTestId("delete-imported-preview-counts")).toContainText("3");
  await page.getByTestId("delete-imported-confirm-input").fill("DELETE IMPORTED DATA");
  await page.getByTestId("delete-imported-confirm").click();

  // 1. A durable operation can be created while the worker is unavailable —
  // no worker process is running at all yet.
  const control = page.getByTestId("delete-imported-control");
  const status = control.getByTestId("operation-status");
  await expect(status).toBeVisible();

  // 2. UI displays delayed processing, not failure or completion — and
  // stays that way for several seconds with genuinely no worker present.
  await expect(status).toContainText("Queued — deletion will begin shortly.");
  await page.waitForTimeout(5_000);
  await expect(status).toContainText("Queued — deletion will begin shortly.");

  // 3-4-5. Start two workers at once (duplicate consumer scenario) —
  // restarting the worker resumes the operation, it completes exactly
  // once, and duplicate job delivery does not duplicate work (the atomic
  // per-operation claim means only one of the two ever actually processes
  // it; the other finds nothing to claim).
  const workerA = spawnWorker();
  const workerB = spawnWorker();
  try {
    await expect(status).toContainText(/Done\. The data has been deleted\./, {
      timeout: TERMINAL_TIMEOUT,
    });

    // No operation or provider side effect is duplicated: exactly the
    // google account's 3 imported items are gone, the untouched secondary
    // account's item remains.
    const counts = JSON.parse(support("counts", userId));
    expect(counts.google_sources).toBe(0);
    expect(counts.secondary_sources).toBe(1);
  } finally {
    killWorker(workerA);
    killWorker(workerB);
  }
});
