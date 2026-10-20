import { expect, test, Page } from "@playwright/test";
import type { Briefing, Issue } from "../components/briefing";

const headers = { "X-Drive-Request": "1", Origin: "http://localhost:3001" };
const empty: Briefing = {
  signal_score: null,
  analyzed: 0,
  limited_sample: true,
  total: 0,
  active_employees: 0,
  needs_attention: 0,
  requiring_review: 0,
  stale: 0,
  failed: 0,
  awaiting: 0,
  period: "All time",
  issues: [],
  recent: [],
  teams: [],
};
const issue: Issue = {
  id: "closing",
  name: "Closing review",
  rubric_name: "Service",
  rubric_version: "1",
  criteria: "Summarize next steps",
  description: "Closing",
  max_score: 100,
  eligible: 5,
  occurrences: 2,
  affected_employees: 1,
  unassigned: 0,
  percent: 40,
  limited_sample: false,
  coaching_ready: true,
};
async function noOverflow(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
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

test("dashboard hides empty modules and restores actionable sections on refresh", async ({
  page,
}) => {
  let data = { ...empty };
  await page.route("**/api/briefing", (route) => route.fulfill({ json: data }));
  await page.route("**/api/preferences", (route) =>
    route.fulfill({
      json: {
        appearance: "light",
        revision: 1,
        modules: [
          "metrics",
          "attention",
          "recent",
          "issues",
          "teams",
          "coaching",
          "recommendations",
          "processing",
          "review",
        ],
      },
    }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Recent interactions", exact: true }),
  ).toBeVisible();
  const optional = [
    "Needs Attention",
    "Frequent Quality Issues",
    "Team Performance",
    "Coaching Opportunities",
    "Signal Recommends",
    "Processing Status",
  ];
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const name of optional)
      await expect(
        page.getByRole("heading", { name, exact: true }),
      ).toHaveCount(0);
    await expect(page.locator(".dashboard-modules > div")).toHaveCount(2);
    await expect(
      page.getByRole("link", { name: /Open the supervisor review queue/ }),
    ).toHaveCount(0);
    await noOverflow(page);
  }
  await page.screenshot({
    path: "test-results/dashboard-empty-mobile.png",
    fullPage: true,
  });
  data = {
    ...empty,
    total: 5,
    analyzed: 5,
    signal_score: 84,
    limited_sample: false,
    needs_attention: 1,
    requiring_review: 1,
    stale: 1,
    awaiting: 1,
    issues: [issue],
    recent: [
      {
        id: "call-one",
        filename: "service-call.wav",
        employee_id: null,
        employee_name: null,
        manager_id: null,
        manager_name: null,
        score: 84,
        status: "completed",
        stale: true,
        needs_review: true,
        rubric_name: "Service",
        rubric_version: "1",
        is_demo: false,
      },
    ],
    teams: [
      {
        id: "manager",
        name: "Service team",
        active: true,
        direct_reports: 2,
        interactions: 5,
        analyzed: 5,
        limited_sample: false,
        score: 84,
      },
    ],
  };
  await page.getByRole("button", { name: "Refresh briefing" }).click();
  for (const name of optional)
    await expect(
      page.getByRole("heading", { name, exact: true }),
    ).toBeVisible();
  const recommendations = page.locator(".signal-recommends");
  await expect(
    recommendations.getByRole("button", { name: "Create Team Email" }),
  ).not.toBeVisible();
  await recommendations.locator("summary").click();
  await expect(
    recommendations.getByRole("button", { name: "Create Team Email" }),
  ).toBeVisible();
  await recommendations.locator("summary").click();
  await expect(
    page.getByRole("link", { name: "service-call.wav" }),
  ).toHaveAttribute("href", "/calls/call-one");
  await expect(
    page.locator('.briefing-attention a[href="/calls?status=failed"]'),
  ).toHaveCount(0);
  await expect(
    page.locator('.briefing-attention a[href="/calls?needs_review=true"]'),
  ).toBeVisible();
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await noOverflow(page);
    await page.screenshot({
      path: `test-results/dashboard-actionable-${width}.png`,
      fullPage: true,
    });
  }
  // A low-sample issue remains reviewable without claiming a coaching opportunity.
  data = {
    ...empty,
    issues: [{ ...issue, coaching_ready: false, limited_sample: true }],
  };
  await page.getByRole("button", { name: "Refresh briefing" }).click();
  await expect(
    page.getByRole("heading", { name: "Frequent Quality Issues", exact: true }),
  ).toBeVisible();
  for (const name of [
    "Needs Attention",
    "Coaching Opportunities",
    "Signal Recommends",
    "Processing Status",
  ])
    await expect(page.getByRole("heading", { name, exact: true })).toHaveCount(
      0,
    );
  data = { ...empty, needs_attention: 1, failed: 1 };
  await page.getByRole("button", { name: "Refresh briefing" }).click();
  await expect(
    page.locator('.briefing-attention a[href="/calls?status=failed"]'),
  ).toBeVisible();
  await expect(
    page.locator('.briefing-attention a[href="/calls?needs_review=true"]'),
  ).toHaveCount(0);
  data = { ...empty };
  await page.getByRole("button", { name: "Refresh briefing" }).click();
  await expect(
    page.getByRole("heading", { name: "Needs Attention", exact: true }),
  ).toHaveCount(0);
  await expect(page.locator(".dashboard-modules > div")).toHaveCount(2);
  await page.unroute("**/api/preferences");
  await page.route("**/api/preferences", (route) =>
    route.fulfill({
      json: {
        appearance: "light",
        revision: 1,
        modules: ["attention", "coaching"],
      },
    }),
  );
  await page.reload();
  await expect(page.getByRole("status")).toHaveText(
    "No actionable items in your selected modules.",
  );
  await expect(page.locator(".dashboard-modules > div")).toHaveCount(0);
});

