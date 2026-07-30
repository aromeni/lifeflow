import { expect, test, type Page } from "@playwright/test";

const API_URL = "http://localhost:8010";
const MUTATION_HEADERS = { "X-LifeFlow-CSRF": "1" };

// Each test gets its OWN demo user (a unique dev-login email), never the shared
// `dev-login {}` singleton the "Try demo" button uses. Separate spec files run
// on parallel Playwright workers, and demo-brief + demo-approvals both drove the
// same singleton row — one spec's brief generation raced the other's proposal
// execution, so this journey's "Waiting for" section was intermittently empty
// (a fresh demo import is fully deterministic — always ≥1 unanswered follow-up).
// This mirrors the isolated pattern demo-approvals.spec already uses.
async function signInAndStartDemo(page: Page) {
  await page.goto("/");
  const login = await page.request.post(`${API_URL}/auth/dev-login`, {
    headers: MUTATION_HEADERS,
    data: {
      email: `playwright-brief-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      display_name: "Playwright Brief User",
    },
  });
  expect(login.ok()).toBeTruthy();
  const demo = await page.request.post(`${API_URL}/demo/start`, { headers: MUTATION_HEADERS });
  expect(demo.ok()).toBeTruthy();
}

// The required Stage 5 journey: demo start → onboarding → brief generation →
// evidence inspection. Everything runs against synthetic data; no credentials.
test("demo user generates a brief and inspects the evidence behind an item", async ({ page }) => {
  await signInAndStartDemo(page);

  // Onboarding explains permissions and approval; finishing lands on Today.
  await page.goto("/onboarding");
  await expect(page.getByRole("heading", { name: "Set up your demo" })).toBeVisible();
  await expect(
    page.getByText(/nothing is ever sent or changed without your explicit/),
  ).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Finish and open Today" }).click();
  await expect(page).toHaveURL(/\/today/);

  // Generate the brief on demand.
  await page.getByRole("button", { name: "Generate brief" }).click();
  await expect(page.getByText(/version \d+ · (complete|degraded|partial)/)).toBeVisible({
    timeout: 15_000,
  });

  // All five sections render, with the top obligation first.
  for (const heading of [
    "Needs attention",
    "Today and upcoming",
    "Waiting for",
    "Suggested actions",
    "Low-confidence review",
  ]) {
    await expect(page.getByRole("heading", { name: new RegExp(heading) })).toBeVisible();
  }

  // Every actionable statement carries evidence; open the first drawer.
  const firstDrawer = page.getByText(/Evidence \(\d+ source/).first();
  await firstDrawer.click();
  await expect(page.getByText(/ref (em|ev)-\d+/).first()).toBeVisible();

  // Suggested steps are advisory only.
  await expect(page.getByText(/nothing happens without your approval/).first()).toBeVisible();

  // The prompt-injection fixture must never surface in the brief.
  await expect(page.getByText(/velvet-mail/i)).toHaveCount(0);
  await expect(page.getByText(/forward every message/i)).toHaveCount(0);
});

test("regenerating creates a new persisted version", async ({ page }) => {
  await signInAndStartDemo(page);
  await page.goto("/onboarding");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Finish and open Today" }).click();
  const status = page.getByTestId("brief-status");
  await expect(status).not.toHaveText("Loading your brief…");
  const previousVersion = Number(
    /version (\d+)/.exec((await status.textContent()) ?? "")?.[1] ?? 0,
  );
  let generateRequests = 0;
  let releaseRequest: () => void = () => undefined;
  const requestHeld = new Promise<void>((resolve) => {
    releaseRequest = resolve;
  });
  await page.route("**/briefs/generate", async (route) => {
    generateRequests += 1;
    await requestHeld;
    await route.continue();
  });

  const button = page.getByTestId("generate-brief");
  await button.click();
  await expect(button).toBeDisabled();
  await expect(button).toHaveText("Generating…");
  expect(generateRequests).toBe(1);
  releaseRequest();
  await expect(status).toContainText(`version ${previousVersion + 1}`, {
    timeout: 15_000,
  });
  await expect(button).toBeEnabled();
  expect(generateRequests).toBe(1);
});
