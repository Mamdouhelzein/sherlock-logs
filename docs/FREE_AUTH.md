# Free self-hosted authentication

The chosen route runs open-source Supabase Auth, PostgreSQL and PostgREST with a mandatory local gateway. The account guard executes inside Auth for every password request, including requests that skip React and FastAPI. There is no hosted hook subscription. This is an isolated local development realm; cloud deployment and migration of the existing hosted accounts are separate release gates.

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

The browser suite uses the real Supabase JS client and local email links, with no mocked provider:

```bash
npm --prefix frontend exec -- playwright install chromium
cd frontend
npx playwright test --config playwright.free-auth.config.ts
```

It exercises registration, confirmation/PKCE, private profile access, five failed sign-ins, a denied correct password, recovery/PKCE, password update and return to the account on desktop and mobile. It uses fictional `@example.test` accounts only. Browser fixture accounts/messages remain local; CI uses an ephemeral runner. No tests target the existing hosted account or consume the earlier two-request hosted-test authorization.

## Cutover and remaining work

The hosted app on port 5173 and its monitoring database are a different realm. Until cutover, its hosted password endpoint still has only the protections configured in that project. The new local guard must not be advertised as protecting that hosted realm.

Before moving real accounts, take and test a private backup, select a documented compatible Auth export/import or owner-led recovery migration, preserve UUID/profile/role relationships, and inventory all session issuers and API origins. Imported password hashes and token/session material are credentials, must never enter Git, and require a deliberate private migration. Do not point a second Auth service at the hosted Auth schema or disable the old service as a shortcut. Verify identity isolation, restoration and rollback before changing the live app configuration.

Local successful-login audit collection can reuse the existing collector against the separate generated connection. The hosted Management API failure-log token does not apply here and is explicitly empty in this realm. A self-hosted trusted failure/rejection publisher and investigation-health reporting remain separate work. A denied correct password must not be recorded as an observed incorrect password. ML scoring remains independent of enforcement and is disabled in the new preview until its local worker is configured.

This configuration is for an awake local machine, not an always-on production service. A public deployment requires an actual hosting target, HTTPS, private database/service networks, real SMTP, backups/restore checks, key management, trusted-proxy configuration, health monitoring, and security updates. Free software does not guarantee zero-cost production infrastructure.

References: [self-hosted Auth hooks](https://supabase.com/docs/guides/self-hosting/self-hosted-auth-hooks), [Supabase Auth source](https://github.com/supabase/auth/tree/v2.197.0), [Docker port bindings](https://docs.docker.com/reference/compose-file/services/#ports), [Mailpit API](https://mailpit.axllent.org/docs/api-v1/).
