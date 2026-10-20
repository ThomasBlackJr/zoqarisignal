import { expect, test } from "@playwright/test";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

function mailFor(email: string) {
  return readdirSync(process.env.DRIVE_E2E_MAIL_FOLDER!)
    .filter((name) => name.endsWith(".txt"))
    .map((name) =>
      readFileSync(path.join(process.env.DRIVE_E2E_MAIL_FOLDER!, name), "utf8"),
    )
    .filter((message) => message.includes(`To: ${email}`));
}

test("short passwords are blocked before registration, including scripted autofill", async ({
  page,
}) => {
  const email = "short-password@registration.test";
  let submissions = 0;
  await page.route("**/api/auth/register", async (route) => {
    submissions += 1;
    await route.abort();
  });
  await page.goto("/register");
  await page.getByLabel("Your name").fill("Registration Test");
  await page.getByLabel("Business email").fill(email);
  await page.getByLabel("New password").fill("Short12!");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  expect(
    await page
      .getByLabel("New password")
      .evaluate((input: HTMLInputElement) => input.validity.tooShort),
  ).toBe(true);
  // Browser minlength does not reliably apply to values assigned by scripts/password managers.
  for (const password of ["Tiny12!", "Abcdef12!XY", "😀😁😂😃😄😅"]) {
    await page
      .getByLabel("New password")
      .evaluate((input: HTMLInputElement, value) => {
        input.value = value;
        input.form!.requestSubmit();
      }, password);
    await expect(page.locator(".error[role=alert]")).toContainText(
      "at least 12 characters",
    );
  }
  expect(submissions).toBe(0);
  expect(mailFor(email)).toHaveLength(0);
  await expect(page).toHaveURL(/\/register$/);
});

test("one valid registration survives a second submit while mail response is pending", async ({
  page,
}) => {
  const email = "valid-password@registration.test";
  const requests: number[] = [];
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  let accepted!: () => void;
  const submitted = new Promise<void>((resolve) => {
    accepted = resolve;
  });
  await page.route("**/api/auth/register", async (route) => {
    requests.push(route.request().postDataJSON().password.length);
    const response = await route.fetch();
    if (requests.length === 1) {
      expect(response.status()).toBe(201);
      accepted();
      await gate;
    }
    await route.fulfill({ response });
  });
  try {
    await page.goto("/register");
    await page.getByLabel("Your name").fill("Registration Test");
    await page.getByLabel("Business email").fill(email);
    await page.getByLabel("New password").fill("SafePass12!X");
    const registration = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/auth/register") &&
        response.status() === 201,
    );
    await page
      .getByRole("button", { name: "Create account", exact: true })
      .click();
    await submitted;
    expect(mailFor(email)).toHaveLength(1);
    // Force a second submit even if the UI is disabled; it must be ignored synchronously.
    await page
      .getByLabel("New password")
      .evaluate((input: HTMLInputElement) => {
        input.value = "Short12!";
        input.form!.requestSubmit();
      });
    await expect(page.getByLabel("New password")).toBeDisabled();
    release();
    const response = await registration;
    const challenge = (await response.json()).challenge;
    await expect(
      page.getByRole("heading", { name: "Verify your email" }),
    ).toBeVisible();
    expect(requests).toEqual([12]);
    expect(
      new URLSearchParams(new URL(page.url()).hash.slice(1)).get("challenge"),
    ).toBe(challenge);
    await expect(page.getByText(/v\*\*\*@registration.test/)).toBeVisible();
    await expect(page.locator(".error[role=alert]")).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: /Resend code in/ }),
    ).toBeDisabled();
    const cooldown = await page.request.post(
      "/api/auth/verification-code/resend",
      {
        headers: { "X-Drive-Request": "1", Origin: "http://localhost:3001" },
        data: { challenge },
      },
    );
    expect(cooldown.status()).toBe(429);
    expect(mailFor(email)).toHaveLength(1);
    const code = mailFor(email)[0].match(/Verification code: ([0-9]{6})/)![1];
    await page
      .getByLabel("Verification code", { exact: true })
      .fill(code === "000000" ? "000001" : "000000");
    await page
      .getByRole("button", { name: "Verify email", exact: true })
      .click();
    await expect(page.locator(".error[role=alert]")).toContainText(
      "Code is invalid, expired or already used",
    );
    await expect(page).toHaveURL(/\/verify-email#/);
    await page.getByLabel("Verification code", { exact: true }).fill(code);
    await page
      .getByRole("button", { name: "Verify email", exact: true })
      .click();
    await page.getByRole("link", { name: "Continue to Signal" }).click();
    await expect(
      page.getByRole("heading", { name: "Dashboard", exact: true }),
    ).toBeVisible();
    await page.goto("/account");
    await expect(page.getByLabel("Business name")).toBeVisible();
  } finally {
    release();
  }
});

test("successful registration retires the password form while verification navigation is delayed", async ({
  page,
}) => {
  const challenge = "synthetic-browser-challenge-" + "x".repeat(20);
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/auth/register", (route) =>
    route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ challenge }),
    }),
  );
  await page.route(/\/verify-email(?:\?|$)/, async (route) => {
    await gate;
    await route.continue();
  });
  try {
    await page.goto("/register");
    await page.getByLabel("Your name").fill("Navigation Test");
    await page
      .getByLabel("Business email")
      .fill("navigation@registration.test");
    await page.getByLabel("New password").fill("SafePass12!X");
    await page
      .getByRole("button", { name: "Create account", exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText(
      "Registration submitted",
    );
    await expect(page.getByLabel("New password")).toHaveCount(0);
    await expect(
      page.getByRole("link", { name: "Continue", exact: true }),
    ).toHaveAttribute(
      "href",
      `/verify-email#challenge=${challenge}&email=n***%40registration.test`,
    );
    release();
    await expect(
      page.getByRole("heading", { name: "Verify your email" }),
    ).toBeVisible();
  } finally {
    release();
  }
});
