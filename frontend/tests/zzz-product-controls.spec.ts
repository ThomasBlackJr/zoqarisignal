import path from "node:path";
import { existsSync, readFileSync } from "node:fs";
import { expect, test, Page } from "@playwright/test";
const headers = { "X-Drive-Request": "1", Origin: "http://localhost:3001" };
async function login(page: Page) {
  // Reuse the isolated test account session; keep the production sign-in limiter unchanged.
  const statePath = path.join(
    process.env.DRIVE_E2E_MAIL_FOLDER!,
    "controls-session.json",
  );
  if (existsSync(statePath)) {
    await page
      .context()
      .addCookies(JSON.parse(readFileSync(statePath, "utf8")).cookies);
    return;
  }
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
  await page.context().storageState({ path: statePath });
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

test("explicit manager eligibility and safe unused employee deletion", async ({
  page,
}) => {
  await login(page);
  for (const [name, manager] of [
    ["Jon Aurand", false],
    ["Sarah Controls", true],
  ] as const) {
    await page.goto("/employees");
    await page.getByLabel("Name", { exact: true }).fill(name);
    if (manager) await page.getByLabel("Can manage employees").check();
    await page.getByRole("button", { name: "Create employee" }).click();
    await expect(page.getByRole("link", { name, exact: true })).toBeVisible();
  }
  await page.goto("/employees");
  await expect(
    page
      .getByLabel("Manager", { exact: true })
      .locator("option")
      .filter({ hasText: "Sarah Controls" }),
  ).toHaveCount(1);
  await expect(
    page
      .getByLabel("Manager", { exact: true })
      .locator("option")
      .filter({ hasText: "Jon Aurand" }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: "Jon Aurand", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Jon Aurand", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Can manage employees").check();
  await page.getByRole("button", { name: "Save employee" }).click();
  await expect(page.getByLabel("Can manage employees")).toBeChecked();
  await page.goto("/employees");
  await expect(
    page
      .getByLabel("Manager", { exact: true })
      .locator("option")
      .filter({ hasText: "Jon Aurand" }),
  ).toHaveCount(1);
  await page
    .getByLabel("Name", { exact: true })
    .fill("Accidental Controls Employee");
  await page.getByRole("button", { name: "Create employee" }).click();
  await page
    .getByRole("link", { name: "Accidental Controls Employee", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Permanently delete employee" })
    .click();
  await expect(
    page.getByRole("button", { name: "Confirm permanent deletion" }),
  ).toBeDisabled();
  await page.getByLabel("Type DELETE to confirm").fill("DELETE");
  await page
    .getByRole("button", { name: "Confirm permanent deletion" })
    .click();
  await expect(page).toHaveURL(/\/employees$/);
  await expect(
    page.getByRole("link", {
      name: "Accidental Controls Employee",
      exact: true,
    }),
  ).toHaveCount(0);
});

test("selected scorecards govern single, new and bulk evaluations; delete and archive retain integrity", async ({
  page,
}) => {
  await login(page);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const cards: Record<string, string> = {};
  for (const [name, categories] of [
    [
      "Customer Service Controls",
      [
        ["Greeting", 50],
        ["Closing", 50],
      ],
    ],
    [
      "Sales Controls",
      [
        ["Verification", 70],
        ["Documentation", 30],
      ],
    ],
  ] as const) {
    const draft = await (
      await page.request.post("/api/rubrics", {
        headers,
        data: {
          name,
          categories: categories.map(([label, weight]) => ({
            name: label,
            weight,
            criteria: `Check ${label}`,
            description: "",
          })),
        },
      })
    ).json();
    const published = await page.request.post(
      `/api/rubrics/${draft.id}/activate`,
      { headers, data: { revision: 1 } },
    );
    expect(published.ok()).toBeTruthy();
    cards[name] = draft.id;
  }
  await page.goto("/upload");
  await page.getByLabel("Choose audio recording").setInputFiles({
    name: "scorecard-controls.wav",
    mimeType: "audio/wav",
    buffer: wav(220),
  });
  await expect(
    page.getByRole("button", { name: "Upload & process" }),
  ).toBeDisabled();
  await page
    .getByLabel("Scorecard", { exact: true })
    .selectOption(cards["Customer Service Controls"]);
  await page.getByRole("button", { name: "Upload & process" }).click();
  await expect(page.locator(".status.completed")).toBeVisible({
    timeout: 20000,
  });
  await expect(page.locator(".qa-panel .panel-heading").first()).toContainText(
    "Customer Service Controls",
  );
  await expect(page.locator(".category-list details")).toHaveCount(2);
  await expect(page.locator(".category-list")).toContainText("Greeting");
  await page
    .getByRole("button", { name: "New QA evaluation", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByLabel("Scorecard", { exact: true })
    .selectOption(cards["Sales Controls"]);
  await expect(page.getByRole("dialog")).toContainText("Sales Controls");
  await page.getByRole("button", { name: "Start new evaluation" }).click();
  await expect(page.locator(".qa-panel .panel-heading").first()).toContainText(
    "Sales Controls",
    { timeout: 20000 },
  );
  await expect(page.locator(".category-list")).toContainText("Verification");
  await expect(page.locator(".category-list")).toContainText("Documentation");
  await page.getByRole("button", { name: "Evaluation history" }).click();
  await expect(page.locator(".history-evaluation")).toHaveCount(2);
  await expect(page.getByRole("dialog")).toContainText(
    "Customer Service Controls",
  );
  await expect(page.getByRole("dialog")).toContainText("Sales Controls");
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page
    .getByLabel("Assigned employee", { exact: true })
    .selectOption({ label: "Jon Aurand" });
  await page.getByRole("button", { name: "Save assignment" }).click();
  await page.getByRole("link", { name: "Jon Aurand", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Jon Aurand", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Permanently delete employee" })
    .click();
  await page.getByLabel("Type DELETE to confirm").fill("DELETE");
  await page
    .getByRole("button", { name: "Confirm permanent deletion" })
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "Permanent deletion blocked",
  );
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await page
    .getByRole("button", { name: "Archive employee", exact: true })
    .click();
  await page.getByRole("button", { name: "Confirm archive" }).click();
  await expect(
    page.getByText("INACTIVE EMPLOYEE", { exact: true }),
  ).toBeVisible();
  await page.goto("/batches");
  await page
    .getByLabel("Scorecard", { exact: true })
    .selectOption(cards["Sales Controls"]);
  await page.getByLabel("Choose batch recordings").setInputFiles(
    [221, 222].map((i) => ({
      name: `controls-batch-${i}.wav`,
      mimeType: "audio/wav",
      buffer: wav(i),
    })),
  );
  await page.getByRole("button", { name: "Submit batch" }).click();
  const batch = page
    .locator(".batch-panel")
    .filter({ hasText: "controls-batch-221.wav" });
  await expect(batch.locator(".batch-counts")).toContainText("2 Complete", {
    timeout: 20000,
  });
  await expect(batch).toContainText("Sales Controls");
  await batch
    .getByRole("link", { name: "controls-batch-221.wav", exact: true })
    .click();
  await expect(page.locator(".qa-panel .panel-heading").first()).toContainText(
    "Sales Controls",
  );
  await page
    .getByRole("button", { name: "Delete interaction", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Confirm permanent deletion" }),
  ).toBeDisabled();
  await page.screenshot({
    path: "test-results/delete-interaction-confirmation.png",
    fullPage: true,
  });
  await page.getByLabel("Type DELETE to confirm").fill("DELETE");
  await page
    .getByRole("button", { name: "Confirm permanent deletion" })
    .click();
  await expect(page).toHaveURL(/\/calls$/);
  await expect(
    page.getByRole("link", {
      name: "Open controls-batch-221.wav",
      exact: true,
    }),
  ).toHaveCount(0);
  await page.goto("/batches");
  await expect(
    page.getByText("Deleted interaction", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/batch-deletion-tombstone.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
