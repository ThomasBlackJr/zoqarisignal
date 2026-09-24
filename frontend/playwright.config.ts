import { defineConfig } from "@playwright/test";
import { randomBytes } from "node:crypto";
import path from "node:path";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";

process.env.DRIVE_TEST_PASSWORD ??= randomBytes(24).toString("base64url");
process.env.DRIVE_E2E_MAIL_FOLDER ??= mkdtempSync(
  path.join(tmpdir(), "signal-test-mail-"),
);
const python = path.resolve(
  "..",
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
export default defineConfig({
  testDir: "./tests",
  timeout: 60000,
  workers: 1,
  use: {
    baseURL: "http://localhost:3001",
    browserName: "chromium",
    channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `"${python}" -m tests.e2e_server`,
      cwd: "../backend",
      url: "http://127.0.0.1:8001/health",
      reuseExistingServer: false,
      timeout: 30000,
    },
    {
      command: "npm run dev -- --port 3001",
      url: "http://localhost:3001/login",
      env: { BACKEND_URL: "http://127.0.0.1:8001", DRIVE_E2E: "1" },
      reuseExistingServer: false,
      timeout: 90000,
    },
  ],
});
