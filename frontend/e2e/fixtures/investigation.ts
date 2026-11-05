import { expect, type Page } from "@playwright/test";

export const viewer = "00000000-0000-4000-8000-000000000001";
export const account = "00000000-0000-4000-8000-000000000002";
export const incidentId = "00000000-0000-4000-8000-000000000201";
export const events = [
  {
    id: "00000000-0000-4000-8000-000000000101",
    occurred_at: "2026-11-04T15:00:00Z",
    outcome: "failure",
    flagged: true,
    ml_score: 0.8,
    rule_score: 1.5,
    signals: ["ml_outlier", "account_failure_burst"],
  },
  {
    id: "00000000-0000-4000-8000-000000000102",
    occurred_at: "2026-11-04T14:59:00Z",
    outcome: "success",
    flagged: false,
    ml_score: 0.4,
    rule_score: 0,
    signals: [],
  },
  {
    id: "00000000-0000-4000-8000-000000000103",
    occurred_at: "2026-11-04T14:58:00Z",
    outcome: "success",
    flagged: null,
    ml_score: null,
    rule_score: null,
    signals: null,
  },
].map((e) => ({
  ...e,
  received_at: e.occurred_at,
  source: "trusted_auth_adapter",
  user_id: account,
  account_key: null,
  source_ip: "192.0.2.25",
  user_agent: "Synthetic test browser",
  job_state: e.flagged === null ? "pending" : "processed",
  attempts: e.flagged === null ? 0 : 1,
  last_error: null,
  context_warnings: ["limited_account_history"],
  model_version_id: e.flagged === null ? null : "a".repeat(64),
  artifact_label: e.flagged === null ? null : "Synthetic test model",
}));
export async function investigationFixture(
  page: Page,
  {
    role = "admin",
    empty = false,
  }: { role?: "member" | "admin"; empty?: boolean } = {},
) {
  const state = {
    revoked: false,
    unavailable: false,
    workerReady: true,
    failureCoverage: "not_connected" as
      | "not_connected"
      | "provider_logs_recent_window"
      | "provider_logs_unhealthy",
    collectionStale: false,
    cleanupStale: false,
    cleanupEnabled: true,
    requests: [] as string[],
  };
  const user = {
    id: viewer,
    aud: "authenticated",
    role: "authenticated",
    email: "detective@example.test",
    email_confirmed_at: "2026-11-01T00:00:00Z",
    app_metadata: {},
    user_metadata: {},
    identities: [],
    created_at: "2026-11-01T00:00:00Z",
  };
  const jwt = `${Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url")}.${Buffer.from(JSON.stringify({ sub: viewer, aud: "authenticated", exp: Math.floor(Date.now() / 1000) + 3600 })).toString("base64url")}.test-signature`;
  await page.route("https://sherlock-test.supabase.co/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/token"))
      return route.fulfill({
        json: {
          access_token: jwt,
          token_type: "bearer",
          expires_in: 3600,
          refresh_token: "fixture-refresh",
          user,
        },
      });
    if (path.endsWith("/user")) return route.fulfill({ json: user });
    if (path.endsWith("/profiles"))
      return route.fulfill({ json: { display_name: "Detective" } });
    if (path.endsWith("/logout")) return route.fulfill({ status: 204 });
    return route.abort();
  });
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({ json: { id: viewer, email: user.email, role } }),
  );
  await page.route("**/api/v1/admin/**", (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace("/api/v1/admin", "");
    if (path === "/status")
      return route.fulfill({
        json: { status: "authorized", scope: "administrator", user_id: viewer },
      });
    state.requests.push(path + url.search);
    expect(route.request().headers().authorization).toBe(`Bearer ${jwt}`);
    if (state.revoked)
      return route.fulfill({
        status: 403,
        json: { detail: "Administrator access is required." },
      });
    if (state.unavailable)
      return route.fulfill({
        status: 503,
        json: { detail: "private database error must never be reflected" },
      });
    if (path === "/detection/status")
      return route.fulfill({
        json: {
          mode: "shadow",
          worker_ready: state.workerReady,
          worker_fresh: state.workerReady,
          worker: {
            status: state.workerReady ? "ready" : "model_unavailable",
            last_seen: new Date().toISOString(),
            model_version_id: "a".repeat(64),
            artifact_label: "Synthetic test model",
          },
          queue: { processed: empty ? 0 : 2, pending: empty ? 0 : 1 },
          scored: empty ? 0 : 2,
          flagged: empty ? 0 : 1,
          failed_login_coverage: "not_connected",
        },
      });
    if (path === "/telemetry/status") {
      const recent = new Date().toISOString();
      const old = new Date(Date.now() - 3 * 3600_000).toISOString();
      return route.fulfill({
        json: {
          collection: {
            status: "ready",
            healthy: !state.collectionStale,
            lease_fresh: null,
            last_success_at: state.collectionStale ? old : recent,
            last_full_scan_at: recent,
            next_run_at: recent,
            interval_seconds: 30,
            scan_full: false,
            full_scan_overdue: false,
            counts: { scanned: 1, inserted: 0, duplicates: 1, rejected: 0 },
            error_code: null,
          },
          retention: {
            enabled: state.cleanupEnabled,
            keep_days: 30,
            status: "ready",
            healthy: state.cleanupEnabled && !state.cleanupStale,
            last_success_at: state.cleanupStale ? old : recent,
            deleted: 0,
            backlog: false,
            error_code: null,
          },
          failed_login_coverage: state.failureCoverage,
          failure_source: {
            coverage: state.failureCoverage,
            status:
              state.failureCoverage === "not_connected"
                ? "not_configured"
                : "ready",
            healthy: state.failureCoverage === "provider_logs_recent_window",
            last_success_at:
              state.failureCoverage === "not_connected" ? null : recent,
            scanned: 2,
          },
          retention_schedule: "hourly",
        },
      });
    }
    if (path === "/investigation/events") {
      let rows = empty ? [] : events;
      if (url.searchParams.has("user_id"))
        rows = rows.filter(
          (e) => e.user_id === url.searchParams.get("user_id"),
        );
      if (url.searchParams.has("outcome"))
        rows = rows.filter(
          (e) => e.outcome === url.searchParams.get("outcome"),
        );
      if (url.searchParams.has("flagged"))
        rows = rows.filter((e) => e.flagged === true);
      const cursor = url.searchParams.get("cursor");
      return route.fulfill({
        json: {
          items: cursor ? rows.slice(2) : rows.slice(0, 2),
          next_cursor: !cursor && rows.length > 2 ? "older-fixture-page" : null,
          mode: "shadow",
        },
      });
    }
    if (path === "/incidents")
      return route.fulfill({
        json: {
          items: empty
            ? []
            : [
                {
                  id: incidentId,
                  model_version_id: "a".repeat(64),
                  artifact_label: "Synthetic test model",
                  entity_type: "account",
                  first_seen: events[0].occurred_at,
                  last_seen: events[0].occurred_at,
                  window_start: events[0].occurred_at,
                  event_count: 1,
                },
              ],
          next_cursor: null,
          mode: "shadow",
        },
      });
    if (path === `/incidents/${incidentId}`)
      return route.fulfill({
        json: { items: [events[0]], next_cursor: null, mode: "shadow" },
      });
    const event = events.find((e) => path === `/events/${e.id}/detection`);
    if (event)
      return route.fulfill({
        json: {
          ...event,
          mode: event.flagged === null ? null : "shadow",
          features:
            event.flagged === null
              ? null
              : { account_failures_15m: 12, account_successes_30d: 3 },
          feature_version: event.flagged === null ? null : "login-history-v1",
          ml_threshold: event.flagged === null ? null : 0.59,
          rule_threshold: event.flagged === null ? null : 0.6,
          history_as_of: event.flagged === null ? null : event.occurred_at,
          scored_at: event.flagged === null ? null : event.occurred_at,
        },
      });
    return route.fulfill({ status: 404, json: { detail: "Not found" } });
  });
  return state;
}
export async function investigationLogin(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email address").fill("detective@example.test");
  await page.getByLabel("Password", { exact: true }).fill("fixture-passphrase");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Identity, verified." }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Investigations", exact: true }).click();
}
