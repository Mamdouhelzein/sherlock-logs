# Free self-hosted authentication

The chosen route runs open-source Supabase Auth, PostgreSQL and PostgREST with a mandatory local gateway. The account guard executes inside Auth for every password request, including requests that skip React and FastAPI. There is no hosted hook subscription. This is an isolated local development realm; cloud deployment and migration of the existing hosted accounts are separate release gates. The local realm can now feed the existing event ledger, shadow worker and administrator investigations.

## Components and boundaries

| Component | Purpose | Host access |
| --- | --- | --- |
| Supabase Auth v2.197.0 | Password verification, confirmation, PKCE, recovery, refresh and sessions | No published port |
| Private SQL guard | Atomic per-account failure counter and fixed cooldown | Auth service only; outside Data API schemas |
| PostgreSQL 17 | Auth identities, existing application schemas, durable guard state | `127.0.0.1:54322` |
| PostgREST v16.5 | Existing profiles and caller-role RPC with JWT verification and RLS | No published port |
| Nginx gateway | Public-key check, exact development CORS, trusted source headers, Auth/Data API routing | `127.0.0.1:54421` |
| Local Mailpit inbox | Development confirmation/recovery messages | `127.0.0.1:54324` |
| Separate app/API preview | Existing React and FastAPI integration pointed at this realm | `127.0.0.1:5180` / `127.0.0.1:8001` |

The database and gateway base images are pinned by digest. Auth, PostgREST and Mailpit use explicit version tags. Review upstream security updates before deploying or refreshing them. Images are from official PostgreSQL/Nginx or Supabase distributions.

The gateway overwrites caller-supplied source headers, blocks Auth administration/metrics routes and leaves RLS authoritative for data reads. Auth and REST are reachable only on their Docker network. Server settings and strong generated credentials stay in ignored `.env.free-auth.local`, mode 0600. Only the project URL and an opaque `sb_publishable_` key enter React; the JWT signing secret and database passwords do not.

Gateway access and request-error logging are disabled because confirmation/recovery query strings contain one-time credentials. Use startup diagnostics and health checks instead of request dumps; do not turn on debug/request logging to investigate an account flow.

The API continues to verify tokens with its fixed Auth service and read the caller's current role through the same user's RPC. No local JWT decoding shortcut, trusted browser role, password proxy to the old hosted service, service-role browser key, or parallel public password endpoint is introduced for the new realm.

## Start locally

Install the backend dependencies using the root README, install frontend dependencies with `npm --prefix frontend ci`, and start Docker. Then, from the repository root:

```bash
backend/.venv/bin/python tools/free_auth.py up
```

The setup creates a separate persistent Docker volume, generates credentials once, starts Auth, applies the repository's application migrations and restricted role setup, installs the guard, and starts the public gateway last. It does not read the hosted `.env` credentials. The migration ledger and the guard are private. Rerunning setup preserves account and cooldown state. Do not delete the credential file while keeping its database volume; restore the matching file from a private backup instead.

Start the preview in two terminals:

```bash
backend/.venv/bin/python tools/free_auth.py api
backend/.venv/bin/python tools/free_auth.py frontend
```

