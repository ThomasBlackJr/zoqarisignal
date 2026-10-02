import { expect, test } from "@playwright/test";
import path from "node:path";
import { existsSync, readFileSync } from "node:fs";

const headers = { "X-Drive-Request": "1", Origin: "http://localhost:3001" };
function wav(index: number) {
  const b = Buffer.alloc(16044);
  b.write("RIFF");
  b.writeUInt32LE(16036, 4);
  b.write("WAVEfmt ", 8);
  b.writeUInt32LE(16, 16);
  b.writeUInt16LE(1, 20);
  b.writeUInt16LE(1, 22);
  b.writeUInt32LE(8000, 24);
  b.writeUInt32LE(16000, 28);
  b.writeUInt16LE(2, 32);
  b.writeUInt16LE(16, 34);
  b.write("data", 36);
  b.writeUInt32LE(16000, 40);
  b[16043] = index;
  return b;
}

test("operator batch, audit evidence, flag lifecycle and mobile navigation", async ({
  page,
}) => {
  const statePath = path.join(
    process.env.DRIVE_E2E_MAIL_FOLDER!,
    "controls-session.json",
  );
  if (existsSync(statePath))
    await page
      .context()
      .addCookies(JSON.parse(readFileSync(statePath, "utf8")).cookies);
  else {
    const auth = await page.request.post("/api/auth/login", {
      headers,
      data: {
        email: "reviewer@example.test",
        password: process.env.DRIVE_TEST_PASSWORD!,
      },
    });
    expect(auth.ok()).toBeTruthy();
    await page.context().storageState({ path: statePath });
  }
  const created = await page.request.post("/api/employees", {
    headers,
    data: { name: "Sprint Operator" },
  });
  expect(created.status()).toBe(201);
  const operator = await created.json();
  await page.goto("/flagged-terms");
  await page.getByLabel("Term or phrase").fill("delivery");
  // A previous full-suite test may already have created this rule.
  const existing = await (await page.request.get("/api/flag-rules")).json();
  if (!existing.items.some((r: { phrase: string }) => r.phrase === "delivery"))
    await page.getByRole("button", { name: "Add Flag", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Edit delivery", exact: true }),
  ).toBeVisible();
  await page.goto("/batches");
  await page
    .getByLabel("Scorecard", { exact: true })
    .selectOption({ index: 1 });
  await page.getByLabel("Choose batch recordings").setInputFiles([
    { name: "sprint-one.wav", mimeType: "audio/wav", buffer: wav(231) },
    { name: "sprint-two.wav", mimeType: "audio/wav", buffer: wav(232) },
    {
      name: "sprint-invalid.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("invalid"),
    },
  ]);
  await expect(
    page
      .getByLabel("Assign operator")
      .locator("option", { hasText: "Sprint Operator" }),
  ).toHaveCount(1);
  await page.getByLabel("Assign operator").selectOption(operator.id);
  await expect(
    page.getByLabel("Apply selected operator to all new calls"),
  ).toBeChecked();
  await page
    .getByRole("button", { name: "Upload & process", exact: true })
    .click();
  const panel = page
    .locator(".batch-panel")
    .filter({ hasText: "sprint-one.wav" });
  await expect(panel.getByText("2 Complete", { exact: true })).toBeVisible({
    timeout: 30000,
  });
  await expect(panel.getByText("1 Failed", { exact: true })).toBeVisible();
  await expect(
    panel.getByRole("cell", { name: "Sprint Operator", exact: true }),
  ).toHaveCount(2);
  await page.screenshot({
    path: "test-results/sprint-batch-desktop.png",
    fullPage: true,
  });
  await panel.getByRole("link", { name: "sprint-one.wav" }).click();
  await expect(page).toHaveURL(/\/calls\/[^/]+$/);
  const callUrl = page.url();
  await expect(
    page.getByRole("heading", { name: "Transcript", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Sprint Operator", exact: true }),
  ).toBeVisible();
  await expect(page.locator("blockquote").first()).toBeVisible();
  await page.goto("/flagged-terms");
  await page
    .getByRole("button", { name: "Edit delivery", exact: true })
    .click();
  await page.getByLabel("Term or phrase").fill("Sprint phrase replacement");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: "Delete Sprint phrase replacement",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Delete Sprint phrase replacement",
      exact: true,
    })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Delete Sprint phrase replacement",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Delete Sprint phrase replacement",
      exact: true,
    })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Delete rule", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Edit Sprint phrase replacement",
      exact: true,
    }),
  ).toHaveCount(0);
  await page.goto(callUrl);
  await expect(
    page.getByRole("heading", { name: /delivery.*Deleted rule/ }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/sprint-audit-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.goto("/upload");
  await expect(page.getByLabel("Assign operator")).toBeVisible();
  await page
    .getByRole("link", { name: "Scorecards", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Scorecards", exact: true }),
  ).toBeVisible();
});

test("flag evidence refreshes when processing completes at revision zero", async ({
  page,
}) => {
  const statePath = path.join(
    process.env.DRIVE_E2E_MAIL_FOLDER!,
    "controls-session.json",
  );
  await page
    .context()
    .addCookies(JSON.parse(readFileSync(statePath, "utf8")).cookies);
  const response = await page.request.post("/api/calls", {
    headers,
    multipart: {
      file: {
        name: "flag-refresh.wav",
        mimeType: "audio/wav",
        buffer: wav(239),
      },
    },
  });
  const { id } = await response.json();
  let completed = false;
  await page.route(`**/api/calls/${id}`, async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    await route.fulfill({
      response,
      json: {
        ...body,
        status: completed ? "completed" : "transcribing",
        transcript: null,
        evaluation: null,
      },
    });
  });
  await page.route(`**/api/calls/${id}/flags?*`, (route) =>
    route.fulfill({
      json: {
        transcript_revision: 0,
        items: completed
          ? [
              {
                id: "fixture-flag",
                phrase: "fresh evidence",
                severity: "attention",
                transcript_revision: 0,
                rule_revision: 1,
                matches: [
                  {
                    quote: "Synthetic flag evidence",
                    role: "UNKNOWN",
                    start: null,
                    source_start: 0,
                    source_end: 8,
                  },
                ],
              },
            ]
          : [],
      },
    }),
  );
  await page.goto(`/calls/${id}`);
  await expect(page.getByText(/No matches recorded/)).toBeVisible();
  completed = true;
  await expect(
    page.getByRole("heading", { name: "fresh evidence · attention" }),
  ).toBeVisible({ timeout: 10000 });
});
