import { defineConfig } from "@playwright/test";

// Stage 11A Phase 2: the owner-operated failure-walkthrough spec needs the
// same dedicated resilience stack the Journey specs use (GOOGLE_OAUTH_ENABLED,
// the fake Google server, port 8011/8098/3001) — unlike
// playwright.owner-validation.config.ts (Phase 1's plain demo-stack
// walkthrough, port 8010/3000). The API and fake-Google server are started
// and torn down by scripts/stage11a-phase2-owner-walkthrough.sh itself
// (mirroring scripts/e2e-resilience.sh), never by this config's own
// webServer, so the spec's real OS-level considerations (a genuinely
// running, externally-owned process) match Journey B's precedent exactly.
// Only the web dev server is a `webServer` entry here.

export default defineConfig({
  testDir: "./e2e-owner-validation",
  testMatch: /phase2-failure-walkthrough\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:3001",
    trace: "on-first-retry",
  },
  webServer: [
    {
      command: "pnpm dev",
      url: "http://localhost:3001",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        PORT: "3001",
        NEXT_PUBLIC_API_URL: "http://localhost:8011",
      },
    },
  ],
});
