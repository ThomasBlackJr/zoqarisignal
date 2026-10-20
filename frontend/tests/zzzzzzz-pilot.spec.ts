import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

test("trusted pilot grant opens the existing workspace without billing and revoke blocks it", async ({
  page,
}) => {
  const sessionPath = path.join(
    process.env.DRIVE_E2E_MAIL_FOLDER!,
    "controls-session.json",
  );
  if (existsSync(sessionPath)) {
    await page
      .context()
      .addCookies(JSON.parse(readFileSync(sessionPath, "utf8")).cookies);
  } else {
    const login = await page.request.post("/api/auth/login", {
      headers: { "X-Drive-Request": "1", Origin: "http://localhost:3001" },
      data: {
        email: "reviewer@example.test",
        password: process.env.DRIVE_TEST_PASSWORD!,
      },
    });
    expect(login.status()).toBe(200);
  }
  const database = path
    .join(process.env.DRIVE_E2E_DB_FOLDER!, "drive.db")
    .replaceAll("\\", "/");
  const python = process.env.SIGNAL_TEST_PYTHON || path.resolve(
    "..",
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );
  const operate = (action: "grant" | "revoke", expires?: string) => {
    execFileSync(
      python,
      [
        "-m",
        "app.pilot_cli",
        action,
        "--organization-id",
        "00000000-0000-0000-0000-000000000002",
        "--confirm-name",
        "Signal workspace",
        "--actor-email",
        "reviewer@example.test",
        "--reason",
        "Synthetic isolated browser pilot test",
        ...(expires ? ["--expires-at", expires] : []),
      ],
      {
        cwd: path.resolve("..", "backend"),
        env: {
          ...process.env,
          DATABASE_URL: `sqlite:///${database}`,
          ENVIRONMENT: "development",
          VERCEL: "0",
        },
        timeout: 15000,
      },
    );
  };
  operate("grant", new Date(Date.now() + 3600000).toISOString());
  await page.goto("/account");
  await expect(
    page.getByText(/Your organization has Beta Access/),
  ).toBeVisible();
  await expect(page.getByText(/Your account remains active/)).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Subscription billing" }),
  ).toHaveCount(0);
  expect((await page.request.get("/api/calls")).status()).toBe(200);
  operate("grant");
  await page.reload();
  await expect(page.getByText(/Expiration: Never/)).toBeVisible();
  operate("revoke");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Signal Access" }),
  ).toBeVisible();
  expect((await page.request.get("/api/dashboard")).status()).toBe(200);
  expect(
    (
      await page.request.post("/api/calls/missing/retry", {
        headers: { "X-Drive-Request": "1", Origin: "http://localhost:3001" },
      })
    ).status(),
  ).toBe(403);
  await expect(page.getByText(/access is currently inactive/)).toBeVisible();
});
