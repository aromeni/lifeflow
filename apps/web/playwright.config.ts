import { defineConfig } from "@playwright/test";

// End-to-end tests need PostgreSQL with migrations applied — run via
// scripts/e2e.sh, which prepares the database and then invokes Playwright.
// The API and web dev servers are started (or reused) automatically below.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  webServer: [
    {
      command: "uv run uvicorn --app-dir src lifeflow_api.main:app --port 8010",
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
