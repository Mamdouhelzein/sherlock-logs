# Step 4: trusted login telemetry

Status: the private event store, strict contract, service-signed ingestion, admin-only API, audit adapter, and retention command are implemented. **No hosted Supabase project is connected or verified.** A successful test against fixtures does not establish live event coverage.

## Coverage decision

The first collector reads `auth.audit_log_entries` through a read-only database connection. It accepts only the `login` action and maps it to a successful authentication event. It ignores refreshes, registrations, recovery requests, and other actions. It does not infer a failed attempt from the absence of a successful entry.

Supabase's [password-grant implementation](https://github.com/supabase/auth/blob/master/internal/api/token.go) returns invalid-credential errors before creating its login audit entry. Its [audit model](https://github.com/supabase/auth/blob/master/internal/models/audit_log_entry.go) also shows why database rows and external Auth logs can contain different context. These are upstream implementation observations, **not verification of your hosted version**.

| Source | Implemented support | Gaps |
| --- | --- | --- |
| Supabase database audit `login` rows | Successful logins with stable audit ID and timestamp; user ID/IP/user agent when present | Failed passwords and unknown-account attempts are not covered; IP/user agent may be missing |
| Signed trusted server adapter | Accepts explicit success/failure events from an authorized publisher | No provider-specific failed-login publisher is connected yet |
| Browser callbacks or user/admin bearer tokens | Cannot ingest events | Browser claims never establish login outcomes |

