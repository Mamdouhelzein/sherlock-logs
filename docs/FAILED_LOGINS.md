# Provider-confirmed password failures

Status: adapter, fenced health metadata, and dashboard reporting are implemented. Hosted activation requires an approved scoped Logs Read token and the metadata migration. No token has been created by this change yet.

## Source and scope

The existing audit projection remains the successful-login source. Password failures come from Supabase Auth server logs through the Management API, including attempts sent directly to the Auth provider. Browser event reports and a missing successful login are never treated as evidence of failure.

On 2026-11-05, two controlled requests (an incorrect password for the development account and a nonexistent test account) both returned `invalid_credentials`. Auth logs recorded explicit password grant, POST `/token`, status 400, error code, provider request ID, timestamp and remote address. These observations establish the source shape, not automatic ingestion. Raw emails, passwords and tokens were not saved with the verification record.

The fixed query selects only the fields needed to validate those explicit failures. The adapter accepts `invalid_credentials`, `grant_type=password`, `method=POST`, endpoint `/token`, and status 400 together. Other 400 errors, unconfirmed email, refresh-token errors, throttling, outages, signup and OAuth are not counted as invalid-password attempts. Provider logs do not establish the attempted account for these failures. `user_id` and `account_key` remain null; the model reports missing account context. Source-based burst features can still use the provider-reported address. Account-level brute-force or password-spraying effectiveness is not established by this source.

No raw log message is persisted. Only the strict login fact contract leaves the adapter. A project-namespaced UUID derived from the provider request ID deduplicates retries; reused IDs with conflicting facts fail instead of overwriting evidence. Successful logins continue to use only the audit adapter, avoiding duplicate success observations from two sources.

## Bounded collection and health

When enabled, the existing fenced collection daemon reads both sources under its current unexpired lease. Failure scans repeatedly cover the recent hour, with 100 rows per page and a default ten-page budget (maximum configurable budget 100). An explicit upper timestamp, strict keyset ordering and ID validation prevent an unbounded or repeating scan. HTTP requests have a timeout, refuse redirects and environment proxies, and accept at most 256 KiB of decoded response data per page. HTTP/query errors never log provider responses or credentials.

The source is healthy only after a complete scan with zero rejections. Bounded incomplete scans or provider failures publish partial/error state and back off; the overall collector does not report complete coverage. A separate metadata function only accepts updates from the current unexpired lease. Health expires after two minutes at the default interval (or three collection intervals, whichever is greater), checks the scanned window's end, and requires an active collector. Administrator responses include aggregate counts and timestamps, never the token or raw logs.

A one-hour rescan catches delayed logs within that window. A longer outage or provider log-retention limit can leave a gap. This is explicitly recent-hour invalid-password coverage, not complete historical authentication coverage. The six-hour full audit rescan does not backfill old provider failure logs. Rate limits/query allowance can interrupt this read path; do not silently reinterpret an empty or failed query as absence of attacks.

## Least-privilege setup

1. Apply `supabase/migrations/202611050002_failed_login_collection.sql` after the existing operations migration. It adds health columns and an ingestion-group function which records only fenced collection metadata. It creates no login roles, does not grant browser writes, and does not change cleanup or Auth settings.
2. Create a scoped personal access token for the single development project, with **Logs: Read only**, all other permissions None. The permission can read the project's other operational logs too; the collector's fixed query requests Auth failure facts only. Do not use a legacy full-account token. Token prefixes cannot prove scope; review the actual resource/permission summary.
3. Store `AUTH_LOGS_TOKEN` and the matching `AUTH_LOGS_PROJECT_REF` only in ignored server `.env` with mode 0600. The optional `AUTH_LOGS_MAX_PAGES` defaults to 10. Never add these to a `VITE_` setting, commit, browser storage, command argument, screenshot, CI output, or event body. The API and scoring worker do not need the log token in their container environments.
4. Restart the collector and API after the migration/configuration update. Verify the controlled records are inserted once, a retry reports duplicates, scoring completes, and the administrator dashboard identifies recent-hour coverage and missing account context. Test outages without changing real credentials.
5. Record the token expiry and rotate through the same scoped workflow before it expires. Removing/expiring the token must make monitoring report unavailable/stale coverage, not silently claim continued collection. A seven-day development token requires renewal after seven days; production credentials need an explicit rotation process.

This does not add per-account authentication throttling, block sign-ins, or deploy an always-on collector. Logs monitoring is asynchronous. Supabase's password-verification hook and log drains are separate paid options and are not enabled by this implementation.

## Validation

Unit tests cover explicit evidence, field exclusion, fixed destination, scoped-token configuration, retry identity, bounded pages/responses, invalid cursors, lease loss, error privacy, and partial-source reporting. Disposable PostgreSQL tests verify fenced metadata updates, stale health, and role restrictions. Desktop/mobile browser fixtures distinguish missing, recent-hour and overdue failure coverage. Hosted ingestion and alert behavior remain separate verification steps until activation.

References: [Auth hooks and plan availability](https://supabase.com/docs/guides/auth/auth-hooks), [Management API log access and permissions](https://supabase.com/docs/reference/api/v1-get-project-logs), [querying logs](https://supabase.com/docs/guides/observability/advanced-log-filtering), [scoped personal access tokens](https://supabase.com/docs/guides/platform/personal-access-tokens).
