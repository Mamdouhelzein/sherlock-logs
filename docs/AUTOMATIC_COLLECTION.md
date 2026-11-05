# Automatic collection and physical retention

Status: activated and verified in the development project on 2026-11-05 after owner approval. A local collector runs every 30 seconds after each cycle; Supabase Cron runs 30-day cleanup hourly. The first cleanup deleted zero expired records and preserved the existing login. See [development verification](DEVELOPMENT_VERIFICATION.md) for evidence and remaining limits. Existing scoring and sign-in continue independently.

## Collection

The separate `sherlock-collector` / `python -m sherlock_api.telemetry.scheduler run` process connects only through the existing read-only audit projection login and restricted event-ingestion login. Neither role can read Auth accounts. No new login credential or administrator database password is required. The local processes read shared private configuration; this is not operating-system credential isolation. The Compose collector receives only its required database credentials.

The default interval is 30 seconds **after a cycle completes**. A database-fenced 120-second lease prevents overlapping scheduled collectors. Progress renews the lease before/after each bounded page. Only the current unexpired run can finish; an expired run cannot overwrite a newer result. Event IDs and original facts retain transactional deduplication across retries and manual collection. Stops are checked between pages; a finished batch can commit before shutdown, then the next run safely rescans it.

The initial run scans the retention window. Regular scans cover the most recent hour, while a successful full-window rescan is required every six hours and after a collection-window change. This reduces repeated long-history queries but means older, late-committed source rows may take up to the next full rescan to appear. Invalid rows or incomplete bounded scans do not establish successful coverage and leave a full scan due. A retention-window change is not considered covered until a full scan of that window succeeds.

Pages contain at most 100 rows and valid rows are inserted in one transaction per page. Conflicting IDs roll back that page. A run has a configurable page budget, source/DB statement bounds, and exponential source-error backoff capped at 15 minutes. Lease loss, partial scans, errors, and stopping never publish a successful scan. Console output and stored operational state contain aggregate counters and allowlisted error codes, not provider payloads, emails, IPs, passwords, or connection strings.

## Setup

1. Apply `supabase/migrations/202611050001_telemetry_operations.sql` after the identity, telemetry and inference migrations. This adds private operational state, metadata-only functions for the ingestion group, and read-only administrator monitoring. It does not enable cleanup.
2. Keep `DATABASE_URL` and `COLLECTOR_DATABASE_URL` in the ignored local `.env` with mode 0600. Use verified TLS. Set `COLLECTION_INTERVAL_SECONDS=30` and `COLLECTION_MAX_PAGES=1000` unless the source volume requires another bounded budget.
3. Start the separate process from the repository root:

```sh
PYTHONPATH=backend/src backend/.venv/bin/python -m sherlock_api.telemetry.scheduler run
```

For a bounded verification cycle, use `collect-once` instead of `run`. It records a stopped state when it exits; an exited one-shot command is not presented as a running daemon. A restarted daemon can claim immediately from a stopped state. Competing daemons wait without replacing each other's records.

The optional `telemetry` Compose profile uses the backend runtime without NumPy/model dependencies. For hosted TLS, set `INGEST_CONTAINER_DATABASE_URL` and `COLLECTOR_CONTAINER_DATABASE_URL` to the same restricted roles with `sslrootcert=/certs/root.crt` and `sslmode=verify-full`. Mount the trusted CA through `SUPABASE_CA_CERT_PATH`; a host-only certificate path in a DSN does not exist in a container. Never disable certificate checking. Then run `docker compose --profile telemetry up --build -d collector`. The service has no host port and receives no browser, service-role, signing, or scoring credentials.

Local processes pause when the laptop sleeps and do not automatically start after reboot. An always-on deployment remains separate. No authentication request waits for collection or scoring.

## Approved cleanup policy

Physical deletion is **disabled by default**. After explicit owner approval, run `supabase/setup/schedule_retention.sql` as the trusted owner. It enables Supabase Cron and schedules the named `sherlock-retention-30-days` job hourly. The setup also runs one bounded verification cycle.

The no-argument cleanup function reads the owner-controlled policy: keep 30 days by event observation time. The policy cannot be configured below 30 days. Each invocation deletes at most 10,000 expired event facts; linked jobs, scores and incident events cascade, and empty incident groups are removed. A backlog is reported until a complete bounded pass finds no more expired facts. Failed deletion rolls back before recording an error. A canceled transaction can leave old operational state; an overdue timestamp then exposes missing verification. This does not delete Supabase Auth accounts, profiles, provider audit logs, model files, or backups.

Only the owner/Cron can invoke cleanup; browser roles, the collector/API, scoring worker and read group cannot. There is no cleanup HTTP endpoint and no new cleanup password. The collector refuses a collection window wider than an enabled cleanup policy, preventing a misconfigured rescan from reintroducing already-expired observations. API read retention and physical policy should be configured consistently.

Deactivate this job through Supabase Cron to pause scheduled cleanup. Do not disable the entire extension: that removes all jobs, including unrelated ones. Cron execution history is provider operational data; its own growth/retention needs deployment monitoring and is not silently purged by this policy.

## Monitoring and limits

`GET /api/v1/admin/telemetry/status` uses current server-verified administrator authorization. It exposes last successful/complete scans, last full rescan, next attempt, aggregate last-run counters, partial/error/stopped/expired-lease states, retention policy and last cleanup. It never returns collection lease identifiers. Collection and retention health are separate from model readiness. Missing migration/storage returns a safe 503 for this check without breaking scoring reads or sign-in.

A ready collection result must be recent and have a non-overdue full rescan. A cleanup schedule alone is not proof of health: a successful cleanup within two hours is required. The dashboard is a snapshot at the last refresh. It reports stale collection, incomplete scans, missing schedules, cleanup backlog and outages distinctly. The optional [provider failed-login adapter](FAILED_LOGINS.md) adds separate recent-hour invalid-password coverage after approved token activation. Without it, failed-login collection remains unconnected. Automatic collection does not establish brute-force protection.

Tests cover fenced leases, contention, partial/error recovery, retention changes, disabled cleanup, fresh-row preservation, no browser/runtime cleanup authority, safe reporting, and independent overdue monitoring. Hosted timed collection and a successful cleanup must be verified separately from disposable-database and browser fixtures.

References: [Supabase Cron installation](https://supabase.com/docs/guides/cron/install), [job scheduling and monitoring](https://supabase.com/docs/guides/cron/quickstart).
