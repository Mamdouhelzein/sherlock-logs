import { z } from "zod";

const systemSchema = z.object({
  service: z.literal("sherlock-logs-api"),
  version: z.string().min(1),
  status: z.literal("ok"),
  stage: z.literal("foundation"),
  checked_at: z.iso.datetime(),
  uptime_seconds: z.number().int().nonnegative(),
  integrations: z
    .array(
      z.object({
        id: z.enum(["authentication", "database", "detector"]),
        name: z.string(),
        status: z.enum(["not_configured", "not_trained"]),
        detail: z.string(),
      }),
    )
    .refine(
      (items) =>
        items.length === 3 && new Set(items.map((item) => item.id)).size === 3,
      "Expected all three foundation integrations",
    ),
});

export type SystemSnapshot = z.infer<typeof systemSchema>;
export type SystemCheck = { snapshot: SystemSnapshot; latencyMs: number };

export function getApiOrigin(
  raw = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000",
) {
  try {
    const url = new URL(raw);
    if (
      !["http:", "https:"].includes(url.protocol) ||
      url.username ||
      url.password ||
      url.pathname !== "/" ||
      url.search ||
      url.hash
    )
      throw new Error("Invalid origin");
    return url.origin;
  } catch {
    throw new Error(
      "Set VITE_API_BASE_URL to an HTTP(S) origin, such as http://127.0.0.1:8000.",
    );
  }
}

export async function fetchSystem(signal?: AbortSignal): Promise<SystemCheck> {
  const origin = getApiOrigin();
  const started = performance.now();
  let response: Response;
  try {
    response = await fetch(`${origin}/api/v1/system`, {
      signal: signal
        ? AbortSignal.any([signal, AbortSignal.timeout(5_000)])
        : AbortSignal.timeout(5_000),
      credentials: "omit",
      cache: "no-store",
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new Error(
      "Cannot reach the API. Start the backend and check its URL and allowed origins.",
    );
  }
  if (!response.ok)
    throw new Error(
      `The API returned HTTP ${response.status}. Try checking again.`,
    );
  const parsed = systemSchema.safeParse(
    await response.json().catch(() => null),
  );
  if (!parsed.success)
    throw new Error(
      "The API response does not match the expected system contract.",
    );
  return {
    snapshot: parsed.data,
    latencyMs: Math.max(1, Math.round(performance.now() - started)),
  };
}