Supabase documents optional [database audit storage](https://supabase.com/docs/guides/auth/audit-logs). Check that it is enabled before using the database collector. Its [Password Verification Hook](https://supabase.com/docs/guides/auth/auth-hooks/password-verification-hook) supplies a known user ID and password-validity flag; the [hook availability table](https://supabase.com/docs/guides/auth/auth-hooks) currently lists it for Teams/Enterprise. This release does not enable a paid hook or add a synchronous authentication hook. Unknown-account attempts require additional verified telemetry even with that hook.

The supported initial scope is therefore successful Supabase audit events plus a restricted integration interface for a future verified server publisher. **Failed-attempt coverage remains a release gate for brute-force and password-spraying detection.** Missing context is stored as null, never fabricated. Login and session handling do not call ingestion or wait for ML.

## Database setup

1. Finish [Supabase identity setup](../supabase/README.md).
2. Apply [the telemetry migration](../supabase/migrations/202610300002_telemetry.sql) once after the identity migration. Keep `private` out of exposed Data API schemas.
3. Use trusted database administration to create dedicated **LOGIN** roles and strong passwords. The migration creates only **NOLOGIN group roles**, so no credentials are created automatically.
4. Grant the API database login membership in `sherlock_ingest` and `sherlock_reader`. It can insert/read events, but cannot update/delete facts or change user roles.
5. Apply [collector access setup](../supabase/setup/collector_access.sql) as a database owner with permission to grant access to Auth audit columns. Grant the separate collector login membership in `sherlock_audit_source`.
6. For retention, use a separate maintenance login with `sherlock_retention`. Use that connection as `DATABASE_URL` only in the maintenance command's environment. Avoid granting retention/delete access to the running API.

Example membership grants after you have created those named login roles:

```sql
grant sherlock_ingest, sherlock_reader to YOUR_EVENT_API_LOGIN;
grant sherlock_audit_source to YOUR_AUDIT_READER_LOGIN;
grant sherlock_retention to YOUR_RETENTION_LOGIN;
```

Do not use the normal `authenticated`, `anon`, `authenticator`, or browser role for any of these memberships. Do not use a superuser connection in the running application. The ingestion API and SQL adapters are trusted server boundaries.

Set server-only configuration in the untracked root `.env`:

```dotenv
DATABASE_URL=postgresql://EVENT_LOGIN:ENCODED_PASSWORD@YOUR_HOST:5432/postgres?sslmode=verify-full
COLLECTOR_DATABASE_URL=postgresql://AUDIT_LOGIN:ENCODED_PASSWORD@YOUR_HOST:5432/postgres?sslmode=verify-full
INGESTION_SIGNING_KEY=YOUR_RANDOM_SERVICE_KEY_WITH_AT_LEAST_32_BYTES
EVENT_RETENTION_DAYS=30
```

Generate the service key privately using `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. Share it only with the authorized server publisher. Store it in your deployment's secret manager and never in a `VITE_` setting, repository, browser, issue, or event body. Database URL passwords must be URL-encoded. Production requires `sslmode=verify-full`; configure the appropriate trusted root certificate for your PostgreSQL endpoint. Local disposable PostgreSQL can use an ordinary local connection.

## Inspect and collect

After installing the backend and restarting the API:

```bash
backend/.venv/bin/python -m sherlock_api.telemetry.cli inspect-source
backend/.venv/bin/python -m sherlock_api.telemetry.cli collect-once
```

The optional installed equivalent is `sherlock-telemetry`. Inspection reports schema access, IP-column availability, and explicit coverage limitations. Schema access is not proof that real login events are captured. Collection prints only counts: scanned, inserted, duplicate, rejected, and completion status. It does not print raw audit records, addresses, account identifiers, or credentials.

Each run scans the configured retention window in stable `(created_at,id)` order. Re-scanning catches late-committing source rows, and unique source IDs make retries safe. This prototype favors correctness over polling efficiency. Batches are bounded; `--max-pages` bounds a run (default 1,000 pages of 100). Exit 2 means incomplete scanning or rejected rows, and requires operator investigation. Raising the page limit may be needed for a backfill. Exit 1 means a configuration, database, schema, or data-conflict error. Commands never print exception details containing connection secrets.

Run collection periodically as a separate process in your deployment. The repository does not install a scheduler. Review collection cost and capacity before shortening the interval or using a large retention window.

## Signed service ingestion

`POST /api/v1/internal/events` is for an authorized server publisher. It is disabled without a signing key and event database. Bearer tokens from members or administrators cannot authorize ingestion. CORS does not permit browser POSTs.

Example contract (use an actual observation time within the retention window):

```json
{
  "events": [{
    "schema_version": 1,
    "event_id": "00000000-0000-4000-8000-000000000001",
    "occurred_at": "2026-10-30T10:00:00Z",
    "outcome": "failure",
    "user_id": null,
    "account_key": null,
    "source_ip": "192.0.2.1",
    "user_agent": null
  }]
}
```

The source is fixed to `trusted_auth_adapter` by the server; it cannot be chosen in JSON. `event_id` is a stable publisher-generated UUID that must survive retries. `account_key`, when used, is a lowercase 64-character HMAC-SHA256 hex digest computed by the trusted publisher with a separate private identifier key; do not send a raw email, username, or unsalted email hash. Define normalization and key rotation with the publisher before relying on cross-event account correlation.

Sign the **exact UTF-8 request bytes**:

```python
timestamp = str(int(time.time()))
signature = "v1=" + hmac.new(
    signing_key.encode(), timestamp.encode() + b"." + body, hashlib.sha256
).hexdigest()
# Headers:
# Content-Type: application/json
# X-Sherlock-Timestamp: timestamp
# X-Sherlock-Signature: signature
```

The receiver checks the signature in constant time and allows five minutes of clock skew. Replays within that window cannot create duplicate records. Retry using the same event IDs and facts; generate a fresh signature when necessary. Changed facts under the same source event ID return 409 and roll back the **whole batch**. Storage failures return 503 so publishers can retry without changing IDs. The future publisher needs its own durable queue/retry policy; this repository does not claim a provider delivery guarantee.

Requests allow 1–100 events and at most 128 KiB. Unknown fields, invalid UUIDs/IPs, timezone-free dates, future observations beyond five minutes, observations outside retention, and user agents over 512 characters are rejected. Raw payloads, email addresses, passwords, tokens, and arbitrary metadata have no storage fields. Validation errors never reflect rejected body values. API/gateway logs must not record request bodies, signatures, bearer tokens, or database connection strings.

The publisher must establish outcomes from the authentication server and verify original source context. The receiver does not turn a submitted IP or user agent into independently verified evidence. It ignores request forwarding headers; a publisher connection address is not the login visitor's address.

## Reading and retention

`GET /api/v1/admin/events?limit=50` requires the existing server-verified administrator role. Maximum page size is 100; pass the returned `next_cursor` for the next page. Results use descending `(occurred_at,id)` order and exclude payload digests. Browser accounts have no direct SQL/Data API access, including accounts whose UI says administrator. The API authorizes each read before using its server database connection.

All events start as `pending`; inference and processing leases come later. The default retention is **30 days by observation time**, configurable from 1–365 days. Reads exclude expired events, and ingestion rejects them. To physically remove expired rows, run daily with the dedicated retention connection:

```bash
backend/.venv/bin/python -m sherlock_api.telemetry.cli purge-expired
```

No cleanup schedule is installed automatically. An operator must schedule and monitor it; expired rows otherwise remain in the database even though API reads hide them. Cleanup uses bounded transactions. Historical `user_id` values intentionally have no foreign key to `auth.users`, so account deletion does not silently erase investigation history. For an approved account-data deletion, remove matching event rows using trusted maintenance access; also handle source logs and backups under the project's retention policy. Raw IPs and user agents are sensitive and must not be exposed in public demo artifacts.

## Live verification still required

After connecting a development project:

1. Confirm database audit storage and inspect the actual schema.
2. Make a controlled successful login, wrong-password attempt, and unknown-email attempt through the real application.
3. Check which events and fields exist in database audit logs versus external Auth logs. Record the hosted version, test times, source semantics, and gaps without copying secrets into the repository.
4. Run the collector twice: the second run must report duplicates and preserve original records.
5. Verify member/anonymous event reads and writes are denied. Promote/revoke an administrator and check API reads.
6. Attach and verify a real failed-login publisher before claiming brute-force/password-spraying coverage. Test malformed events, retries, conflicts, outage recovery, and the retention schedule.

CI covers transaction rollback, concurrent duplicates, keyset pagination with timestamp ties, late source rows, secret exclusion, retention, SQL privileges, invalid signatures, body bounds, and administrator authorization using disposable PostgreSQL and controlled fixtures. Synthetic tests are not live telemetry.
