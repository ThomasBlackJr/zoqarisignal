import path from "node:path";
import { expect, test } from "@playwright/test";

const headers = { "X-Drive-Request": "1", Origin: "http://localhost:3001" };

test("current manager teams, interaction filters, reporting moves and audit", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
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
  await page
    .context()
    .storageState({
      path: path.join(
        process.env.DRIVE_E2E_MAIL_FOLDER!,
        "controls-session.json",
      ),
    });
  const ids: Record<string, string> = {};
  for (const [name, manager] of [
    ["Sarah Johnson", ""],
    ["David Williams", ""],
    ["John Smith", "Sarah Johnson"],
    ["Maria Garcia", "Sarah Johnson"],
    ["Robert Jones", "David Williams"],
  ]) {
    await page.goto("/employees");
    await page.getByLabel("Name", { exact: true }).fill(name);
    if (!manager) await page.getByLabel("Can manage employees").check();
    if (manager)
      await page
        .getByLabel("Manager", { exact: true })
        .selectOption({ label: manager });
    await page.getByRole("button", { name: "Create employee" }).click();
    const link = page.getByRole("link", { name, exact: true });
    await expect(link).toBeVisible();
    ids[name] = (await link.getAttribute("href"))!.split("/").pop()!;
  }
  // Synthetic recordings exercise the actual upload and demo evaluation pipeline.
  for (const [i, name] of [
    "John Smith",
    "Maria Garcia",
    "Robert Jones",
  ].entries()) {
    const wav = Buffer.alloc(16044);
    wav.write("RIFF");
    wav.writeUInt32LE(16036, 4);
    wav.write("WAVEfmt ", 8);
    wav.writeUInt32LE(16, 16);
    wav.writeUInt16LE(1, 20);
    wav.writeUInt16LE(1, 22);
    wav.writeUInt32LE(8000, 24);
    wav.writeUInt32LE(16000, 28);
    wav.writeUInt16LE(2, 32);
    wav.writeUInt16LE(16, 34);
    wav.write("data", 36);
    wav.writeUInt32LE(16000, 40);
    wav[16043] = 200 + i;
    await page.goto("/upload");
    await page.getByLabel("Choose audio recording").setInputFiles({
      name: `hierarchy-${i}.wav`,
      mimeType: "audio/wav",
      buffer: wav,
    });
    await page
      .getByLabel("Scorecard", { exact: true })
      .selectOption({ index: 1 });
    await page.getByRole("button", { name: "Upload & process" }).click();
    await expect(page.locator(".status.completed")).toBeVisible({
      timeout: 20000,
    });
    await page
      .getByLabel("Assigned employee", { exact: true })
      .selectOption({ label: name });
    await page.getByRole("button", { name: "Save assignment" }).click();
    await expect(page.getByRole("link", { name, exact: true })).toBeVisible();
  }
  await page.goto(`/employees/${ids["Sarah Johnson"]}`);
  await page
    .getByRole("link", { name: "View current team performance" })
    .click();
  await expect(
    page.getByRole("link", { name: "John Smith", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Maria Garcia", exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".metric").filter({ hasText: "Team Signal Score" }),
  ).toContainText("90");
  await page.screenshot({
    path: "test-results/manager-team-light.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "View team interactions" }).click();
  await expect(page.getByLabel("Filter by manager")).toHaveValue(
    ids["Sarah Johnson"],
  );
  await expect(
    page.getByRole("link", { name: "Open hierarchy-0.wav", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Open hierarchy-1.wav", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Open hierarchy-2.wav", exact: true }),
  ).not.toBeVisible();
  await page.goto(`/employees/${ids["Maria Garcia"]}`);
  await page
    .getByLabel("Manager", { exact: true })
    .selectOption(ids["David Williams"]);
  await page.getByRole("button", { name: "Save employee" }).click();
  await expect(
    page.getByRole("link", { name: "David Williams", exact: true }),
  ).toBeVisible();
  await page.getByText(/Reporting and user-link history/).click();
  await expect(
    page.getByText("Sarah Johnson → David Williams", { exact: false }),
  ).toBeVisible();
  await page.goto(`/employees/${ids["Sarah Johnson"]}/team`);
  await expect(
    page.getByRole("link", { name: "John Smith", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Maria Garcia", exact: true }),
  ).not.toBeVisible();
  await page.goto(`/employees/${ids["David Williams"]}/team`);
  await expect(
    page.getByRole("link", { name: "Maria Garcia", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Robert Jones", exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".metric").filter({ hasText: "Interactions analyzed" }),
  ).toContainText("2");
  await page.getByLabel("Appearance", { exact: true }).selectOption("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({
    path: "test-results/manager-team-dark.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/manager-team-mobile.png",
    fullPage: true,
  });
  await page.goto("/employees/managers");
  await page.getByLabel("Sort manager teams").selectOption("interactions");
  await expect(
    page.getByRole("link", { name: "Sarah Johnson", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "David Williams", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
