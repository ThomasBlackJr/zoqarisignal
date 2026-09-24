import { expect, test } from "@playwright/test";

function wav(seconds = 1) {
  const size = 16000 * seconds;
  const data = Buffer.alloc(size + 44);
  data.write("RIFF", 0);
  data.writeUInt32LE(size + 36, 4);
  data.write("WAVEfmt ", 8);
  data.writeUInt32LE(16, 16);
  data.writeUInt16LE(1, 20);
  data.writeUInt16LE(1, 22);
  data.writeUInt32LE(8000, 24);
  data.writeUInt32LE(16000, 28);
  data.writeUInt16LE(2, 32);
  data.writeUInt16LE(16, 34);
  data.write("data", 36);
  data.writeUInt32LE(size, 40);
  return data;
}

test("sign in, upload, process, play, review, find later, and log out on mobile", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/login");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/login-desktop.png",
    fullPage: true,
  });
  await page.getByLabel("Work email").fill("reviewer@example.test");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DRIVE_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Sign in to Signal" }).click();
  await expect(
    page.getByRole("heading", { name: "Dashboard", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Upload call", exact: true })
    .first()
    .click();
  await page.getByLabel("Choose audio recording").setInputFiles({
    name: "dispatch-review.wav",
    mimeType: "audio/wav",
    buffer: wav(),
  });
  await page
    .getByLabel("Scorecard", { exact: true })
    .selectOption({ index: 1 });
  await page.getByRole("button", { name: "Upload & process" }).click();
  await expect(
    page.getByRole("heading", { name: "dispatch-review.wav" }),
  ).toBeVisible();
  await expect(page.locator(".status.completed")).toBeVisible({
    timeout: 20000,
  });
  await expect(page.locator(".final-score strong")).toContainText("90");
  await expect(page.locator(".category-list details")).toHaveCount(6);
  await expect(page.locator(".transcript-body")).toContainText(
    "Thank you for calling Signal dispatch",
  );
  await expect(page.locator(".speaker-role.dispatcher").first()).toBeVisible();
  await expect(page.locator(".speaker-role.caller").first()).toBeVisible();
  await expect(page.locator(".transcript-disclosure")).toContainText(
    "tentative",
  );
  await page.getByRole("button", { name: "Raw segments", exact: true }).click();
  await expect(page.locator(".raw-segment")).toHaveCount(7);
  await page.getByRole("button", { name: "Conversation", exact: true }).click();
  await page.locator("audio").evaluate(async (element: HTMLAudioElement) => {
    await element.play();
    element.pause();
  });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/call-review-desktop.png",
    fullPage: true,
  });
  await page.reload();
  await expect(page.locator(".final-score strong")).toContainText("90");
  await page.getByRole("link", { name: "Back to calls" }).click();
  await page
    .getByRole("textbox", { name: "Search recordings" })
    .fill("not-found");
  await expect(page.getByText("No calls to show")).toBeVisible();
  await page
    .getByRole("textbox", { name: "Search recordings" })
    .fill("dispatch-review");
  await expect(
    page.getByRole("link", { name: /dispatch-review.wav/ }).first(),
  ).toBeVisible();
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(
    page
      .locator(".metric")
      .filter({ hasText: "Interactions analyzed" })
      .locator(".metric-value"),
  ).toHaveText("1");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/dashboard-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/dashboard-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page
    .getByRole("button", { name: "Log out", exact: true })
    .filter({ visible: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Welcome to Signal" }),
  ).toBeVisible();
  await page.goto("/calls");
  await expect(page).toHaveURL(/\/login$/);
  expect(errors).toEqual([]);
});

