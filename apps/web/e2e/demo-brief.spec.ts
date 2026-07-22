import { expect, test } from "@playwright/test";

// The required Stage 5 journey: demo start → onboarding → brief generation →
// evidence inspection. Everything runs against synthetic data; no credentials.
test("demo user generates a brief and inspects the evidence behind an item", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Try demo/ }).click();

  // Onboarding explains permissions and approval; finishing lands on Today.
  await expect(page.getByRole("heading", { name: "Set up your demo" })).toBeVisible();
  await expect(
    page.getByText(/nothing is ever sent or changed without your explicit/),
  ).toBeVisible();
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
  await page.goto("/");
  await page.getByRole("button", { name: /Try demo/ }).click();
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
