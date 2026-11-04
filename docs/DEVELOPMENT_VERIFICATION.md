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

Database audit telemetry supports successful login entries only. No real failed-login publisher, collection scheduler, retention scheduler, always-on cloud worker, or deployed investigation dashboard is connected. The local shadow-scoring worker is connected as recorded below. Synthetic CI tests do not establish hosted security behavior or real-world detection effectiveness.

## Confirmation troubleshooting

The hosted dashboard showed the development account as confirmed while its last sign-in was still empty. Confirmation and completion of a PKCE session are separate checks; password sign-in is the recovery path before requesting another email. The exact cause of the failed callback has not been established.

The project uses the built-in email service. Supabase documents a [two-message hourly project limit and team-address restriction](https://supabase.com/docs/guides/auth/auth-smtp). The reported delivery stop after two messages is consistent with that quota; no extra emails were sent during diagnosis. The app now distinguishes email-send limits from generic failures and explains the sign-in recovery path.

During the email investigation on 2026-11-03, the existing development account was confirmed but its last-sign-in field was still empty; the later real password sign-in described above resolved that check. Custom SMTP remains disabled. The signup form's generic success response is not evidence that a new email was sent; Supabase can obscure responses for existing accounts. Registration guidance now states that delivery is not confirmed and directs existing users to password sign-in. No new confirmation emails were requested during this check. Delivery for new users remains unverified until custom SMTP is configured and tested.

## Shadow worker activation, 2026-11-04

The inference migration and dedicated scoring login were applied after approval. TLS certificate and hostname verification succeeded. The login inherits only `sherlock_worker`, has no elevated role flags, cannot read Auth accounts or role assignments, cannot edit original event facts, and cannot directly insert results. All six scoring tables have RLS enabled. Its credential is saved only in ignored local configuration with mode 0600.

The trusted pinned artifact scored the existing real collected login: one claimed, one processed, zero flagged, zero retries or lost leases. An immediate second run claimed and processed zero events. The stored result has the expected model version, feature snapshot, scores, and explicit missing-IP/browser, cold-start, limited-history, and retention-history warnings. No incident was fabricated for this unflagged event. Incident creation and duplicate prevention were verified independently in disposable PostgreSQL tests.

A separate local daemon reports a fresh ready heartbeat. It runs while the laptop is available; it is not a boot-time service or cloud deployment. New successful logins must first be collected by the separate collector. Failed-login coverage remains absent. Hosted administrator/member HTTP checks still require appropriate user sessions; no account was promoted during worker activation.
