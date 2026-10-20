import { expect, test } from "@playwright/test";

test("billing is Owner-only and inactive members receive plain access guidance", async ({
  page,
}) => {
  let role = "EMPLOYEE";
  let organization: string | null = "fixture-org";
  await page.route("**/api/account", (route) =>
    route.fulfill({
      json: {
        id: "fixture-user",
        email: "fixture@example.test",
        name: "Beta member",
        role,
        organization_id: organization,
        organization_name: organization ? "Beta workspace" : null,
        email_verified: true,
        operational_access: false,
        can_review: role !== "EMPLOYEE",
        suspended: false,
        access_message: organization
          ? "Your organization's access is currently inactive. Please contact your organization owner."
          : null,
        subscription_status: "inactive",
        entitlement_source: null,
        entitlement_expires_at: null,
        dev_activation_available: false,
        mail_delivery: "smtp",
        checkout_available: false,
        onboarding_completed: false,
      },
    }),
  );
  await page.route("**/api/billing", (route) =>
    route.fulfill({ json: { configured: false } }),
  );
  for (const memberRole of ["ADMIN", "MANAGER", "REVIEWER", "EMPLOYEE"]) {
    role = memberRole;
    await page.goto("/account");
    await expect(
      page.getByText(
        "Your organization's access is currently inactive. Please contact your organization owner.",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Subscription billing" }),
    ).toHaveCount(0);
    await expect(
      page.getByText(
        "Contact your organization Owner or Admin to manage billing.",
      ),
    ).toHaveCount(0);
  }
  role = "OWNER";
  await page.goto("/account");
  await expect(
    page.getByRole("region", { name: "Subscription billing" }),
  ).toBeVisible();
  organization = null;
  role = "EMPLOYEE";
  await page.goto("/account");
  await expect(
    page.getByText(
      /You can keep your account without creating an organization/,
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Subscription billing" }),
  ).toHaveCount(0);
});
