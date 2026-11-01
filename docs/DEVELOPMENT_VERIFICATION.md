# Development connection verification

Checked on 2026-11-01 against the development Supabase project. Configuration and credentials remain local and untracked; cloning this repository does not connect another installation.

## Verified

- Identity and private telemetry schemas are installed. Anonymous profile and role-helper requests are denied.
- Supabase Auth responds, with email confirmation required.
- Site URL is `http://127.0.0.1:5173`. Exact redirect allowlist entries are `/auth/callback` and `/reset-password` on that origin; settings persisted after reload.
- Both server logins connect through the session pooler with TLS certificate and hostname verification. Neither login has superuser, database/role creation, replication, or BYPASSRLS rights.
- The API login can SELECT and INSERT events, but cannot UPDATE or DELETE them. A probe insert was rolled back; no synthetic login was persisted.
- The collector login can SELECT the private login-only source projection, but cannot modify it or read the raw audit payload. Neither server login can read `auth.users` or `private.user_roles`.
- Source inspection succeeded. Two bounded collection runs each returned zero scanned/inserted/duplicate/rejected events and `complete=true`. An empty run establishes connectivity, not event-delivery or deduplication coverage.
- The administrator bootstrap password and temporary credential recovery file were removed after restricted credentials were saved in local `.env`.

## Still required

Create and confirm a development app account, then verify successful login, profile persistence, recovery, member/admin authorization, revocation, and two-account isolation against the hosted service. Review the hosted password policy, email delivery, and rate limits. Capture a controlled real login and collect it twice to establish source context and deduplication behavior without publishing private log fields.

Database audit telemetry supports successful login entries only. No real failed-login publisher, collection scheduler, retention scheduler, ML detector, or deployed investigation dashboard is connected. Synthetic CI tests do not establish hosted security behavior or real-world detection effectiveness.
