import { expect, test } from "@playwright/test";
import path from "node:path";
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
test("review attributes, retain removals, search and exclude verified related calls", async ({
  page,
}) => {
  test.setTimeout(120000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const login = await page.request.post("/api/auth/login", {
    headers,
    data: {
      email: "reviewer@example.test",
      password: process.env.DRIVE_TEST_PASSWORD!,
    },
  });
  expect(login.ok()).toBeTruthy();
  // Reuse this isolated session in later non-authentication workflows so
  // adding coverage does not exhaust the unchanged production login limiter.
  await page
    .context()
    .storageState({
      path: path.join(
        process.env.DRIVE_E2E_MAIL_FOLDER!,
        "controls-session.json",
      ),
    });
  const rubrics = await (await page.request.get("/api/rubrics")).json();
  const ids: string[] = [];
  try {
    for (const index of [201, 202]) {
      const uploaded = await page.request.post("/api/calls", {
        headers,
        multipart: {
          rubric_id: rubrics[0].id,
          file: {
            name: `intelligence-${index}.wav`,
            mimeType: "audio/wav",
            buffer: wav(index),
          },
        },
      });
      expect(uploaded.status()).toBe(201);
      const call = await uploaded.json();
      ids.push(call.id);
      await page.goto(`/calls/${call.id}`);
      await expect(page.locator(".status.completed")).toBeVisible({
        timeout: 30000,
      });
      await expect(
        page.getByRole("heading", { name: "Call intelligence", exact: true }),
      ).toBeVisible();
      await page.getByLabel("Order # value", { exact: true }).fill("ZX-104582");
      await page
        .getByRole("button", { name: "Save & verify Order #", exact: true })
        .click();
      await expect(
        page
          .locator(".intelligence-attribute")
          .filter({ has: page.getByLabel("Order # value", { exact: true }) }),
      ).toContainText("Verified");
    }
    await page.getByLabel("Customer value", { exact: true }).fill("John Smith");
    await page
      .getByRole("button", { name: "Save & verify Customer", exact: true })
      .click();
    await expect(page.locator(".intelligence-panel")).toContainText(
      "1 matching interaction",
    );
    await page
      .getByRole("button", { name: "Remove relationship", exact: true })
      .click();
    await expect(page.locator(".intelligence-panel")).toContainText(
      "0 matching interactions",
    );
    await page
      .getByRole("button", { name: "Remove Customer", exact: true })
      .click();
    await expect(
      page.getByLabel("Customer value", { exact: true }),
    ).toHaveValue("");
    await page
      .getByRole("button", { name: "Recheck saved transcript", exact: true })
      .click();
    await expect(
      page.getByLabel("Customer value", { exact: true }),
    ).toHaveValue("");
    await page
      .locator("summary")
      .filter({ hasText: "Attribute history" })
      .click();
    await expect(
      page.locator(".intelligence-panel .audit-history"),
    ).toContainText("John Smith");
    await page.screenshot({
      path: "test-results/intelligence-review.png",
      fullPage: true,
    });
    await page.goto("/calls");
    await page
      .getByLabel("Search attribute", { exact: true })
      .selectOption("order");
    await page
      .getByLabel("Search attribute value", { exact: true })
      .fill("zx104582");
    await page
      .getByRole("button", { name: "Search attributes", exact: true })
      .click();
    await expect(page.locator(".intelligence-result")).toHaveCount(2);
    await page
      .getByText("Company transcription vocabulary (optional)", { exact: true })
      .click();
    await expect(
      page.getByText("Registered company:", { exact: false }),
    ).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: "test-results/intelligence-mobile.png",
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    expect(errors).toEqual([]);
  } finally {
    for (const id of ids) {
      const deleted = await page.request.delete(`/api/calls/${id}`, {
        headers,
      });
      expect(deleted.ok()).toBeTruthy();
    }
  }
});
