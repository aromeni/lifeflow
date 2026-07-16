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

  await page.getByRole("button", { name: "Generate brief" }).click();
  const status = page.getByText(/version \d+/);
  await expect(status).toBeVisible({ timeout: 15_000 });
  const firstVersion = Number(/version (\d+)/.exec((await status.textContent()) ?? "")?.[1]);

  await page.getByRole("button", { name: "Generate brief" }).click();
  await expect(page.getByText(new RegExp(`version ${firstVersion + 1}`))).toBeVisible({
    timeout: 15_000,
  });
});
