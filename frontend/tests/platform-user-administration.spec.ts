import { expect, test } from "@playwright/test";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

test("platform account lifecycle and confirmed ownership transfer retain the old Owner", async ({
  page,
  browser,
}) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("platform@example.test");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DRIVE_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Sign in to Signal" }).click();
  await expect(page).toHaveURL(/\/platform$/);
  await page.goto("/platform/users/new");
  const email = `admin-lifecycle-${Date.now()}@example.test`;
  await page.getByLabel("First name", { exact: true }).fill("Synthetic");
  await page.getByLabel("Last name", { exact: true }).fill("Candidate");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page
    .getByLabel("Reason", { exact: true })
    .fill("Synthetic account lifecycle");
  await page.getByLabel("I confirm this administrative change.").check();
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(page).toHaveURL(/\/platform\/users\/[a-f0-9-]+$/);
  const id = page.url().split("/").pop()!;
  const headers = { "X-Drive-Request": "1", Origin: "http://localhost:3001" };
  // Credentials stay inside the private test outbox and request body.
  const folder = process.env.DRIVE_E2E_MAIL_FOLDER!;
  const messages = readdirSync(folder)
    .map((n) => readFileSync(path.join(folder, n), "utf8").replace(/\r\n/g, "\n"))
    .filter((t) => t.includes(`To: ${email}\n`));
  const code = messages.find((t) => t.includes("Purpose: verify_code\n"))?.match(/Verification code: (\d{6})/)?.[1];
  const resetMessage = messages.find((t) => t.includes("Purpose: reset\n"));
  const resetLink = resetMessage?.split("\n").find((t) => t.startsWith("http"));
  if (!code || !resetLink) throw new Error("Expected private setup messages");
  const resetToken = new URLSearchParams(new URL(resetLink).hash.slice(1)).get("token");
  const recipient = await browser.newContext();
  const password = process.env.DRIVE_TEST_PASSWORD!;
  expect((await recipient.request.post("http://localhost:3001/api/auth/reset-password", {
    headers, data: { token: resetToken, password },
  })).status()).toBe(200);
  expect((await recipient.request.post("http://localhost:3001/api/auth/login", {
    headers, data: { email, password },
  })).status()).toBe(200);
  const verified = await recipient.request.post("http://localhost:3001/api/auth/verify-email", {
    headers, data: { code },
  });
  expect(verified.status()).toBe(200);
  await recipient.close();
  await page.reload();
  await page.getByRole("button", { name: "Edit name", exact: true }).click();
  await page.getByLabel("First name", { exact: true }).fill("Updated");
  await page
    .getByLabel("Reason", { exact: true })
    .fill("Synthetic profile edit");
  await page.getByLabel("I confirm this administrative change.").check();
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Updated Candidate", exact: true }),
  ).toBeVisible();
  for (const action of [
    "Deactivate account",
    "Reactivate account",
    "Send password reset",
  ]) {
    await page.getByRole("button", { name: action, exact: true }).click();
    await page
      .getByLabel("Reason", { exact: true })
      .fill("Synthetic lifecycle check");
    await page.getByLabel("I confirm this administrative change.").check();
    await page.getByRole("button", { name: "Confirm", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(
      page.getByRole("heading", { name: "Updated Candidate", exact: true }),
    ).toBeVisible();
  }
  await page
    .getByRole("button", { name: "Change membership / role", exact: true })
    .click();
  const owners = await (
    await page.request.get("/api/platform/users?q=owner%40example.test")
  ).json();
  const oldOwner = owners.items.find(
    (u: { email: string }) => u.email === "owner@example.test",
  );
  await page
    .getByRole("combobox", { name: "New organization", exact: true })
    .selectOption(oldOwner.organization_id);
  await page
    .getByRole("combobox", { name: "Customer role", exact: true })
    .selectOption("ADMIN");
  await page
    .getByLabel("Reason", { exact: true })
    .fill("Synthetic membership assignment");
  await page.getByLabel("I confirm this administrative change.").check();
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.goto(`/platform/organizations/${oldOwner.organization_id}`);
  await page
    .getByRole("button", { name: "Transfer ownership", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Replacement Owner", exact: true })
    .selectOption(id);
  await page
    .getByLabel("Reason", { exact: true })
    .fill("Synthetic confirmed transfer");
  await page.getByLabel("I confirm this administrative change.").check();
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const previous = await (
    await page.request.get(`/api/platform/users/${oldOwner.id}`)
  ).json();
  const current = await (
    await page.request.get(`/api/platform/users/${id}`)
  ).json();
  expect(previous.role).toBe("ADMIN");
  expect(previous.active).toBe(true);
  expect(current.role).toBe("OWNER");
  await page.goto(`/platform/users/${id}`);
  await expect(
    page.getByRole("button", { name: "Deactivate account", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Remove membership", exact: true }),
  ).toBeDisabled();
  await page.screenshot({
    path: "test-results/platform-account-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/platform-account-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});
