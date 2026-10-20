import { expect, test } from "@playwright/test";

async function login(page: import("@playwright/test").Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Work email").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DRIVE_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Sign in to Signal" }).click();
}

test("organization-free platform administrator lands in separate admin area and manages another organization", async ({
  page,
}) => {
  await login(page, "platform@example.test");
  await expect(page).toHaveURL(/\/platform$/);
  await expect(
    page.getByRole("heading", { name: "Platform dashboard" }),
  ).toBeVisible();
  await expect(
    page.getByText("Platform administrator", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Workspace", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("navigation", { name: "Platform", exact: true })
    .getByRole("link", { name: "Organizations", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Create organization", exact: true })
    .click();
  const name = `Platform beta ${Date.now()}`;
  await page.getByLabel("Organization name", { exact: true }).fill(name);
  await page
    .getByLabel("Reason", { exact: true })
    .fill("Synthetic beta organization");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Organization users", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Grant beta access", exact: true })
    .click();
  await page.getByLabel("Reason", { exact: true }).fill("Synthetic grant");
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "Grant beta access completed." }),
  ).toContainText("Grant beta access completed.");
  await page
    .getByRole("button", { name: "Suspend organization", exact: true })
    .click();
  await page.getByLabel("Reason", { exact: true }).fill("Synthetic suspension");
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Reactivate organization", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Reactivate organization", exact: true })
    .click();
  await page
    .getByLabel("Reason", { exact: true })
    .fill("Synthetic reactivation");
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Suspend organization", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Revoke beta access", exact: true })
    .click();
  await page.getByLabel("Reason", { exact: true }).fill("Synthetic revocation");
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Revoke beta access", exact: true }),
  ).toBeDisabled();
  await page.screenshot({
    path: "test-results/platform-organization-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/platform-organization-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page
    .getByRole("navigation", { name: "Platform", exact: true })
    .getByRole("link", { name: "Users", exact: true })
    .click();
  await page
    .getByLabel("Search users", { exact: true })
    .fill("platform@example.test");
  await expect(
    page.getByRole("cell", { name: "platform@example.test", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "No organization", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("navigation", { name: "Platform", exact: true })
    .getByRole("link", { name: "Activity", exact: true })
    .click();
  await expect(
    page.getByRole("cell", { name: "beta.grant", exact: true }).first(),
  ).toBeVisible();
  // A separate customer membership must not override platform landing priority.
  const joined = await page.request.post("/api/organizations", {
    headers: { "X-Drive-Request": "1", Origin: "http://localhost:3001" },
    data: { name: "Operator customer organization" },
  });
  expect(joined.status()).toBe(201);
  await page.getByRole("button", { name: "Log out", exact: true }).click();
  await login(page, "platform@example.test");
  await expect(page).toHaveURL(/\/platform$/);
  await expect(
    page.getByRole("heading", { name: "Platform dashboard" }),
  ).toBeVisible();
});

test("customer Owner and Admin cannot access platform pages or APIs", async ({
  page,
}) => {
  for (const email of ["owner@example.test", "reviewer@example.test"]) {
    await login(page, email);
    await expect(page).toHaveURL(/localhost:3001\/$/, { timeout: 15000 });
    await expect(
      page.getByRole("link", { name: "Zoqari Admin", exact: true }),
    ).toHaveCount(0);
    await page.goto("/platform");
    await expect(page).toHaveURL(/\/account$/);
    for (const route of [
      "/platform/users",
      "/platform/organizations",
      "/platform/activity",
      "/platform/session",
    ]) {
      expect((await page.request.get(`/api${route}`)).status()).toBe(403);
    }
    await page.getByRole("button", { name: "Log out", exact: true }).click();
  }
});
