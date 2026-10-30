import { expect, test, type Page } from "@playwright/test";

// Exercise the real Supabase JS client with mocked provider HTTP responses.
// These tests do not claim to verify a provisioned hosted Supabase project.
test.use({ baseURL: "http://127.0.0.1:5174" });
const id = "00000000-0000-4000-8000-000000000001";
const user = {
  id,
  aud: "authenticated",
  role: "authenticated",
  email: "detective@example.test",
  email_confirmed_at: "2026-10-30T00:00:00Z",
  app_metadata: {},
  user_metadata: {},
  identities: [],
  created_at: "2026-10-30T00:00:00Z",
};
const jwt = `${Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url")}.${Buffer.from(JSON.stringify({ sub: id, aud: "authenticated", exp: Math.floor(Date.now() / 1000) + 3600 })).toString("base64url")}.test-signature`;
const session = {
  access_token: jwt,
  token_type: "bearer",
  expires_in: 3600,
  refresh_token: "test-refresh-token",
  user,
};

async function mockProvider(page: Page, role: "member" | "admin" = "member") {
  let name = "Detective";
  await page.route("https://sherlock-test.supabase.co/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (path.endsWith("/token")) {
      const body = request.postDataJSON();
      if (body.password === "wrong-password")
        return route.fulfill({
          status: 400,
          json: {
            code: "invalid_credentials",
            msg: "Invalid login credentials",
          },
        });
      return route.fulfill({ json: session });
    }
    if (path.endsWith("/signup")) return route.fulfill({ json: user });
    if (path.endsWith("/recover")) return route.fulfill({ json: {} });
    if (path.endsWith("/logout")) return route.fulfill({ status: 204 });
    if (path.endsWith("/user")) return route.fulfill({ json: user });
    if (path.endsWith("/profiles")) {
      if (request.method() === "PATCH")
        name = request.postDataJSON().display_name;
      return route.fulfill({ json: { display_name: name } });
    }
    throw new Error(`Unexpected mocked Supabase request: ${path}`);
  });
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({ json: { id, email: user.email, role } }),
  );
  await page.route("**/api/v1/admin/status", (route) =>
    role === "admin"
      ? route.fulfill({
          json: { status: "authorized", scope: "administrator", user_id: id },
        })
      : route.fulfill({
          status: 403,
          json: { detail: "Administrator access is required." },
        }),
  );
}

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email address").fill(user.email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("long-test-passphrase");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Identity, verified." }),
  ).toBeVisible();
}

test("protects deep links, signs in, persists, saves a private profile, and signs out", async ({
  page,
}) => {
  await mockProvider(page);
  await page.goto("/account");
  await expect(page).toHaveURL(/\/login$/);
  await login(page);
  await page.getByLabel("Display name").fill("Sherlock Jr.");
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByText("Profile saved.")).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Identity, verified." }),
  ).toBeVisible();
  await page.goto("/admin");
  await expect(
    page.getByRole("heading", { name: "Administrator access required." }),
  ).toBeVisible();
  await page.goto("/account");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/account");
  await expect(page).toHaveURL(/\/login$/);
});

test("handles invalid credentials and checks admin access against the API", async ({
  page,
}) => {
  await mockProvider(page, "admin");
  await page.goto("/login");
  await page.getByLabel("Email address").fill(user.email);
  await page.getByLabel("Password", { exact: true }).fill("wrong-password");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute(
    "type",
    "text",
  );
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Sign-in failed");
  await page
    .getByLabel("Password", { exact: true })
    .fill("long-test-passphrase");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("link", { name: /Check administrator access/ }).click();
  await expect(
    page.getByRole("heading", { name: "Administrator access confirmed." }),
  ).toBeVisible();
  await page.route("**/api/v1/admin/status", (route) =>
    route.fulfill({ status: 403, json: {} }),
  );
  await page.reload();
  await expect(page.getByRole("alert")).toContainText(
    "Administrator access is required",
  );
});

test("registers, confirms a PKCE link, and rejects an expired callback", async ({
  page,
}) => {
  await mockProvider(page);
  await page.goto("/register");
  await page.getByLabel("Display name").fill("Detective");
  await page.getByLabel("Email address").fill(user.email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("long-test-passphrase");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(page.getByText(/Check your inbox/)).toBeVisible();
  await page.goto("/auth/callback?code=confirmation-fixture");
  await expect(
    page.getByRole("heading", { name: "Identity, verified." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.route("**/auth/v1/token**", (route) =>
    route.fulfill({
      status: 400,
      json: { error: "invalid_grant", error_description: "expired" },
    }),
  );
  await page.goto("/auth/callback?code=expired-fixture");
  await expect(
    page.getByRole("heading", { name: "This link needs another look." }),
  ).toBeVisible();
});

test("requests recovery and updates the password after a PKCE recovery link", async ({
  page,
}) => {
  await mockProvider(page);
  await page.goto("/forgot-password");
  await page.getByLabel("Email address").fill(user.email);
  await page.getByRole("button", { name: "Send recovery link" }).click();
  await expect(page.getByText(/If an account exists/)).toBeVisible();
  await page.goto("/reset-password?code=recovery-fixture");
  await page
    .getByLabel("Password", { exact: true })
    .fill("replacement-passphrase");
  const update = page.waitForRequest(
    (request) =>
      request.url().endsWith("/auth/v1/user") && request.method() === "PUT",
  );
  await page.getByRole("button", { name: "Update password" }).click();
  expect((await update).postDataJSON().password).toBe("replacement-passphrase");
  await expect(page.getByText(/Password updated/)).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
