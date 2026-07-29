import { defineConfig } from "@playwright/test";

// Stage 9 Delivery Phase 5 (§20): the four outage/resilience Playwright
// journeys run against their OWN dedicated stack — a separate API instance
// (port 8011), a separate Next.js dev server (port 3001), and the fake
// Google server (port 8098) — rather than the shared stack `playwright.config.ts`
// uses (port 8010/3000). Two reasons this must be a separate stack, not an
// extra project on the existing config:
//   1. These journeys need `GOOGLE_OAUTH_ENABLED=true` plus a fake-Google
//      origin override, which the other 10 journeys deliberately run
//      without (`connections.spec.ts` documents relying on it being unset).
//   2. Journey D stops/starts the real Postgres/Redis containers the API
//      depends on — running that in the same Playwright invocation as the
//      other specs would break whichever of them happened to run
//      concurrently. Run `scripts/e2e.sh` and `scripts/e2e-resilience.sh`
//      sequentially, never at the same time.
//
// The API (port 8011) is deliberately NOT a `webServer` entry here — unlike
// the other three, `scripts/e2e-resilience.sh` starts and owns that process
// itself (`scripts/resilience-api-env.sh`), because Journey B kills and
// respawns it mid-test to prove an API restart never retries an uncertain
// provider write; Playwright's `webServer` supervises a process for the
// whole run and is not designed to survive one of its entries being killed
// out from under it mid-suite.

export default defineConfig({
  testDir: "./e2e-resilience",
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
      command:
        "LIFEFLOW_E2E_FAKE_GOOGLE=1 uv run uvicorn --app-dir src " +
        "lifeflow_api.testing.fake_google_server:app --port 8098",
      cwd: "../api",
      url: "http://localhost:8098/__control__/state",
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
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
