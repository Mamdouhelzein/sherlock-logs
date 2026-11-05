import { randomUUID } from "node:crypto";
import { expect, test, type APIRequestContext } from "@playwright/test";

async function emailLink(
  request: APIRequestContext,
  email: string,
  subject: RegExp,
) {
  let messageId = "";
  await expect
    .poll(async () => {
      const response = await request.get(
        "http://127.0.0.1:54324/api/v1/search",
        {
          params: { query: `to:${email}` },
        },
      );
      const data = await response.json();
      messageId =
        data.messages?.find((message: { ID: string; Subject: string }) =>
          subject.test(message.Subject),
        )?.ID ?? "";
      return messageId;
    })
    .not.toBe("");
  const response = await request.get(
    `http://127.0.0.1:54324/api/v1/message/${messageId}`,
  );
  const message = await response.json();
  const link = String(message.HTML)
    .match(/href="([^"]+)"/)?.[1]
    ?.replaceAll("&amp;", "&");
  expect(link).toBeTruthy();
  const url = new URL(link!);
  expect(url.origin).toBe("http://127.0.0.1:54421");
  expect(url.pathname).toBe("/auth/v1/verify");
  return link!;
}

test("confirms a new account, enforces cooldown, and recovers through real PKCE", async ({
  page,
  request,
}) => {
  const email = `browser-${randomUUID()}@example.test`;
  const password = `local-test-${randomUUID()}`;
  await page.goto("/register");
  await page.getByLabel("Display name").fill("Local Detective");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(page.getByText(/Registration request received/)).toBeVisible();
  await page.goto(await emailLink(request, email, /confirm/i));
  await expect(page).toHaveURL(/\/account$/);
  await expect(
    page.getByRole("heading", { name: "Identity, verified." }),
  ).toBeVisible();
  await expect(page.getByLabel("Display name")).toHaveValue("Local Detective");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("deliberately-wrong-fixture");
  for (let attempt = 0; attempt < 5; attempt++) {
    const response = page.waitForResponse((response) =>
      response.url().includes("/auth/v1/token?grant_type=password"),
    );
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    expect((await response).status()).toBe(400);
    await expect(page.getByRole("alert")).toContainText("Sign-in failed");
    await expect(
      page.getByRole("button", { name: "Sign in", exact: true }),
    ).toBeEnabled();
  }
  await page.getByLabel("Password", { exact: true }).fill(password);
  const blocked = page.waitForResponse((response) =>
    response.url().includes("/auth/v1/token?grant_type=password"),
  );
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  expect((await blocked).status()).toBe(400);
  await expect(page.getByRole("alert")).toContainText("Sign-in failed");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByRole("link", { name: "Forgot password?" }).click();
  await page.getByLabel("Email address").fill(email);
  const recoveryResponse = page.waitForResponse((response) =>
    response.url().includes("/auth/v1/recover"),
  );
  await page
    .getByRole("button", { name: "Send recovery link", exact: true })
    .click();
  const recovery = await recoveryResponse;
  const recoveryBody = await recovery.json();
  expect(
    recovery.status(),
    `Recovery code: ${recoveryBody.code ?? "none"}`,
  ).toBe(200);
  await expect(page.getByText(/If an account exists/)).toBeVisible();
  await page.goto(await emailLink(request, email, /reset|recover/i));
  await expect(page).toHaveURL(/\/reset-password/);
  await page
    .getByLabel("Password", { exact: true })
    .fill(`recovered-test-${randomUUID()}`);
  await page
    .getByRole("button", { name: "Update password", exact: true })
    .click();
  await expect(
    page.getByText("Password updated. You can return to your account."),
  ).toBeVisible();
  await page.getByRole("link", { name: "Go to your account" }).click();
  await expect(
    page.getByRole("heading", { name: "Identity, verified." }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
