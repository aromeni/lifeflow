import { defineConfig } from "@playwright/test";

// End-to-end tests need PostgreSQL with migrations applied — run via
// scripts/e2e.sh, which prepares the database and then invokes Playwright.
// The API and web dev servers are started (or reused) automatically below.
//
// Stage 9 Delivery Phase 4 (ADR 0005 D64/D81): rate limiting is enabled for
// this e2e API process with test-only overrides so the throttling journeys
// (rate-limiting.spec.ts) never wait out a production window. Every other
// existing journey is unaffected: `anonymous_auth` (the only client-IP-keyed
// policy any existing spec touches, via dev-login) is overridden generously
// rather than left at its tiny production default, since every spec shares
// one client IP (localhost) across the whole suite. Every other overridden
// policy is authenticated-user-keyed and each spec signs in as its own fresh
// dev-login user, so one spec's usage never touches another's bucket — the
// capacities below are set to the highest number of legitimate calls any
// existing spec's own user already makes (2, for a regenerate-brief journey
// and an execute-then-replay journey), so this phase's throttling journeys
// deliberately make one call more than that to observe the block.
const RATE_LIMIT_OVERRIDES = JSON.stringify({
  anonymous_auth: { capacity: 100, refill_amount: 200, refill_window_seconds: 60 },
  brief_generate: { capacity: 2, refill_amount: 2, refill_window_seconds: 3600 },
  external_execution: { capacity: 2, refill_amount: 2, refill_window_seconds: 3600 },
  deletion_confirm_cancel: { capacity: 1, refill_amount: 1, refill_window_seconds: 3600 },
});

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  // Playwright's 5s default is tight for `next dev`'s on-demand, first-hit
  // route compilation under CI's constrained (2 vCPU) runners — a Stage 9
  // Final Integration CI run surfaced this as page-navigation assertions
  // (toHaveURL) timing out on cold routes, never on a warm local machine.
  // Left at Playwright's default locally, where this margin was never an
  // issue in any local run of this suite.
  expect: { timeout: process.env.CI ? 10_000 : 5_000 },
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  webServer: [
    {
      // --forwarded-allow-ips="" is required: uvicorn otherwise trusts
      // X-Forwarded-For from any loopback connection by default, which would
      // silently defeat the anonymous_auth trusted-proxy test coverage below
      // (ADR 0005 D64/D81).
      command:
        'uv run uvicorn --app-dir src lifeflow_api.main:app --port 8010 --forwarded-allow-ips=""',
      cwd: "../api",
      url: "http://localhost:8010/health",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: {
        RATE_LIMITING_ENABLED: "true",
        // A fixed, obviously-fictional test-only value — never a real secret.
        RATE_LIMIT_KEY_SECRET: "playwright-e2e-rate-limit-secret-not-a-real-secret-32c", // pragma: allowlist secret
        RATE_LIMIT_POLICY_OVERRIDES_JSON: RATE_LIMIT_OVERRIDES,
      },
    },
    {
      command: "pnpm dev",
      url: "http://localhost:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
