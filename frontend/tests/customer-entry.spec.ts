import { expect, test } from "@playwright/test";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

function localLink(email: string, purpose: string) {
  const folder = process.env.DRIVE_E2E_MAIL_FOLDER!;
  const messages = readdirSync(folder)
    .filter((name) => name.endsWith(".txt"))
    .sort(
      (a, b) =>
        statSync(path.join(folder, b)).mtimeMs -
        statSync(path.join(folder, a)).mtimeMs,
    )
    .map((name) =>
      readFileSync(path.join(folder, name), "utf8").replace(/\r\n/g, "\n"),
    );
  const message = messages.find(
    (text) =>
      text.includes("To: " + email + "\n") &&
      text.includes("Purpose: " + purpose + "\n"),
  );
  if (!message) throw new Error("Expected test outbox message");
  if (purpose === "verify_code")
    return message.match(/Verification code: ([0-9]{6})/)![1];
  return message.split("\n").find((line) => line.startsWith("http"))!;
}

function recording() {
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
  return data;
}

test("credential forms cannot submit a GET before JavaScript is ready", async ({
  browser,
}) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  for (const route of [
    "login",
    "register",
    "forgot-password",
    "reset-password",
  ]) {
    await page.goto("http://localhost:3001/" + route);
    await expect(page.locator("form")).toHaveAttribute("method", "post");
    await expect(page.locator("form button")).toBeDisabled();
  }
  await context.close();
});

test("customer registers, verifies, creates an isolated business, activates development access and reviews", async ({
  page,
}) => {
  test.setTimeout(150000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const email = "new-owner@customer.test";
  await page.goto("/login");
  await page.getByRole("link", { name: "Create an account" }).click();
  await page.getByLabel("Your name").fill("Customer Owner");
  await page.getByLabel("Business email").fill(email);
  await page.getByLabel("New password").fill(process.env.DRIVE_TEST_PASSWORD!);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Verify your email" }),
  ).toBeVisible();
  await expect(
    page.getByText(/LOCAL DEVELOPMENT · No email was sent/),
  ).toBeVisible();
  const originalCode = localLink(email, "verify_code");
  const originalChallenge = new URLSearchParams(
    new URL(page.url()).hash.slice(1),
  ).get("challenge");
  await expect(
    page.getByLabel("Verification code", { exact: true }),
  ).toHaveAttribute("autocomplete", "one-time-code");
  await expect(
    page.getByRole("button", { name: /Resend code in/ }),
  ).toBeDisabled();
  await page
    .getByLabel("Verification code", { exact: true })
    .fill(originalCode === "000000" ? "000001" : "000000");
  await page.getByRole("button", { name: "Verify email", exact: true }).click();
  await expect(page.locator(".error[role=alert]")).toContainText(
    "Code is invalid, expired or already used",
  );
  const resend = page.getByRole("button", { name: "Resend code", exact: true });
  await expect(resend).toBeEnabled({ timeout: 70000 });
  await resend.click();
  await expect(page.getByRole("status")).toContainText(
    "A new code was requested",
  );
  await expect(
    page.getByLabel("Verification code", { exact: true }),
  ).toHaveValue("");
  const newChallenge = new URLSearchParams(
    new URL(page.url()).hash.slice(1),
  ).get("challenge");
  expect(newChallenge).not.toBe(originalChallenge);
  const oldAttempt = await page.request.post("/api/auth/verify-email", {
    headers: { "X-Drive-Request": "1", Origin: "http://localhost:3001" },
    data: { code: originalCode, challenge: originalChallenge },
  });
  expect(oldAttempt.status()).toBe(400);
  await page
    .getByLabel("Verification code", { exact: true })
    .fill(localLink(email, "verify_code"));
  await page.getByRole("button", { name: "Verify email", exact: true }).click();
  await page.getByRole("link", { name: "Continue to Signal" }).click();
  await expect(
    page.getByRole("heading", { name: "Dashboard", exact: true }),
  ).toBeVisible();
  await page.goto("/account");
  await page.getByLabel("Business name").fill("Customer Services");
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(
    page.getByRole("heading", { name: "Signal Access" }),
  ).toBeVisible();
  // Direct navigation cannot bypass the backend access boundary.
  await page.goto("/upload");
  await expect(page).toHaveURL(/\/upload$/);
  await expect(
    page.getByRole("button", { name: "Beta access required", exact: true }),
  ).toBeDisabled();
  await page.goto("/account");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/customer-access-mobile.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Activate development access", exact: true })
    .click();
  await expect(
    page.getByText("No payment was taken.", { exact: false }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Setup guide (optional)" }).click();
  await expect(
    page.getByRole("heading", { name: "Your first quality review" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({
    path: "test-results/customer-setup-desktop.png",
    fullPage: true,
  });
  await page
    .getByRole("link", { name: "Review scorecards", exact: true })
    .click();
  await page
    .getByRole("button", { name: /Dispatch QA starter Version 1.0/ })
    .click();
  await expect(
    page.getByRole("button", { name: "Duplicate as draft" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Setup guide" }).click();
  await page
    .getByRole("link", { name: "Upload a recording", exact: true })
    .click();
  await page.getByLabel("Choose audio recording").setInputFiles({
    name: "customer-first.wav",
    mimeType: "audio/wav",
    buffer: recording(),
  });
  await page
    .getByLabel("Scorecard", { exact: true })
    .selectOption({ index: 1 });
  await page.getByRole("button", { name: "Upload & process" }).click();
  await expect(page.locator(".status.completed")).toBeVisible({
    timeout: 20000,
  });
  await expect(page.locator(".final-score strong")).toHaveText("90 / 100");
  await page.getByRole("link", { name: "Setup guide" }).click();
  await page.getByRole("button", { name: "Finish setup", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Dashboard", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Account & access" }).click();
  await page.getByRole("button", { name: "Log out", exact: true }).click();
  await page.getByLabel("Work email").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DRIVE_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Sign in to Signal" }).click();
  await expect(
    page.getByRole("heading", { name: "Dashboard", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: /customer-first.wav/ }).first(),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("password recovery uses the real local mail adapter and new password", async ({
  page,
}) => {
  const email = "recovery@customer.test";
  await page.goto("/register");
  await page.getByLabel("Your name").fill("Recovery Customer");
  await page.getByLabel("Business email").fill(email);
  await page.getByLabel("New password").fill(process.env.DRIVE_TEST_PASSWORD!);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Verify your email" }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "reset your password", exact: true })
    .click();
  await page.getByLabel("Business email").fill(email);
  await page.getByRole("button", { name: "Request reset link" }).click();
  await expect(page.getByRole("status")).toContainText("no email was sent");
  await page.goto(localLink(email, "reset"));
  await page.getByLabel("New password").fill("new-customer-passphrase-123");
  await page.getByRole("button", { name: "Change password" }).click();
  await page.getByRole("link", { name: "Back to sign in" }).click();
  await page.getByLabel("Work email").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("new-customer-passphrase-123");
  await page.getByRole("button", { name: "Sign in to Signal" }).click();
  await expect(
    page.getByRole("heading", { name: "Verify your email" }),
  ).toBeVisible();
});
