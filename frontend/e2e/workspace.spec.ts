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

test("searches workspace navigation and restores focus on dismissal", async ({
  page,
}) => {
  await page.goto("/");
  const trigger = page.getByRole("button", { name: "Open navigation search" });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Jump to a page" });
  await expect(dialog).toBeVisible();
  await page.getByRole("textbox", { name: "Search pages" }).fill("setup");
  await page.getByRole("textbox", { name: "Search pages" }).press("Enter");
  await expect(
    page.getByRole("heading", { name: "Start the investigation." }),
  ).toBeVisible();
  await expect(dialog).not.toBeVisible();
  await trigger.click();
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
});

test("supports keyboard search and reduced decorative motion", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Ambient effects" }),
  ).toHaveAttribute("aria-pressed", "false");
  await page.keyboard.press("Control+k");
  await expect(
    page.getByRole("dialog", { name: "Jump to a page" }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Search pages" })
    .fill("nothing matches");
  await expect(page.getByRole("status")).toContainText("No matching pages");
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Open navigation search" }),
  ).toBeVisible();
});