test("flag rule switches preserve severity, recipients, enablement and deletion", async ({
  page,
}) => {
  await page.goto("/flagged-terms");
  await page.getByLabel("Term or phrase").fill("UX lifecycle phrase");
  await page
    .getByRole("combobox", { name: "Severity", exact: true })
    .selectOption("urgent");
  const enabled = page.getByRole("switch", { name: "Enabled", exact: true });
  await expect(enabled).toBeChecked();
  await page
    .getByRole("switch", { name: "Email notification", exact: true })
    .click();
  const recipients = page.getByRole("group", { name: "Verified recipients" });
  await expect(recipients.getByRole("checkbox").first()).toBeVisible();
  await recipients.getByRole("checkbox").first().check();
  await page.getByRole("button", { name: "Add Flag", exact: true }).click();
  const card = page.locator(".flag-rule").filter({
    has: page.getByRole("heading", {
      name: "UX lifecycle phrase",
      exact: true,
    }),
  });
  await expect(card.locator(".flag-status")).toHaveText("Active");
  await expect(card.locator(".flag-severity")).toHaveText("Urgent");
  await expect(card).toContainText("Email alerts · 1 recipient");
  for (const theme of ["light", "dark"]) {
    await page.getByLabel("Appearance", { exact: true }).selectOption(theme);
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await noOverflow(page);
      await page.screenshot({
        path: `test-results/flag-rules-${theme}-${width}.png`,
        fullPage: true,
      });
    }
  }
  await card.getByRole("button", { name: "Edit UX lifecycle phrase" }).click();
  await expect(recipients.getByRole("checkbox").first()).toBeChecked();
  await enabled.focus();
  await page.keyboard.press("Space");
  await expect(enabled).not.toBeChecked();
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(card.locator(".flag-status")).toHaveText("Inactive");
  await page.reload();
  await expect(card.locator(".flag-status")).toHaveText("Inactive");
  await card.getByRole("button", { name: "Edit UX lifecycle phrase" }).click();
  await enabled.click();
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(card.locator(".flag-status")).toHaveText("Active");
  await page
    .getByRole("button", { name: "Scan existing transcripts", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await card
    .getByRole("button", { name: "Delete UX lifecycle phrase" })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Delete rule", exact: true })
    .click();
  await expect(card).toHaveCount(0);
});
