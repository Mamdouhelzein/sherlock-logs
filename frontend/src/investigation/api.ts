import { z } from "zod";
import { AccessError, getApiOrigin } from "../lib/api";

const timestamp = z.iso.datetime({ offset: true });
const nullableText = z.string().nullable();
const nullableScore = z.number().finite().nullable();
export const eventSchema = z.object({
  id: z.uuid(),
  occurred_at: timestamp,
  received_at: timestamp,
  source: z.enum(["supabase_audit", "trusted_auth_adapter"]),
  outcome: z.enum(["success", "failure"]),
  user_id: z.uuid().nullable(),
  account_key: nullableText,
  source_ip: nullableText,
  user_agent: nullableText,
  job_state: z
    .enum(["pending", "processing", "processed", "failed"])
    .nullable(),
  attempts: z.number().int().nullable(),
  last_error: nullableText,
  flagged: z.boolean().nullable(),
  ml_score: nullableScore,
  rule_score: nullableScore,
  signals: z.array(z.string()).nullable(),
  context_warnings: z.array(z.string()).nullable(),
  model_version_id: nullableText,
  artifact_label: nullableText,
});
export const detailSchema = eventSchema.extend({
  mode: z.literal("shadow").nullable(),
  features: z.record(z.string(), z.number().finite()).nullable(),
  feature_version: nullableText,
  ml_threshold: nullableScore,
  rule_threshold: nullableScore,
  history_as_of: timestamp.nullable(),
  scored_at: timestamp.nullable(),
});
export const incidentSchema = z.object({
  id: z.uuid(),
  model_version_id: z.string(),
  artifact_label: z.string(),
  entity_type: z.enum(["account", "source", "event"]),
  first_seen: timestamp,
  last_seen: timestamp,
  window_start: timestamp,
  event_count: z.number().int().nonnegative(),
});
export const timelineEventSchema = z.object({
  id: z.uuid(),
  occurred_at: timestamp,
  outcome: z.enum(["success", "failure"]),
  user_id: z.uuid().nullable(),
  account_key: nullableText,
  source_ip: nullableText,
  ml_score: z.number().finite(),
  rule_score: z.number().finite(),
  flagged: z.boolean(),
  signals: z.array(z.string()),
  context_warnings: z.array(z.string()),
  model_version_id: z.string(),
});
export const statusSchema = z.object({
  mode: z.literal("shadow"),
  worker_ready: z.boolean(),
  worker_fresh: z.boolean(),
  worker: z
    .object({
      status: z.enum(["ready", "model_unavailable", "stopped"]),
      last_seen: timestamp,
      model_version_id: nullableText,
      artifact_label: nullableText,
    })
    .nullable(),
  queue: z.record(z.string(), z.number().int().nonnegative()),
  scored: z.number().int().nonnegative(),
  flagged: z.number().int().nonnegative(),
  failed_login_coverage: z.literal("not_connected"),
});
export const pageSchema = <T extends z.ZodType>(schema: T) =>
  z.object({
    items: z.array(schema),
    next_cursor: nullableText,
    mode: z.literal("shadow"),
  });
export type InvestigationEvent = z.infer<typeof eventSchema>;
export type EventDetail = z.infer<typeof detailSchema>;
export type Incident = z.infer<typeof incidentSchema>;
export type TimelineEvent = z.infer<typeof timelineEventSchema>;

export async function investigationRequest<T>(
  path: string,
  token: string,
  schema: z.ZodType<T>,
  signal?: AbortSignal,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${getApiOrigin()}/api/v1/admin${path}`, {
      headers: { Authorization: `Bearer ${token}` },
      credentials: "omit",
      cache: "no-store",
      signal: signal
        ? AbortSignal.any([signal, AbortSignal.timeout(12000)])
        : AbortSignal.timeout(12000),
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new AccessError(
      0,
      "The investigation service could not be reached. Try again.",
    );
  }
  if (!response.ok)
    throw new AccessError(
      response.status,
      response.status === 401
        ? "Your session expired. Sign in again to continue."
        : response.status === 403
          ? "Administrator access is required. Your permissions may have changed."
          : response.status === 404
            ? "This event is unavailable or outside the retention window."
            : response.status === 422
              ? "This investigation link or filter is invalid."
              : "Investigation storage is unavailable. Check the API and database, then retry.",
    );
  const parsed = schema.safeParse(await response.json().catch(() => null));
  if (!parsed.success)
    throw new Error(
      "The service returned an unexpected investigation response. Refresh or check the API version.",
    );
  return parsed.data;
}