Open [the separate app](http://127.0.0.1:5180/register). Create a local account and open its confirmation message in [the local inbox](http://127.0.0.1:54324) using the same browser/origin. Messages are captured locally; **they are not sent to Gmail or other real inboxes**. Confirmation remains required. Existing hosted sign-ins are not copied automatically and existing hosted sessions do not authenticate in this realm.

```bash
backend/.venv/bin/python tools/free_auth.py status
backend/.venv/bin/python tools/free_auth.py down
```

Shutdown preserves the volume. No destructive reset command or automatic volume deletion is provided. If the Docker CLI is not on PATH on macOS, add its actual installed `Contents/Resources/bin` location in your shell; this utility does not rewrite system links or Docker preferences.

## Connect collection and shadow scoring

After installing the ML environment from [the inference guide](INFERENCE.md), pin a model bundle you trained locally and trust. Pass its full bundle fingerprint (not a model filename or a made-up version):

```bash
backend/.venv/bin/python tools/free_auth.py pin-model --artifact-dir artifacts/models/iforest-v1 --model-version YOUR_64_CHARACTER_BUNDLE_FINGERPRINT
backend/.venv/bin/python tools/free_auth.py collector
backend/.venv/bin/python tools/free_auth.py worker
```

Run the last two commands in separate terminals. Restart the local API after pinning to update its configuration indicator. The worker validates the bundle, dependencies and shared feature code before deserializing it. Scoring stays in shadow mode and never controls the password guard. These commands use only generated local database connections; hosted failure-log credentials and hosted model settings are not inherited. The helper refuses connections that do not match this realm.

Successful sign-ins come from the provider audit view. A second private journal captures known-account incorrect passwords and cooldown rejections inside the provider hook. The collector reads only a fixed four-column projection, rescans its retained window, and deduplicates by the immutable journal UUID. The API, worker and browser cannot read or mutate the journal or execute the hook. Collection health distinguishes this journal from hosted Management API logs and becomes unhealthy when scans fail or become stale.

In the ledger, both rejection types are failed **sign-ins**. `invalid_password` reports an incorrect password observed by Auth; `cooldown_rejected` reports a policy block and makes no claim about password correctness. The evidence pane shows the distinction. The model uses denied-sign-in features for both, with an explicit cooldown context warning. Its synthetic calibration has not established accuracy for policy-rejected traffic. Source IP and browser context remain missing because the hook does not supply trusted values. Unknown-account, pre-hook rate-limit and other provider rejections are outside this journal's coverage.

The journal append and cooldown update share the provider transaction. A journal write failure denies that password attempt; it does not bypass protection. The separate collector/model can be stopped without removing the hook or changing the provider decision. The local realm limits reads to 30 days. Its separate opt-in cleanup service can also remove expired stored events, linked model results, empty incident groups, provider audit entries and guard-journal records; see below. The hosted cleanup timer does not run against this database.

## Automatic local cleanup

Inspect counts before activation:

```bash
backend/.venv/bin/python tools/free_auth.py cleanup-plan
backend/.venv/bin/python tools/free_auth.py enable-cleanup
```

Activation keeps 30 days of login history. It generates one separate private cleanup credential in ignored `.env.free-auth.local` (0600), installs the restricted routine, explicitly enables the local policy and starts the Docker maintenance service. Installation through ordinary `up` alone does not enable deletion. Once activated, `up` resumes that service and `down` stops it with the rest of this project; the database volume remains intact.

The container checks a durable database schedule every minute. A successful pass is due hourly, and a backlog/error is retried after one minute. A restart or wake from sleep rechecks the persisted deadline. Each transaction handles at most 10,000 expired rows from each source plus 10,000 empty incident groups. Expired event deletion cascades to linked jobs, scores and incident memberships. A failure rolls back the whole pass and publishes a generic error. Locked rows are skipped and reported as a backlog rather than waiting indefinitely. Cleanup has statement and lock time limits; logs contain bounded aggregate results only.

The execute-only cleanup login cannot read raw records, delete directly, change retention settings, invoke the password hook or modify accounts, sessions, profiles, roles or cooldowns. The routine itself has a separate non-login, non-superuser owner with narrowly scoped source-ID/time, expired-row and cleanup-metadata privileges. Provider-owned audit triggers therefore cannot borrow database-superuser authority through cleanup. The container runs as the image's non-root PostgreSQL user, drops capabilities, uses a read-only filesystem and publishes no ports. The normal administrator-only telemetry status includes separate journal/audit/empty-incident counts and the persisted next due time; Members do not gain dashboard access.

Cleanup removes rows from the working database, not from existing backups or Mailpit messages. PostgreSQL autovacuum makes deleted space reusable; database files need not shrink immediately. No blocking `VACUUM FULL` is scheduled. See [PostgreSQL 17 maintenance behavior](https://www.postgresql.org/docs/17/sql-vacuum.html). Backup expiry, real SMTP and always-on hosting remain separate work. This timer runs while Docker and the laptop are awake.

## Account policy

Five invalid password attempts in a fixed 15-minute window trigger a 15-minute cooldown for the account UUID, across sources. A correct password is also denied during that cooldown. New attempts do not extend the deadline. A valid verification outside the cooldown clears failures. Each account's row is locked during its decision; the database clock is read after acquiring the lock. Lock contention beyond 500 ms and malformed hook events fail closed. Existing sessions are not revoked by the guard.

Rejections use the same invalid-credentials message as a wrong password or missing account. Recovery remains independent and can establish a verified session during a cooldown; it does not let an anonymous browser clear the counter. Session refresh does not increment password failures. Successful password verification clears failures before the provider's later confirmation/session checks; it is not itself a claim that sign-in completed.

The hook runs after password verification, so provider IP limits remain necessary for resource abuse and nonexistent accounts. An attacker can deliberately trigger an account cooldown; bounded non-extending deadlines reduce one lockout's duration but do not eliminate repeated-lockout risk. See the [policy and threat model](BRUTE_FORCE_PROTECTION.md).

## Verification

Disposable PostgreSQL tests cover threshold behavior, persistence across connections, parallel failures, expiry, resets, malformed/unknown accounts, row-lock timeouts, account deletion and denied access for application/browser/collector/worker roles. These do not replace real Auth HTTP checks.

After `up`, run real HTTP checks against only this local realm:

```bash
TEST_FREE_AUTH=1 PYTHONPATH=backend/src backend/.venv/bin/python -m pytest backend/tests/test_free_auth_integration.py -q
```

These tests create disposable fictional accounts, verify the direct Auth boundary, preserve existing sessions/refresh during lockout, compare generic responses, verify independent accounts, profile RLS and current role revocation, and deny password login when hook execution is unavailable. They confirm only their own fixture accounts directly in SQL; they never confirm real user accounts.

The browser suite uses the real Supabase JS client and local email links, with no mocked provider. Its fixture helper temporarily grants an administrator role only to explicitly gated, confirmed `browser-UUID@example.test` accounts, collects their events, and removes that role in a finally block:

```bash
npm --prefix frontend exec -- playwright install chromium
cd frontend
npx playwright test --config playwright.free-auth.config.ts
```

It exercises registration, confirmation/PKCE, private profile access, five failed sign-ins, a denied correct password, recovery/PKCE, password update, return to the account and real cooldown evidence in the investigation desk on desktop and mobile. It uses fictional `@example.test` accounts only. Browser fixture accounts/messages remain local; CI uses an ephemeral runner. No tests target the existing hosted account or consume the earlier two-request hosted-test authorization.

## Cutover and remaining work

The hosted app on port 5173 and its monitoring database are a different realm. Until cutover, its hosted password endpoint still has only the protections configured in that project. The new local guard must not be advertised as protecting that hosted realm.

Before moving real accounts, take and test a private backup, select a documented compatible Auth export/import or owner-led recovery migration, preserve UUID/profile/role relationships, and inventory all session issuers and API origins. Imported password hashes and token/session material are credentials, must never enter Git, and require a deliberate private migration. Do not point a second Auth service at the hosted Auth schema or disable the old service as a shortcut. Verify identity isolation, restoration and rollback before changing the live app configuration.

Local audit and guard-rejection collection, current-role API checks, shadow inference and investigation evidence are connected. The hosted Management API failure-log token does not apply here and is explicitly empty. Migration of historical hosted records, owner account/profile reconciliation and broader provider rejection coverage remain separate work. Local physical retention is available through its explicit activation command. Applying these application changes to the hosted environment also requires the new event/evidence migrations before restarting its API; the local setup does not apply them remotely.

This configuration is for an awake local machine, not an always-on production service. A public deployment requires an actual hosting target, HTTPS, private database/service networks, real SMTP, backups/restore checks, key management, trusted-proxy configuration, health monitoring, and security updates. Free software does not guarantee zero-cost production infrastructure.

References: [self-hosted Auth hooks](https://supabase.com/docs/guides/self-hosting/self-hosted-auth-hooks), [Supabase Auth source](https://github.com/supabase/auth/tree/v2.197.0), [Docker port bindings](https://docs.docker.com/reference/compose-file/services/#ports), [Mailpit API](https://mailpit.axllent.org/docs/api-v1/).
