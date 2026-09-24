import { expect, test, Page } from "@playwright/test";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

const headers = { "X-Drive-Request": "1", Origin: "http://localhost:3001" };
async function login(page: Page) {
  const r = await page.request.post("/api/auth/login", {
    headers,
    data: {
      email: "reviewer@example.test",
      password: process.env.DRIVE_TEST_PASSWORD!,
    },
  });
  expect(r.ok()).toBeTruthy();
}
function wav(i: number) {
  const data = Buffer.alloc(16044);
  data.write("RIFF");
  data.writeUInt32LE(16036, 4);
  data.write("WAVEfmt ", 8);
  data.writeUInt32LE(16, 16);
  data.writeUInt16LE(1, 20);
  data.writeUInt16LE(1, 22);
  data.writeUInt32LE(8000, 24);
  data.writeUInt32LE(16000, 28);
  data.writeUInt16LE(2, 32);
  data.writeUInt16LE(16, 34);
  data.write("data", 36);
  data.writeUInt32LE(16000, 40);
  data[16043] = i;
  return data;
}

test("bulk upload persists ten files and an invalid item, assignment and corrected reevaluation", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  await page.goto("/batches");
  const files = Array.from({ length: 10 }, (_, i) => ({
    name: `batch-browser-${i}.wav`,
    mimeType: "audio/wav",
    buffer: wav(100 + i),
  }));
  await page.getByLabel("Choose batch recordings").setInputFiles([
    ...files,
    {
      name: "invalid.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("invalid"),
    },
  ]);
  await page
    .getByLabel("Scorecard", { exact: true })
    .selectOption({ index: 1 });
  await page.getByRole("button", { name: "Submit batch" }).click();
  await expect(page.locator(".batch-counts")).toContainText("10 Complete", {
    timeout: 30000,
  });
  await expect(page.locator(".batch-counts")).toContainText("1 Failed");
  await page.getByRole("link", { name: "Employees", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("Browser Employee");
  await page.getByRole("button", { name: "Create employee" }).click();
  await expect(
    page.getByRole("link", { name: "Browser Employee" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Bulk upload", exact: true }).click();
  await expect(page.locator(".batch-counts")).toContainText("10 Complete");
  await page
    .getByRole("link", { name: "batch-browser-0.wav", exact: true })
    .click();
  await page
    .getByLabel("Assigned employee", { exact: true })
    .selectOption({ label: "Browser Employee" });
  await page.getByRole("button", { name: "Save assignment" }).click();
  await expect(
    page.getByRole("link", { name: "Browser Employee" }),
  ).toBeVisible();
  await page
    .getByLabel(/Speaker role for turn/)
    .first()
    .selectOption("CALLER");
  await page.getByRole("button", { name: "Apply correction" }).click();
  await expect(
    page.getByText("Speaker corrections need evaluation"),
  ).toBeVisible();
  await expect(page.locator(".final-score")).toContainText("OUTDATED SCORE");
  await page
    .getByRole("button", { name: "Evaluate corrected transcript" })
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "No transcription request is made",
  );
  await page.getByRole("button", { name: "Start new evaluation" }).click();
  await expect(
    page.getByText("Speaker corrections need evaluation"),
  ).not.toBeVisible({ timeout: 20000 });
  await expect(page.locator(".final-score")).toContainText("SIGNAL SCORE");
  await page.getByRole("button", { name: "Evaluation history" }).click();
  await expect(page.locator(".history-evaluation")).toHaveCount(2);
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page.getByRole("link", { name: "Browser Employee" }).click();
  await expect(
    page.getByRole("heading", { name: "Browser Employee" }),
  ).toBeVisible();
  await expect(page.getByText(/Limited sample/)).toBeVisible();
  await page.screenshot({
    path: "test-results/employee-profile-light.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("personal dashboard and Light Dark System persist across sessions", async ({
  page,
}) => {
  await login(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Customize dashboard" }).click();
  await page.getByRole("checkbox", { name: "Recent interactions" }).uncheck();
  await page
    .getByRole("button", { name: "Move Coaching Opportunities up" })
    .click();
  await page.getByRole("button", { name: "Save dashboard" }).click();
  await expect(
    page.getByRole("heading", { name: "Recent interactions" }),
  ).not.toBeVisible();
  await page.getByLabel("Appearance", { exact: true }).selectOption("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator(".metric").first()).toHaveCSS(
    "background-color",
    "rgb(18, 30, 48)",
  );
  await page.reload();
  await expect(page.getByLabel("Appearance", { exact: true })).toHaveValue(
    "dark",
  );
  await expect(
    page.getByRole("heading", { name: "Recent interactions" }),
  ).not.toBeVisible();
  await page.screenshot({
    path: "test-results/dashboard-dark.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "Employees", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Employees", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/employees-dark.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "Bulk upload", exact: true }).click();
  await expect(page.locator(".batch-counts")).toContainText("10 Complete");
  await page.screenshot({
    path: "test-results/batches-dark.png",
    fullPage: true,
  });
  await page
    .getByRole("link", { name: "batch-browser-0.wav", exact: true })
    .click();
  await expect(page.locator(".final-score strong")).toContainText("90");
  await page.screenshot({
    path: "test-results/review-dark.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/review-dark-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page
    .getByRole("button", { name: "Log out", exact: true })
    .first()
    .click();
  await login(page);
  await page.goto("/");
  await expect(page.getByLabel("Appearance", { exact: true })).toHaveValue(
    "dark",
  );
  await expect(
    page.getByRole("heading", { name: "Recent interactions" }),
  ).not.toBeVisible();
  await page.getByLabel("Appearance", { exact: true }).selectOption("light");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByLabel("Appearance", { exact: true }).selectOption("system");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByRole("button", { name: "Customize dashboard" }).click();
  await page.getByRole("button", { name: "Restore defaults" }).click();
  await page.getByRole("button", { name: "Save dashboard" }).click();
});

test("invited manager joins existing team in a separate browser session", async ({
  page,
  browser,
}) => {
  await login(page);
  await page.goto("/team");
  await page.getByLabel("Work email").fill("invited-browser@example.test");
  await page.getByLabel("Role", { exact: true }).selectOption("MANAGER");
  await page.getByRole("button", { name: "Send invitation" }).click();
  await expect(page.getByRole("status")).toContainText("no email was sent");
  const folder = process.env.DRIVE_E2E_MAIL_FOLDER!;
  const content = readdirSync(folder)
    .map((n) => readFileSync(path.join(folder, n), "utf8"))
    .find(
      (t) =>
        t.includes("invited-browser@example.test") &&
        t.includes("Purpose: invite"),
    )!;
  const link = content.split(/\r?\n/).find((l) => l.startsWith("http"))!;
  const context = await browser.newContext();
  const invited = await context.newPage();
  await invited.goto(link);
  await invited.getByLabel("Your name").fill("Invited Manager");
  await invited
    .getByLabel("Choose password")
    .fill(process.env.DRIVE_TEST_PASSWORD!);
  await invited.getByRole("button", { name: "Join organization" }).click();
  await expect(invited).not.toHaveURL(/accept-invitation/);
  await invited.goto("http://localhost:3001/");
  await expect(
    invited.getByRole("heading", { name: "Dashboard", exact: true }),
  ).toBeVisible();
  await expect(
    invited.getByRole("heading", { name: "Recent interactions" }),
  ).toBeVisible();
  const account = await (
    await invited.request.get("http://localhost:3001/api/account")
  ).json();
  const owner = await (await page.request.get("/api/account")).json();
  expect(account.organization_id).toBe(owner.organization_id);
  expect(account.role).toBe("MANAGER");
  expect(
    (await invited.request.get("http://localhost:3001/api/team")).status(),
  ).toBe(403);
  await page.reload();
  await expect(
    page.getByRole("cell", { name: "Invited Manager", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/team-access.png",
    fullPage: true,
  });
  await context.close();
});
