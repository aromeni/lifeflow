import { expect, test, type Page } from "@playwright/test";

// Stage 7 remediation: the Connections screen previously had zero browser
// coverage. This spec runs against the same demo-only webServer as the other
// e2e specs (no real Google credentials, GOOGLE_OAUTH_ENABLED unset) — it
// proves the not-connected state and the Today <-> Connections route both
// work for a real signed-in user, and that "Sync now" never renders without
// a connected account. The real-Google connect/sync/execute journey is
// exercised end-to-end against the identical `create_app()` composition in
// apps/api/tests/test_google_route_integration.py — a browser-level
// equivalent would require making Google's endpoint hostnames configurable
// via environment overrides, a change deliberately out of scope for this
// remediation (see stage-07.md).

const API_URL = "http://localhost:8010";
const MUTATION_HEADERS = { "X-LifeFlow-CSRF": "1" };

async function signIn(page: Page) {
  await page.goto("/");
  const login = await page.request.post(`${API_URL}/auth/dev-login`, {
    headers: MUTATION_HEADERS,
    data: {
      email: `playwright-connections-${Date.now()}@example.com`,
      display_name: "Connections User",
    },
  });
  expect(login.ok()).toBeTruthy();
}

test("connections screen shows the not-connected state and links back to Today", async ({
  page,
}) => {
  await signIn(page);
  await page.goto("/connections");

  await expect(page.getByRole("heading", { name: "Connections" })).toBeVisible();
  await expect(page.getByTestId("google-connection-card")).toContainText("Not connected");
  await expect(page.getByRole("link", { name: "Connect Google" })).toBeVisible();
  await expect(page.getByTestId("sync-google-now")).toHaveCount(0);
  await expect(page.getByTestId("google-connection-status")).toHaveCount(0);

  await page.getByTestId("nav-today").click();
  await expect(page).toHaveURL(/\/today/);
  await expect(page.getByTestId("connections-link")).toBeVisible();
});
