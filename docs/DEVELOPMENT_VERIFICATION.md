# Development connection verification

Connection checks began on 2026-11-01; hosted sign-in checks were completed on 2026-11-03 against the development Supabase project. Configuration and credentials remain local and untracked; cloning this repository does not connect another installation.

## Verified

- Identity and private telemetry schemas are installed. Anonymous profile and role-helper requests are denied.
- Supabase Auth responds, with email confirmation required.
- A real password sign-in succeeded. The account page loaded only after the API verified the hosted session and returned Member access. The hosted dashboard also recorded the sign-in.
- The account loaded its own private profile, saved the existing display name successfully, and restored both the session and profile after a page reload. The administrator route displayed its member-access denial. This UI check does not independently prove a direct member request to the admin API is denied.
- Site URL is `http://127.0.0.1:5173`. Exact redirect allowlist entries are `/auth/callback` and `/reset-password` on that origin; settings persisted after reload.
- Both server logins connect through the session pooler with TLS certificate and hostname verification. Neither login has superuser, database/role creation, replication, or BYPASSRLS rights.
- The API login can SELECT and INSERT events, but cannot UPDATE or DELETE them. A probe insert was rolled back; no synthetic login was persisted.
- The collector login can SELECT the private login-only source projection, but cannot modify it or read the raw audit payload. Neither server login can read `auth.users` or `private.user_roles`.
- Source inspection succeeded. Two bounded collection runs each returned zero scanned/inserted/duplicate/rejected events and `complete=true`. An empty run establishes connectivity, not event-delivery or deduplication coverage.
- The administrator bootstrap password and temporary credential recovery file were removed after restricted credentials were saved in local `.env`.
- On 2026-11-03, the initial successful sign-in was followed by empty collector runs. Database audit writing was found disabled, then enabled in Authentication > Audit Logs and verified after reload. After the user signed out and signed in again, collection scanned one real login and inserted one event, with zero rejections. An immediate retry scanned the same login, inserted zero events, and reported one duplicate. Both runs completed successfully. This verifies successful-login capture and retry deduplication; field completeness and failed-login coverage remain separate checks.

## Still required

Verify recovery, direct member/admin API authorization, role revocation, and two-account isolation against the hosted service. The approved server policy uses an 8-character minimum with no required character combinations; the app accepts 8–128 characters and spaces. Email confirmation remains enabled. The built-in email provider limits broader hosted testing; custom delivery still needs setup. Inspect the captured login's available context without publishing private log fields. Custom per-account password-attempt limiting is not implemented; provider IP limits do not establish that protection.

Database audit telemetry supports successful login entries only. Provider failure-log reads are now active as recorded below; an always-on cloud collector/worker is not connected. The local dashboard, collection scheduler, shadow-scoring worker, and hosted retention schedule are connected as recorded below. Synthetic CI tests do not establish hosted security behavior or real-world detection effectiveness.

## Confirmation troubleshooting

The hosted dashboard showed the development account as confirmed while its last sign-in was still empty. Confirmation and completion of a PKCE session are separate checks; password sign-in is the recovery path before requesting another email. The exact cause of the failed callback has not been established.

