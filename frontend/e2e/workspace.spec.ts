import { expect, test } from "@playwright/test";

test("connects to the real API and supports direct navigation", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("API reachable", { exact: true })).toBeVisible();
  await expect(page.getByText("Not trained", { exact: true })).toBeVisible();
  await page
    .getByRole("link", { name: "System architecture", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Follow the signal." }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Follow the signal." }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("explains connection failures and recovers on retry", async ({ page }) => {
  await page.route("**/api/v1/system", (route) => route.abort());
  await page.goto("/");
  await expect(
    page.getByText("API unavailable", { exact: true }),
  ).toBeVisible();
  await page.unroute("**/api/v1/system");
  await page.getByRole("button", { name: "Check again" }).click();
  await expect(page.getByText("API reachable", { exact: true })).toBeVisible();
});
