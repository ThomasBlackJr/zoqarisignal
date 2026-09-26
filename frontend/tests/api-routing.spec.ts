import { expect, test } from "@playwright/test";

test("same-origin API proxy, page routes, and direct brand assets", async ({
  page,
  request,
}) => {
  const optimized: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/_next/image")
      optimized.push(request.url());
  });
  await page.goto("/login");
  for (const selector of [".signal-mark", ".signal-wordmark"]) {
    const image = page.locator(selector);
    await expect(image).toBeVisible();
    await expect(image).toHaveAttribute("src", /^\/brand\//);
    await expect
      .poll(() =>
        image.evaluate(
          (node: HTMLImageElement) => node.complete && node.naturalWidth > 0,
        ),
      )
      .toBe(true);
  }
  expect(optimized).toEqual([]);
  for (const asset of [
    "z-mark.png",
    "wordmark.png",
    "favicon.png",
    "apple-touch-icon.png",
  ]) {
    const response = await request.get(`/brand/${asset}`);
    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toContain("image/png");
  }
  for (const path of ["/api/account", "/api/preferences"]) {
    const response = await request.get(path);
    expect(response.status()).toBe(401);
    expect((await response.json()).detail).toContain("sign in");
  }
  expect((await request.get("/api/health")).status()).toBe(200);
  expect((await request.get("/api/auth/options")).status()).toBe(200);
  // /dashboard is not an implemented Next page; it must remain a frontend 404, not the backend dashboard API.
  for (const path of [
    "/",
    "/login",
    "/register",
    "/employees",
    "/rubrics",
    "/upload",
    "/team",
  ]) {
    const response = await request.get(path);
    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toContain("text/html");
  }
  const dashboard = await request.get("/dashboard");
  expect(dashboard.status()).toBe(404);
  expect(dashboard.headers()["content-type"]).toContain("text/html");
});
