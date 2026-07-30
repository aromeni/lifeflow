import { defineConfig } from "@playwright/test";

// Stage 11A Phase 1: a one-off owner-operated walkthrough script, run
// manually to produce screenshot evidence for docs/evaluation/stage-11/
// owner-validation/phase-1/manual-walkthrough.md — not wired into ci.yml
// (owner-only internal validation is local/manual by design; see
// docs/delivery/stage-11a-owner-validation-plan.md). Runs against the same
// plain demo stack as playwright.config.ts and playwright.design.config.ts
// (port 8010/3000) and can reuse an already-running one locally.

export default defineConfig({
  testDir: "./e2e-owner-validation",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  expect: { timeout: 10_000 },
  use: {
    baseURL: "http://localhost:3000",
  },
  webServer: [
    {
      command:
        'uv run uvicorn --app-dir src lifeflow_api.main:app --port 8010 --forwarded-allow-ips=""',
      cwd: "../api",
      url: "http://localhost:8010/health",
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: "pnpm dev",
      url: "http://localhost:3000",
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