The project uses the built-in email service. Supabase documents a [two-message hourly project limit and team-address restriction](https://supabase.com/docs/guides/auth/auth-smtp). The reported delivery stop after two messages is consistent with that quota; no extra emails were sent during diagnosis. The app now distinguishes email-send limits from generic failures and explains the sign-in recovery path.

During the email investigation on 2026-11-03, the existing development account was confirmed but its last-sign-in field was still empty; the later real password sign-in described above resolved that check. Custom SMTP remains disabled. The signup form's generic success response is not evidence that a new email was sent; Supabase can obscure responses for existing accounts. Registration guidance now states that delivery is not confirmed and directs existing users to password sign-in. No new confirmation emails were requested during this check. Delivery for new users remains unverified until custom SMTP is configured and tested.

## Shadow worker activation, 2026-11-04

The inference migration and dedicated scoring login were applied after approval. TLS certificate and hostname verification succeeded. The login inherits only `sherlock_worker`, has no elevated role flags, cannot read Auth accounts or role assignments, cannot edit original event facts, and cannot directly insert results. All six scoring tables have RLS enabled. Its credential is saved only in ignored local configuration with mode 0600.

The trusted pinned artifact scored the existing real collected login: one claimed, one processed, zero flagged, zero retries or lost leases. An immediate second run claimed and processed zero events. The stored result has the expected model version, feature snapshot, scores, and explicit missing-IP/browser, cold-start, limited-history, and retention-history warnings. No incident was fabricated for this unflagged event. Incident creation and duplicate prevention were verified independently in disposable PostgreSQL tests.

A separate local daemon reports a fresh ready heartbeat. It runs while the laptop is available; it is not a boot-time service or cloud deployment. New successful logins must first be collected by the separate collector. Failed-login coverage remains absent. Hosted administrator/member HTTP checks still require appropriate user sessions; no account was promoted during worker activation.

## Investigation dashboard, 2026-11-04

After the owner approved a targeted application-role change for the existing confirmed development account, its normal hosted session passed both identity and administrator checks. The live `/investigations` page loaded one actual successful login and the persisted Isolation Forest/rule scores and thresholds, missing-context warnings, model label/fingerprint, and feature version. Server-filtered account history loaded the same event; the incident view showed zero groups. The model had not flagged this login. No synthetic fixture was inserted into Supabase. The original Member denial was observed before the approved promotion.

The new read-only event query, decision/outcome/account filters, keyset pagination, and rich detail were also checked through the restricted server reader. Anonymous requests to the deployed local API were denied. Full hosted role-revocation, direct member HTTP denial, recovery, and two-account isolation still require independent checks; fixture tests are not substitutes for those hosted checks. Code validation passed on GitHub Actions, including disposable PostgreSQL, worker container, frontend/API containers, backend/ML/frontend checks, and all desktop/mobile browser flows.


## Automatic collection and retention activation, 2026-11-05

After the owner approved automatic collection and permanent 30-day cleanup, the operational migration and named Supabase Cron schedule were applied to the development project. No new login credentials were created. Existing credentials remain in ignored local `.env` with mode 0600, and the temporary activation SQL file was removed.

The initial bounded full-window scan saw the existing login, inserted zero events, reported one duplicate and zero rejections, and completed successfully. The separate local daemon then completed at least six timed recent-hour cycles, with advancing successful-scan timestamps and no inserted or rejected events. The database showed a completed full rescan, the 30-second interval, and a next scheduled attempt. These empty incremental cycles establish timed operation; they do not establish capture of a new login during this verification.

The first cleanup completed with zero deletions, no backlog, and the existing event preserved. The named hourly timer subsequently executed successfully at 2026-11-05 16:17 UTC (18:17 Asia/Beirut), independently of the local collector. Its recorded result was `succeeded`; retention remained `ready`, with zero deleted records and one retained event. The trained artifact and its existing score were preserved. Real expired-record deletion was not exercised against hosted user data; deletion, cascades and fresh-row preservation were verified in disposable PostgreSQL CI.

RLS is enabled on both operational tables. The API cannot directly update collection state or invoke cleanup. The audit-source login, scoring worker and authenticated browser role cannot invoke cleanup either. Anonymous HTTP access to the new administrator telemetry endpoint returns 401. The API, scoring worker and frontend were restarted locally; process liveness and frontend HTTP checks passed, and the scoring worker again reported a fresh ready heartbeat with one scored event and zero flagged events.

An existing hosted administrator session loaded the live investigation dashboard. It displayed healthy automatic collection and cleanup, the last full rescan and next attempt, zero cleanup deletions, and the original login with its ML evidence. These screenshots remain local and are not committed as public demo data. All seven CI jobs passed for the activated source revision: database, backend, machine learning, frontend, browser integration, application containers, and worker container.

Collection and scoring still depend on local processes and pause when the laptop sleeps; reboot does not automatically restart them. Supabase Cron cleanup runs on the hosted database. The subsequent failed-login activation is recorded below. Per-account brute-force protection, always-on deployment and the remaining hosted authorization/recovery checks are still outstanding.


## Approved provider failure-log activation, 2026-11-05

The owner approved a seven-day token scoped to this development project with Logs Read as its only capability, private `.env` storage, and the collection-health migration. The token was created through Supabase's resource/permission review and is stored in ignored local configuration with mode 0600. Supabase shows expiry on 2026-11-12. No token value or real event screenshot is committed. The read scope includes the project's other operational logs, but the fixed adapter query requests only allowlisted Auth failure facts. No billing, Auth configuration, account-management or database-administration access was granted to the token.

The metadata migration completed successfully. The ingestion login can execute its lease-fenced metadata function; the authenticated browser role cannot. The collector and API were restarted, while the existing healthy scoring worker continued. A Management API probe for project-settings access returned 403 for the read token. Browser raw-event reads and worker collection-metadata writes remain denied; anonymous HTTP access to telemetry status returns 401. The first Management API request rejected offset-form UTC parameters; the adapter now sends explicit `Z` timestamps, with regression assertions. After correction, repeated scheduled recent-hour reads completed successfully, with advancing scan/window timestamps and healthy source state. These empty incremental scans establish operation, not fresh failure delivery.

A bounded historical Management API query retrieved only the two controlled failures recorded earlier on this date. The source's explicit password-grant, POST token endpoint, status 400, invalid-credential code, timestamp and request ID were verified before ingestion. The first import inserted two events; retry inserted zero and reported two duplicates. Attempted account IDs and browser context remain explicitly unavailable. The earlier successful login was preserved.

The worker scored both imported failures, bringing the retained totals to three scored events: one success and two failures, with no pending or failed jobs at verification. Both controlled failures crossed the experimental model threshold and were grouped into one source incident. A real hosted administrator session displayed the events, scores, missing-account warnings and two-event incident timeline. These benign controlled attempts are not evidence of attacks; their anomaly flags demonstrate the need to evaluate false alerts and missing-context calibration.

Fresh post-activation delivery was verified in the subsequent check below. Source-based burst effectiveness, per-account brute-force protection and real-world model accuracy are not established. The reader's one-hour lookback can leave gaps after longer outages; collection/scoring still require awake local processes. The read token requires renewal before its displayed expiry. Backend regression checks passed (89 tests; 20 PostgreSQL tests skipped locally), with lint/format clean. The activation source revision passed all seven CI jobs, including the disposable PostgreSQL migration/access tests and the UTC API-parameter correction.


## Fresh automatic failed-login delivery, 2026-11-05

After explicit owner approval of the possible alert/temporary-lockout risk, exactly two password requests were sent to development Supabase: one deliberately incorrect password for the existing development account, and one for a nonexistent test address. Both returned HTTP 400 with `invalid_credentials` and provider request IDs. Neither sign-in request was retried, and no burst was run. The private test record tracks each attempted request before sending so an uncertain result does not justify repeating it.

The existing collector daemon picked up both provider log records without a manual collection command or event import. Their project-namespaced source IDs matched the two response request IDs exactly. Each was stored once and scored once. The maximum observed time from completion of the two requests to ingestion was approximately 39 seconds in this run; provider log delay and the scan interval can change that latency. A subsequent scheduled scan reported two scanned, zero inserted, two duplicates and zero rejected records. This verifies live delivery and retry deduplication, not only connectivity or historical replay.

The real administrator dashboard showed five retained scored events in total: one successful login, two earlier imported failures, and the two fresh automatically collected failures. The new failures formed a separate two-event source incident with its own timeline and scoring evidence. Their missing-account and missing-browser context remained explicit. Both controlled failures were flagged by the experimental model; these are benign test inputs, so the flags do not establish attack detection accuracy or protection.

All seven CI jobs for the activation revision passed. This verification required no code change; only the verification documents and roadmap were updated. Local collection/scoring, the one-hour failure lookback, the read-token expiry, and the remaining authorization/recovery, per-account throttling and model-calibration work retain their documented limits.
