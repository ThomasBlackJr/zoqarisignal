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

test("owner briefing evidence, coaching draft, customization and mobile", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  const person = await (
    await page.request.post("/api/employees", {
      headers,
      data: { name: "Briefing Manager", manager_eligible: true },
    })
  ).json();
  const report = await (
    await page.request.post("/api/employees", {
      headers,
      data: { name: "Briefing Employee", manager_id: person.id },
    })
  ).json();
  const card = await (
    await page.request.post("/api/rubrics", {
      headers,
      data: {
        name: "Briefing Standard",
        categories: [
          {
            name: "Closing review",
            weight: 100,
            description: "A complete closing",
            criteria: "Summarize the next steps and offer further assistance.",
          },
        ],
      },
    })
  ).json();
  expect(
    (
      await page.request.post(`/api/rubrics/${card.id}/activate`, {
        headers,
        data: { revision: card.revision },
      })
    ).ok(),
  ).toBeTruthy();
  for (let i = 0; i < 5; i++) {
    const r = await page.request.post("/api/calls", {
      headers,
      multipart: {
        rubric_id: card.id,
        file: {
          name: `briefing-${i}.wav`,
          mimeType: "audio/wav",
          buffer: wav(i + 110),
        },
      },
    });
    expect(r.ok()).toBeTruthy();
    const call = await r.json();
    expect(
      (
        await page.request.post(`/api/calls/${call.id}/assignment`, {
          headers,
          data: { employee_id: report.id, revision: 0 },
        })
      ).ok(),
    ).toBeTruthy();
    await expect
      .poll(
        async () =>
          (await (await page.request.get(`/api/calls/${call.id}`)).json())
            .status,
      )
      .toBe("completed");
  }
  await page.goto("/");
  await page.getByRole("button", { name: "Customize dashboard" }).click();
  await page.getByRole("button", { name: "Restore defaults" }).click();
  await page.getByRole("button", { name: "Save dashboard" }).click();
  await expect(
    page.getByRole("heading", { name: "Frequent Quality Issues", exact: true }),
  ).toBeVisible();
  const issue = page
    .locator(".briefing-issues article")
    .filter({
      has: page.getByRole("heading", { name: "Closing review", exact: true }),
    })
    .first();
  await expect(issue).toContainText("5 of 5");
  await issue.getByRole("button", { name: "View evidence" }).click();
  await expect(page.getByRole("dialog")).toContainText("Briefing Employee");
  await expect(page.getByRole("dialog")).toContainText(
    "Synthetic rubric demonstration",
  );
  await page
    .getByRole("button", { name: "Generate coaching recommendation" })
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "Consider walking through the scorecard requirements",
  );
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Create Team Email", exact: true })
    .click();
  await expect(page.getByLabel("Email draft", { exact: true })).toHaveValue(
    /Summarize the next steps and offer further assistance/,
  );
  await expect(
    page.getByLabel("Email draft", { exact: true }),
  ).not.toContainText("Briefing Employee");
  await page
    .getByLabel("Subject", { exact: true })
    .fill("Team review reminder");
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.getByRole("button", { name: "Copy draft" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Draft copied. No email was sent.",
  );
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain(
    "Subject: Team review reminder",
  );
  await page.getByRole("button", { name: "Regenerate", exact: true }).click();
  await page.getByRole("button", { name: "Keep edits" }).click();
  await page.screenshot({ path: "test-results/briefing-email.png" });
  await page.getByRole("button", { name: "Close", exact: true }).click();
  const teams = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Team Performance", exact: true }),
  });
  await teams
    .getByRole("link", { name: "Briefing Manager", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: /Briefing Manager/ }),
  ).toBeVisible();
  await page.goto("/");
  await page.getByRole("button", { name: "Customize dashboard" }).click();
  await page
    .getByRole("checkbox", { name: "Frequent Quality Issues", exact: true })
    .uncheck();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Frequent Quality Issues", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Customize dashboard" }).click();
  await page
    .getByRole("checkbox", { name: "Recent interactions", exact: true })
    .uncheck();
  await page
    .getByRole("button", { name: "Move Frequent Quality Issues up" })
    .click();
  await page.getByRole("button", { name: "Save dashboard" }).click();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Recent interactions", exact: true }),
  ).not.toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Frequent Quality Issues", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Appearance", { exact: true }).selectOption("light");
  await page.screenshot({
    path: "test-results/owner-dashboard-light.png",
    fullPage: true,
  });
  await page.getByLabel("Appearance", { exact: true }).selectOption("dark");
  await page.screenshot({
    path: "test-results/owner-dashboard-dark.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/owner-dashboard-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