test("grouped speaker turns show ranges, seek audio, preserve raw view, and fit mobile", async ({
  page,
}) => {
  const headers = { "X-Drive-Request": "1", Origin: "http://localhost:3001" };
  await page.request.post("/api/auth/login", {
    headers,
    data: {
      email: "reviewer@example.test",
      password: process.env.DRIVE_TEST_PASSWORD!,
    },
  });
  const upload = await page.request.post("/api/calls", {
    headers,
    multipart: {
      file: {
        name: "speaker-turns.wav",
        mimeType: "audio/wav",
        buffer: wav(20),
      },
    },
  });
  const { id } = await upload.json();
  // UI fixture for provider-separated speakers. Backend grouping is tested
  // independently; production transcription stays in its honest demo mode.
  const texts = [
    "Thank you for calling.",
    " How can I help you?",
    " I'm the driver on route 42.",
  ];
  const source = texts.join("");
  const boundary = texts[0].length + texts[1].length;
  await page.route(`**/api/calls/${id}`, async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.transcript = {
      text: source,
      provider: "test-fixture",
      model: "speaker-ids-fixture",
      segments: [
        { text: texts[0], start: 0, end: 3, speaker: "A" },
        { text: texts[1], start: 4, end: 6.4, speaker: "A" },
        { text: texts[2], start: 7, end: 12, speaker: "B" },
      ],
      conversation: {
        version: "speaker-turns-v1",
        inference_method: "local-text-cues-v1",
        has_speaker_ids: true,
        alignment: "exact",
        turns: [
          {
            text: source.slice(0, boundary),
            start: 0,
            end: 6.4,
            speaker_id: "A",
            speaker_role: "DISPATCHER",
            role_source: "text_cue",
            confidence: null,
            source_start: 0,
            source_end: boundary,
            segment_indices: [0, 1],
          },
          {
            text: source.slice(boundary),
            start: 7,
            end: 12,
            speaker_id: "B",
            speaker_role: "CALLER",
            role_source: "text_cue",
            confidence: null,
            source_start: boundary,
            source_end: source.length,
            segment_indices: [2],
          },
        ],
      },
    };
    await route.fulfill({ response, json: body });
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`/calls/${id}`);
  await expect(page.locator(".conversation-turn")).toHaveCount(2);
  await expect(
    page.getByRole("button", { name: "Play from 00:00", exact: true }),
  ).toHaveText("00:00 – 00:06");
  await expect(
    page.getByRole("button", { name: "Play from 00:07", exact: true }),
  ).toHaveText("00:07 – 00:12");
  expect(await page.locator(".turn-text").allTextContents()).toEqual([
    source.slice(0, boundary),
    source.slice(boundary),
  ]);
  await expect
    .poll(() =>
      page
        .locator("audio")
        .evaluate((audio: HTMLAudioElement) => audio.readyState),
    )
    .toBeGreaterThan(0);
  await page
    .getByRole("button", { name: "Play from 00:07", exact: true })
    .click();
  await expect
    .poll(() =>
      page
        .locator("audio")
        .evaluate((audio: HTMLAudioElement) => audio.currentTime),
    )
    .toBeGreaterThanOrEqual(7);
  await page
    .locator("audio")
    .evaluate((audio: HTMLAudioElement) => audio.pause());
  await page
    .locator(".transcript-panel")
    .screenshot({ path: "test-results/speaker-turns-desktop.png" });
  await page.getByRole("button", { name: "Raw segments", exact: true }).click();
  await expect(page.locator(".raw-segment")).toHaveCount(3);
  await expect(page.locator(".raw-segment").last()).toContainText(texts[2]);
  await page.getByRole("button", { name: "Conversation", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .locator(".transcript-panel")
    .screenshot({ path: "test-results/speaker-turns-mobile.png" });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});

test("supervisor controls and versioned scorecards", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const headers = { "X-Drive-Request": "1", Origin: "http://localhost:3001" };
  await page.request.post("/api/auth/login", {
    headers,
    data: {
      email: "reviewer@example.test",
      password: process.env.DRIVE_TEST_PASSWORD!,
    },
  });
  const response = await page.request.post("/api/calls", {
    headers,
    multipart: {
      file: {
        name: "supervisor-review.wav",
        mimeType: "audio/wav",
        buffer: wav(),
      },
    },
  });
  const { id } = await response.json();
  await page.goto(`/calls/${id}`);
  await expect(page.locator(".status.completed")).toBeVisible({
    timeout: 20000,
  });
  const original = await page.locator(".turn-text").allTextContents();
  await page
    .getByLabel(/Speaker role for turn/)
    .first()
    .selectOption("CALLER");
  await expect(page.getByRole("dialog")).toContainText("1 conversational turn");
  await page.getByRole("button", { name: "Apply correction" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.getByLabel(/Speaker role for turn/).first()).toHaveValue(
    "CALLER",
  );
  expect(await page.locator(".turn-text").allTextContents()).toEqual(original);
  await page
    .getByRole("button", { name: "Adjust Professionalism", exact: true })
    .click();
  await page.getByLabel("Supervisor score").fill("20");
  await page
    .getByLabel("Reason for adjustment")
    .fill("Verified the original recording.");
  await page.getByRole("button", { name: "Save adjustment" }).click();
  await expect(page.locator(".final-score strong")).toContainText("92");
  await expect(page.locator(".ai-score strong")).toContainText("90");
  await page.reload();
  await expect(page.locator(".final-score strong")).toContainText("92");
  await expect(page.getByLabel(/Speaker role for turn/).first()).toHaveValue(
    "CALLER",
  );
  await page
    .getByRole("button", { name: "Adjust Professionalism", exact: true })
    .click();
  await page
    .getByLabel("Reason for adjustment")
    .fill("Return to the original evaluation.");
  await page.getByRole("button", { name: "Reset to AI score" }).click();
  await expect(page.locator(".final-score strong")).toContainText("90");
  await page
    .getByRole("button", { name: "Complete review", exact: true })
    .click();
  await expect(page.locator(".review-badge")).toHaveText("Reviewed");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/signal-review-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/signal-review-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("link", { name: "Scorecards", exact: true }).click();
  await page.getByRole("button", { name: /Dispatch QA.*Version 1.0/ }).click();
  await page.getByRole("button", { name: "Duplicate as draft" }).click();
  await page.getByLabel("Scorecard name").fill("Signal service standard");
  await page.getByLabel("Weight / points").nth(1).fill("5");
  await expect(page.locator(".weight-total")).toContainText("85 / 100");
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(
    page.getByRole("button", { name: "Publish scorecard" }),
  ).toBeDisabled();
  await page.getByLabel("Weight / points").nth(1).fill("20");
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(
    page.getByRole("button", { name: "Publish scorecard" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Publish scorecard" }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "Existing evaluations and scores remain unchanged",
  );
  await page.getByRole("button", { name: "Confirm publication" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.locator(".rubric-editor .rubric-status")).toHaveText(
    "PUBLISHED",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/signal-scorecards.png",
    fullPage: true,
  });
  await page.goto(`/calls/${id}`);
  await expect(page.locator(".qa-panel .panel-heading")).toContainText(
    "Version 1.0",
  );
  await page.getByRole("button", { name: "New QA evaluation" }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "Signal service standard",
  );
  await page.getByRole("button", { name: "Start new evaluation" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.locator(".status.completed")).toBeVisible({
    timeout: 20000,
  });
  await expect(page.locator(".qa-panel .panel-heading")).toContainText(
    "Version 2.0",
  );
  await page.getByRole("button", { name: "Evaluation history" }).click();
  await expect(page.locator(".history-evaluation")).toHaveCount(2);
  await page.getByRole("button", { name: "Close dialog" }).click();
  expect(errors).toEqual([]);
});
