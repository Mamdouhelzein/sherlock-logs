import { expect, it, vi } from "vitest";
import { investigationRequest, statusSchema } from "./api";

it("rejects malformed worker status instead of inventing readiness", () => {
  expect(
    statusSchema.safeParse({
      mode: "shadow",
      worker_ready: true,
      queue: {},
      scored: 0,
      flagged: 0,
    }).success,
  ).toBe(false);
});
it("keeps raw storage error bodies out of the UI", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({ detail: "private-connection-secret" }),
      }),
  );
  await expect(
    investigationRequest("/detection/status", "fixture-token", statusSchema),
  ).rejects.toThrow("Investigation storage is unavailable");
});
it("sends the bearer only in headers with cache disabled", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: false, status: 403 });
  vi.stubGlobal("fetch", fetch);
  await expect(
    investigationRequest("/detection/status", "fixture-token", statusSchema),
  ).rejects.toThrow("Administrator access is required");
  const [url, options] = fetch.mock.calls[0];
  expect(url).not.toContain("fixture-token");
  expect(options.headers.Authorization).toBe("Bearer fixture-token");
  expect(options.cache).toBe("no-store");
  expect(options.credentials).toBe("omit");
});
