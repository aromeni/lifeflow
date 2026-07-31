import { defineConfig } from "@playwright/test";

// Stage 11A Phase 3: a one-off owner-operated browser-privacy walkthrough,
// run manually to produce the evidence for docs/evaluation/stage-11/
// owner-validation/phase-3/manual-walkthrough.md and browser-privacy-
// results.md — not wired into ci.yml (owner-only internal validation is
// local/manual by design). Runs against the same plain demo stack as
// playwright.owner-validation.config.ts (port 8010/3000); `testMatch` keeps
// this scoped to its own spec so it never collides with Phase 1's or
// Phase 2's owner-validation config/spec pairing in the same directory.

export default defineConfig({
  testDir: "./e2e-owner-validation",
  testMatch: /phase3-privacy-walkthrough\.spec\.ts/,
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
