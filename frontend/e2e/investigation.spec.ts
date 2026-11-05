import { expect, test } from "@playwright/test";
import {
  account,
  events,
  incidentId,
  investigationFixture,
  investigationLogin,
} from "./fixtures/investigation";

test.use({ baseURL: "http://127.0.0.1:5174" });

test("investigates model evidence, server-filtered account history, older pages and incident timeline", async ({
  page,
}, info) => {
  const state = await investigationFixture(page);
  await investigationLogin(page);
  await expect(
    page.getByRole("heading", { name: "Investigation desk." }),
  ).toBeVisible();
  await expect(
    page.getByText("Ready at last check", { exact: true }),
  ).toBeVisible();
  const evidence = page.getByRole("region", {
    name: "Selected event evidence",
  });
  await expect(
    evidence.getByText("Isolation Forest", { exact: true }),
  ).toBeVisible();
  await expect(
    evidence.getByText("Repeated failures", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(/Failed-login collection is not connected/),
  ).toBeVisible();
  await evidence.getByText("Feature snapshot (2)", { exact: true }).click();
  await expect(
    evidence.getByText("Account failures, prior 15 min", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Load older records", exact: true })
    .click();
  await page
    .getByRole("button", { name: /Sign-in succeeded.*Awaiting score/ })
    .click();
  await expect(
    evidence.getByText(/This event has not been scored yet/),
  ).toBeVisible();
  await page.getByRole("button", { name: /Sign-in failed.*Flagged/ }).click();
  await page.getByRole("button", { name: "View account history" }).click();
  await expect(page).toHaveURL(new RegExp(`account=${account}`));
  await expect
    .poll(() =>
      state.requests.some((url) => url.includes(`user_id=${account}`)),
    )
    .toBe(true);
  await page.getByRole("button", { name: "Incidents", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Incident timeline" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Account activity cluster/ }),
  ).toBeVisible();
  await expect(
    evidence.getByText("Repeated failures", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Incident timeline" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `test-results/investigation-${info.project.name}.png`,
    fullPage: true,
  });
  await page.goto(
    `/investigations?view=incidents&incident=${incidentId}&event=${events[0].id}`,
  );
  await expect(
    evidence.getByText("Repeated failures", { exact: true }),
  ).toBeVisible();
});

test("shows honest empty, unavailable and revoked states without retaining private evidence", async ({
  page,
}) => {
  const state = await investigationFixture(page, { empty: true });
  await investigationLogin(page);
  await expect(
    page.getByRole("heading", { name: "No events in this view." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Incidents", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "No grouped alerts yet." }),
  ).toBeVisible();
  state.workerReady = false;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(
    page.getByText("Model unavailable", { exact: true }),
  ).toBeVisible();
  state.unavailable = true;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByRole("alert").first()).toContainText(
    "Investigation storage is unavailable",
  );
  await expect(page.getByText(/private database error/)).not.toBeVisible();
  state.unavailable = false;
  state.revoked = true;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByRole("alert").first()).toContainText(
    "Administrator access is required",
  );
  await expect(
    page.getByRole("heading", { name: "Investigation desk." }),
  ).not.toBeVisible();
});

test("denies member access before fetching investigation records", async ({
  page,
}) => {
  const state = await investigationFixture(page, { role: "member" });
  await investigationLogin(page);
  await expect(
    page.getByRole("heading", { name: "Administrator access required." }),
  ).toBeVisible();
  expect(state.requests).toHaveLength(0);
  await expect(
    page.getByRole("heading", { name: "Investigation desk." }),
  ).not.toBeVisible();
});

test("removes previously visible evidence after authorization is revoked", async ({
  page,
}) => {
  const state = await investigationFixture(page);
  await investigationLogin(page);
  await expect(
    page
      .getByRole("region", { name: "Selected event evidence" })
      .getByText("192.0.2.25", { exact: true }),
  ).toBeVisible();
  state.revoked = true;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Administrator access is required",
  );
  await expect(page.getByText("192.0.2.25", { exact: true })).not.toBeVisible();
});

test("keeps collection and cleanup health separate from model readiness", async ({
  page,
}) => {
  const state = await investigationFixture(page);
  await investigationLogin(page);
  const operations = page.getByRole("region", {
    name: "Collection and retention",
  });
  await expect(
    operations.getByText("Automatic collection healthy", { exact: true }),
  ).toBeVisible();
  await expect(
    operations.getByText("Cleanup healthy", { exact: true }),
  ).toBeVisible();
  state.collectionStale = true;
  state.cleanupStale = true;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(
    operations.getByText("Collector overdue", { exact: true }),
  ).toBeVisible();
  await expect(
    operations.getByText("Cleanup overdue", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Ready at last check", { exact: true }),
  ).toBeVisible();
  state.cleanupEnabled = false;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(
    operations.getByText("Cleanup not enabled", { exact: true }),
  ).toBeVisible();
});

test("distinguishes provider-confirmed recent-hour failure coverage from missing or stale collection", async ({
  page,
}) => {
  const state = await investigationFixture(page);
  await investigationLogin(page);
  await expect(
    page.getByText("Failed-login collection is not connected.", {
      exact: false,
    }),
  ).toBeVisible();
  state.failureCoverage = "provider_logs_recent_window";
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(
    page.getByText(
      /Provider-confirmed password failures are collected from the recent hour/,
    ),
  ).toBeVisible();
  await page
    .getByText("Collection and cleanup details", { exact: true })
    .click();
  await expect(
    page.getByText("Provider Auth logs · recent hour", { exact: true }),
  ).toBeVisible();
  state.failureCoverage = "provider_logs_unhealthy";
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(
    page.getByText(/Failed-login collection is overdue or incomplete/),
  ).toBeVisible();
  await expect(
    page.getByText("Ready at last check", { exact: true }),
  ).toBeVisible();
});
