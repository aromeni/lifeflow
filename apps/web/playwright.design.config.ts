import { defineConfig } from "@playwright/test";

// Stage 10: the design/accessibility/responsive/visual-regression suite runs
// in its own discovery boundary (`./e2e-design`), separate from the original
// 10-journey functional suite (`./e2e`, `playwright.config.ts`) and the
// 4-journey outage/resilience suite (`./e2e-resilience`,
// `playwright.resilience.config.ts`). This suite needs neither
// GOOGLE_OAUTH_ENABLED nor the fake-Google server nor rate-limiting
// overrides — it runs against the same plain demo stack as the original
// suite (port 8010/3000) and can reuse an already-running one locally, but
// is invoked separately (`scripts/e2e-design.sh`) so the three suites'
// journey/test counts stay independently countable and none of the three
// is silently inflated by another's tests (a real gap in this stage's first
// self-review — see docs/delivery/reports/stage-10.md).

export default defineConfig({
  testDir: "./e2e-design",
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  expect: { timeout: process.env.CI ? 10_000 : 5_000 },
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  webServer: [
    {
      command:
        'uv run uvicorn --app-dir src lifeflow_api.main:app --port 8010 --forwarded-allow-ips=""',
      cwd: "../api",
      url: "http://localhost:8010/health",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: "pnpm dev",
      url: "http://localhost:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
