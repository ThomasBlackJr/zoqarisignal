import { expect, test, Page } from "@playwright/test";
import type { Account } from "../lib/api";

const headers = { "X-Drive-Request": "1", Origin: "http://localhost:3001" };
const tutorial = (page: Page) =>
  page.getByRole("region", { name: "Signal tutorial", exact: true });
async function next(page: Page) {
  await tutorial(page)
    .getByRole("button", { name: "Next", exact: true })
    .click();
}
async function viewport(page: Page, width: number, name: string) {
  await page.setViewportSize({ width, height: 900 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: `test-results/tutorial-${name}-${width}.png`,
    fullPage: true,
  });
}
async function fixture(page: Page, overrides: Partial<Account> = {}) {
  const actual: Account = await (await page.request.get("/api/account")).json();
  const account = { ...actual, onboarding_completed: false, ...overrides };
  await page.route("**/api/account", (route) =>
    route.fulfill({ json: account }),
  );
  await page.route("**/api/onboarding", (route) =>
    route.fulfill({
      json: {
        completed: account.onboarding_completed,
        has_interactions: false,
      },
    }),
  );
  return account;
}
test.beforeEach(async ({ page }) => {
  expect(
    (
      await page.request.post("/api/auth/login", {
        headers,
        data: {
          email: "reviewer@example.test",
          password: process.env.DRIVE_TEST_PASSWORD!,
        },
      })
    ).ok(),
  ).toBeTruthy();
});

test("tutorial progresses, resumes and completes using the existing organization endpoint", async ({
  page,
}) => {
  const setup = await (await page.request.get("/api/onboarding")).json();
  // The legacy seeded workspace is already set up. Simulate its initial UI state;
  // completion still calls the real endpoint (the customer journey covers a new org).
  await fixture(page);
  await page.goto("/onboarding");
  await expect(tutorial(page).getByRole("status")).toHaveText("Step 1 of 4");
  await expect(
    tutorial(page).getByRole("button", { name: "Back", exact: true }),
  ).toBeDisabled();
  await viewport(page, 1440, "workspace");
  await next(page);
  await tutorial(page).getByRole("link", { name: "Review scorecards" }).click();
  await expect(page).toHaveURL(/\/rubrics$/);
  await page.getByRole("link", { name: "Tutorial", exact: true }).click();
  await expect(tutorial(page).getByRole("status")).toHaveText("Step 2 of 4");
  await page.reload();
  await expect(tutorial(page).getByRole("status")).toHaveText("Step 2 of 4");
  await tutorial(page)
    .getByRole("button", { name: "Back", exact: true })
    .click();
  await expect(tutorial(page).getByRole("status")).toHaveText("Step 1 of 4");
  await next(page);
  await next(page);
  await viewport(page, 390, "upload");
  await expect(
    tutorial(page).getByRole("link", { name: "Upload call", exact: true }),
  ).toHaveAttribute("href", "/upload");
  await next(page);
  await expect(
    tutorial(page).getByRole("link", { name: "Open calls & audits" }),
  ).toHaveAttribute("href", "/calls");
  const complete = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/onboarding/complete") &&
      response.request().method() === "POST",
  );
  await tutorial(page).getByRole("button", { name: "Finish tutorial" }).click();
  const response = await complete;
  expect(response.ok()).toBeTruthy();
  expect(response.request().postDataJSON()).toEqual({
    skip: !setup.has_interactions,
  });
  await expect(page).toHaveURL("/");
  await expect(
    page.getByRole("link", { name: "Tutorial", exact: true }),
  ).toHaveCount(0);
  expect(
    (await (await page.request.get("/api/account")).json())
      .onboarding_completed,
  ).toBe(true);
  // The existing server flag also suppresses the tutorial without browser state.
  await page.unroute("**/api/account");
  await page.unroute("**/api/onboarding");
  await page.evaluate(() => localStorage.clear());
  await page.goto("/onboarding");
  await expect(
    page.getByRole("heading", { name: "You’re all set" }),
  ).toBeVisible();
  await expect(tutorial(page)).toHaveCount(0);
});

