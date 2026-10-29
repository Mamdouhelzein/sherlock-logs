import { describe, expect, it, vi } from "vitest";
import { fetchSystem, getApiOrigin } from "./api";
import { systemFixture } from "../test/fixture";

describe("API boundary", () => {
  it("accepts a valid response without sending browser credentials", async () => {
    const request = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => systemFixture });
    vi.stubGlobal("fetch", request);
    const check = await fetchSystem();
    expect(check.snapshot.integrations).toHaveLength(3);
    expect(request).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/system"),
      expect.objectContaining({ credentials: "omit", cache: "no-store" }),
    );
  });

  it("rejects responses from an incompatible service", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue({ ok: true, json: async () => ({ status: "ok" }) }),
    );
    await expect(fetchSystem()).rejects.toThrow("expected system contract");
  });

  it("rejects duplicate integration IDs rather than claiming complete coverage", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue({
          ok: true,
          json: async () => ({
            ...systemFixture,
            integrations: Array(3).fill(systemFixture.integrations[0]),
          }),
        }),
    );
    await expect(fetchSystem()).rejects.toThrow("expected system contract");
  });

  it("reports HTTP errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503 }),
    );
    await expect(fetchSystem()).rejects.toThrow("HTTP 503");
  });

  it.each([
    "javascript:alert(1)",
    "https://user:secret@example.com",
    "https://example.com/path",
  ])("rejects unsafe or ambiguous API origins: %s", (origin) => {
    expect(() => getApiOrigin(origin)).toThrow("Set VITE_API_BASE_URL");
  });
});
