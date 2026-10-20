import { expect, test } from "@playwright/test";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

function message(email: string, purpose: string) {
  const folder = process.env.DRIVE_E2E_MAIL_FOLDER!;
  const item = readdirSync(folder)
    .filter((n) => n.endsWith(".txt"))
    .sort(
      (a, b) =>
        statSync(path.join(folder, b)).mtimeMs -
        statSync(path.join(folder, a)).mtimeMs,
    )
    .map((n) =>
      readFileSync(path.join(folder, n), "utf8").replaceAll("\r\n", "\n"),
    )
    .find(
      (t) =>
        t.includes(`To: ${email}\n`) && t.includes(`Purpose: ${purpose}\n`),
    );
  if (!item) throw new Error("Synthetic lifecycle mail was not found");
  return purpose === "verify_code"
    ? item.match(/Verification code: ([0-9]{6})/)![1]
    : item.split("\n").find((l) => l.startsWith("http"))!;
}

test("complete free-pilot lifecycle through separately authorized platform controls", async ({
  browser,
}) => {
  test.setTimeout(180000);
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  const operatorContext = await browser.newContext();
  const admin = await operatorContext.newPage();
  const employeeContext = await browser.newContext();
  const employee = await employeeContext.newPage();
  const ownerEmail = "lifecycle-owner@uspack.test";
  const employeeEmail = "lifecycle-employee@uspack.test";
  const password = process.env.DRIVE_TEST_PASSWORD!;
  const orgName = "USPack lifecycle browser";
  await owner.goto("/register");
  await owner.getByLabel("Your name").fill("USPack Owner");
  await owner.getByLabel("Business email").fill(ownerEmail);
  await owner.getByLabel("New password").fill(password);
  await owner
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    owner.getByRole("heading", { name: "Verify your email" }),
  ).toBeVisible();
  await expect(owner.getByText(/l\*\*\*@uspack.test/)).toBeVisible();
  await owner
    .getByLabel("Verification code", { exact: true })
    .fill(message(ownerEmail, "verify_code"));
  await owner
    .getByRole("button", { name: "Verify email", exact: true })
    .click();
  await owner.getByRole("link", { name: "Continue to Signal" }).click();
  await owner.goto("/account");
  await owner.getByLabel("Business name").fill(orgName);
  await owner
    .getByRole("button", { name: "Create organization", exact: true })
    .click();
  await expect(
    owner.getByRole("heading", { name: "Signal Access" }),
  ).toBeVisible();
  await expect(
    owner.getByText(/access is currently inactive/),
  ).toBeVisible();
  await expect(owner.getByText("Organization ID", { exact: true })).toHaveCount(
    0,
  );
  expect((await owner.request.get("/api/dashboard")).status()).toBe(200);
  expect(
    (
      await owner.request.post("/api/calls/missing/retry", {
        headers: { "X-Drive-Request": "1", Origin: "http://localhost:3001" },
      })
    ).status(),
  ).toBe(403);
  expect((await owner.request.get("/api/platform/users")).status()).toBe(403);
  await owner.setViewportSize({ width: 390, height: 844 });
  await owner.screenshot({
    path: "test-results/lifecycle-pending-mobile.png",
    fullPage: true,
  });

  await owner.goto("/");
  await expect(
    owner.getByRole("heading", { name: "Dashboard", exact: true }),
  ).toBeVisible();
  await owner.goto("/upload");
  await expect(
    owner.getByRole("button", { name: "Beta access required", exact: true }),
  ).toBeDisabled();
  await owner.request.post("/api/auth/logout", {
    headers: { "X-Drive-Request": "1", Origin: "http://localhost:3001" },
  });
  await owner.goto("/login");
  await owner.getByLabel("Work email").fill(ownerEmail);
  await owner.getByLabel("Password", { exact: true }).fill(password);
  await owner.getByRole("button", { name: "Sign in to Signal" }).click();
  await expect(
    owner.getByRole("heading", { name: "Dashboard", exact: true }),
  ).toBeVisible();
  await admin.goto("/login");
  await admin.getByLabel("Work email").fill("platform@example.test");
  await admin.getByLabel("Password", { exact: true }).fill(password);
  await admin.getByRole("button", { name: "Sign in to Signal" }).click();
  await expect(admin).toHaveURL(/\/platform$/);
  await admin.goto("/platform/organizations");
  await admin.getByLabel("Search organizations", { exact: true }).fill(orgName);
  await admin.getByRole("link", { name: orgName, exact: true }).click();
  await expect(admin.getByRole("heading", { name: orgName, exact: true })).toBeVisible();
  const orgId = admin.url().split("/").pop()!;
  await admin.getByRole("button", { name: "Grant beta access", exact: true }).click();
  await admin.getByLabel("Expiration (your local time, optional)").fill("2099-01-01T00:00");
  await admin.getByLabel("Reason", { exact: true }).fill("Approved USPack browser beta");
  await admin.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(admin.getByRole("dialog")).toHaveCount(0);
  expect((await (await admin.request.get("/api/platform/activity")).json()).items.some(
    (event: { action: string; organization_id: string }) => event.action === "beta.grant" && event.organization_id === orgId,
  )).toBe(true);
  await admin.setViewportSize({ width: 390, height: 844 });
  await admin.screenshot({
    path: "test-results/lifecycle-platform-mobile.png",
    fullPage: true,
  });
  expect(
    await admin.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await owner.goto("/account");
  await owner
    .getByRole("button", { name: "Check access again", exact: true })
    .click();
  await expect(owner.getByText(/Your organization has Beta Access/)).toBeVisible();
  expect((await (await owner.request.get("/api/account")).json()).access_expires_at).toBeGreaterThan(Date.now() / 1000);
  const audio = Buffer.alloc(16044);
  audio.write("RIFF");
  audio.writeUInt32LE(16036, 4);
  audio.write("WAVEfmt ", 8);
  audio.writeUInt32LE(16, 16);
  audio.writeUInt16LE(1, 20);
  audio.writeUInt16LE(1, 22);
  audio.writeUInt32LE(8000, 24);
  audio.writeUInt32LE(16000, 28);
  audio.writeUInt16LE(2, 32);
  audio.writeUInt16LE(16, 34);
  audio.write("data", 36);
  audio.writeUInt32LE(16000, 40);
  const upload = await owner.request.post("/api/calls", {
    headers: { "X-Drive-Request": "1", Origin: "http://localhost:3001" },
    multipart: {
      file: { name: "beta.wav", mimeType: "audio/wav", buffer: audio },
    },
  });
  expect(upload.status()).toBe(201);
  await owner.goto("/team");
  await owner.getByLabel("Work email").fill(employeeEmail);
  await owner.getByLabel("Role", { exact: true }).selectOption("EMPLOYEE");
  await owner.getByRole("button", { name: "Send invitation" }).click();
  await expect(owner.getByRole("status")).toContainText("no email was sent");
  await employee.goto(message(employeeEmail, "invite"));
  await employee.getByLabel("Your name").fill("USPack Employee");
  await employee.getByLabel("Choose password").fill(password);
  await employee
    .getByRole("button", { name: "Join organization", exact: true })
    .click();
  await expect(employee).toHaveURL(/\/$/);
  await employee.goto("/account");
  await expect(
    employee.getByText(/Your role does not allow call upload/),
  ).toBeVisible();
  await expect(
    employee.getByRole("button", { name: "Create organization", exact: true }),
  ).toHaveCount(0);
  const account = await (await employee.request.get("/api/account")).json();
  const ownerAccount = await (await owner.request.get("/api/account")).json();
  expect(account.organization_id).toBe(ownerAccount.organization_id);
  expect(account.email_verified).toBe(true);
  expect((await employee.request.get("/api/calls")).status()).toBe(403);

  expect(account.operational_access).toBe(true);
  await admin.goto(`/platform/users/${account.id}`);
  async function changeStatus(action: string) {
    await admin.getByRole("button", { name: action, exact: true }).click();
    await admin.getByLabel("Reason", { exact: true }).fill("Synthetic beta member status change");
    await admin.getByLabel("I confirm this administrative change.").check();
    await admin.getByRole("button", { name: "Confirm", exact: true }).click();
    await expect(admin.getByRole("dialog")).toHaveCount(0);
  }
  await changeStatus("Deactivate account");
  expect((await employee.request.get("/api/account")).status()).toBe(401);
  await employee.goto("/login");
  await employee.getByLabel("Work email").fill(employeeEmail);
  await employee.getByLabel("Password", { exact: true }).fill(password);
  await employee.getByRole("button", { name: "Sign in to Signal" }).click();
  await expect(employee.locator(".error[role=alert]")).toContainText("account is inactive");
  await changeStatus("Reactivate account");
  expect((await employee.request.get("/api/account")).status()).toBe(401);
  await employee.getByRole("button", { name: "Sign in to Signal" }).click();
  await expect(employee).toHaveURL(/\/$/);
  await employee.goto("/account");
  await expect(employee.getByText(/Your role does not allow call upload/)).toBeVisible();
  await admin.goto(`/platform/organizations/${orgId}`);
  // Use a real minute boundary: no clock injection or weakened server expiry check.
  const expires = Math.ceil((Date.now() + 15000) / 60000) * 60000;
  const localExpiry = new Date(expires - new Date(expires).getTimezoneOffset() * 60000)
    .toISOString().slice(0, 16);
  await admin.getByRole("button", { name: "Grant beta access", exact: true }).click();
  await admin.getByLabel("Expiration (your local time, optional)").fill(localExpiry);
  await admin.getByLabel("Reason", { exact: true }).fill("Verify actual beta expiration");
  await admin.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(admin.getByRole("dialog")).toHaveCount(0);
  await expect.poll(async () => (await (await owner.request.get("/api/account")).json()).operational_access,
    { timeout: 90000, intervals: [1000] }).toBe(false);
  expect((await (await employee.request.get("/api/account")).json()).operational_access).toBe(false);
  expect((await owner.request.post("/api/calls/missing/retry", {
    headers: { "X-Drive-Request": "1", Origin: "http://localhost:3001" },
  })).status()).toBe(403);
  await admin.reload();
  await expect(admin.getByText(/Access: Inactive/)).toBeVisible();
  // Renew through the same UI, then verify explicit revocation separately.
  await admin.getByRole("button", { name: "Grant beta access", exact: true }).click();
  await admin.getByLabel("Reason", { exact: true }).fill("Renew after expiration");
  await admin.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(admin.getByRole("dialog")).toHaveCount(0);
  expect((await (await owner.request.get("/api/account")).json()).operational_access).toBe(true);
  expect((await (await employee.request.get("/api/account")).json()).operational_access).toBe(true);
  await admin.getByRole("button", { name: "Revoke beta access", exact: true }).click();
  await admin.getByLabel("Reason", { exact: true }).fill("Synthetic beta ended");
  await admin.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(admin.getByRole("dialog")).toHaveCount(0);
  expect((await (await admin.request.get("/api/platform/activity")).json()).items.some(
    (event: { action: string; organization_id: string }) => event.action === "beta.revoke" && event.organization_id === orgId,
  )).toBe(true);
  expect((await (await employee.request.get("/api/account")).json()).operational_access).toBe(false);
  expect((await owner.request.get("/api/dashboard")).status()).toBe(200);
  expect(
    (
      await owner.request.post("/api/calls/missing/retry", {
        headers: { "X-Drive-Request": "1", Origin: "http://localhost:3001" },
      })
    ).status(),
  ).toBe(403);
  await owner.goto("/");
  await expect(
    owner.getByRole("heading", { name: "Dashboard", exact: true }),
  ).toBeVisible();
  await expect(
    owner
      .getByRole("button", { name: "Beta access required", exact: true })
      .first(),
  ).toBeDisabled();
  // A duplicate signup with correct credentials continues as sign-in, never a fake code dead end.
  await owner.goto("/register");
  await owner.getByLabel("Your name").fill("Ignored duplicate name");
  await owner.getByLabel("Business email").fill(ownerEmail);
  await owner.getByLabel("New password").fill(password);
  await owner
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(owner).toHaveURL(/\/$/);
  await owner.goto("/account");
  await expect(
    owner.getByRole("heading", { name: "Signal Access" }),
  ).toBeVisible();
  await ownerContext.close();
  await operatorContext.close();
  await employeeContext.close();
});