test("dismissal persists and is isolated by user and organization", async ({
  page,
}) => {
  const account = await fixture(page);
  let mutations = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/api/onboarding/complete")) mutations++;
  });
  await page.goto("/onboarding");
  await page.getByLabel("Appearance", { exact: true }).selectOption("dark");
  await viewport(page, 390, "dismiss");
  await tutorial(page).getByRole("button", { name: "Not interested" }).click();
  await expect(page).toHaveURL("/");
  await expect(
    page.getByRole("link", { name: "Tutorial", exact: true }),
  ).toHaveCount(0);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Dashboard", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Tutorial", exact: true }),
  ).toHaveCount(0);
  await page.goto("/onboarding");
  await expect(
    page.getByRole("heading", { name: "Tutorial dismissed" }),
  ).toBeVisible();
  const originalUser = account.id;
  const originalOrg = account.organization_id;
  for (const [id, organization] of [
    ["another-user", originalOrg],
    [originalUser, "another-org"],
  ]) {
    account.id = id!;
    account.organization_id = organization;
    await page.reload();
    await expect(tutorial(page).getByRole("status")).toHaveText("Step 1 of 4");
    await expect(
      page.getByRole("link", { name: "Tutorial", exact: true }),
    ).toBeVisible();
  }
  account.id = originalUser;
  account.organization_id = originalOrg;
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Tutorial dismissed" }),
  ).toBeVisible();
  expect(mutations).toBe(0);
});

test("previously completed setup is optional to revisit without becoming prominent again", async ({
  page,
}) => {
  await fixture(page, { onboarding_completed: true });
  let mutations = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/api/onboarding/complete")) mutations++;
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Dashboard", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Tutorial", exact: true }),
  ).toHaveCount(0);
  await page.goto("/onboarding");
  await expect(
    page.getByRole("heading", { name: "You’re all set" }),
  ).toBeVisible();
  await expect(tutorial(page)).toHaveCount(0);
  await page.getByRole("button", { name: "Review tutorial" }).click();
  await expect(tutorial(page).getByRole("status")).toHaveText("Step 1 of 4");
  await next(page);
  await next(page);
  await next(page);
  await tutorial(page).getByRole("button", { name: "Finish tutorial" }).click();
  await expect(page).toHaveURL("/");
  await expect(
    page.getByRole("link", { name: "Tutorial", exact: true }),
  ).toHaveCount(0);
  expect(mutations).toBe(0);
});

test("reviewers complete personally without organization writes or bypassing beta access", async ({
  page,
}) => {
  await fixture(page, {
    role: "REVIEWER",
    operational_access: false,
    can_review: true,
  });
  let mutations = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/api/onboarding/complete")) mutations++;
  });
  await page.goto("/onboarding");
  await next(page);
  await expect(tutorial(page)).toContainText(
    "Explore the published scorecards",
  );
  await next(page);
  await expect(
    tutorial(page).getByRole("button", { name: "Beta access required" }),
  ).toBeDisabled();
  await expect(
    tutorial(page).getByRole("link", { name: "Upload call" }),
  ).toHaveCount(0);
  await viewport(page, 320, "inactive-reviewer");
  await next(page);
  await tutorial(page).getByRole("button", { name: "Finish tutorial" }).click();
  await expect(page).toHaveURL("/");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Dashboard", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Tutorial", exact: true }),
  ).toHaveCount(0);
  expect(mutations).toBe(0);
});

test("storage failures remain usable and API failures do not record completion", async ({
  page,
}) => {
  await fixture(page);
  await page.addInitScript(() => {
    Storage.prototype.getItem = () => {
      throw new Error("Storage unavailable");
    };
    Storage.prototype.setItem = () => {
      throw new Error("Storage unavailable");
    };
  });
  let reads = 0;
  await page.unroute("**/api/onboarding");
  await page.route("**/api/onboarding", (route) =>
    route.fulfill(
      ++reads === 1
        ? { status: 503, json: { detail: "Tutorial temporarily unavailable" } }
        : { json: { completed: false, has_interactions: false } },
    ),
  );
  await page.route("**/api/onboarding/complete", (route) =>
    route.fulfill({ status: 503, json: { detail: "Please try again" } }),
  );
  await page.goto("/onboarding");
  await expect(
    page.getByText("Tutorial temporarily unavailable", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Reload tutorial" }).click();
  await next(page);
  await next(page);
  await next(page);
  await tutorial(page).getByRole("button", { name: "Finish tutorial" }).click();
  await expect(
    page.getByText("Please try again", { exact: true }),
  ).toBeVisible();
  await expect(tutorial(page).getByRole("status")).toHaveText("Step 4 of 4");
  await expect(
    page.getByRole("link", { name: "Tutorial", exact: true }),
  ).toBeVisible();
  await tutorial(page).getByRole("button", { name: "Not interested" }).click();
  await expect(page).toHaveURL("/");
  await expect(
    page.getByRole("link", { name: "Tutorial", exact: true }),
  ).toHaveCount(0);
});
