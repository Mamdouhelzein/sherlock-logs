# Architecture

Status: React, FastAPI, Supabase authentication integration, private profiles, and administrator authorization are implemented. Configure a Supabase project and apply the migration to enable real sign-in. Telemetry ingestion, the worker, and detection remain planned.

## Implemented foundation

React calls `GET /api/v1/system` directly with an explicit API origin, a five-second timeout, runtime response validation, and manual retry. The overview reflects the last completed check. `GET /healthz` reports process liveness only. No login events are collected or stored. The architecture and setup pages remain accessible when the API is unavailable.

FastAPI validates environment settings, restricts CORS to configured origins, disables developer docs in production mode, and sends non-cacheable responses. CORS is a browser access policy, not authentication. Current endpoints contain public development status only. A `production` setting does not make this scaffold a complete production security system.

## Components

| Component | Responsibility |
| --- | --- |
| React + TypeScript + Vite | Account pages and administrator investigation interface |
| Tailwind CSS + shadcn/ui + Recharts | UI components and charts |
| Supabase Auth | Identity, authentication, and sessions |
| Supabase PostgreSQL | Durable events, processing state, model results, and incidents |
| FastAPI | Authenticated custom operations and trusted ingestion boundaries |
| Python worker | Historical features, security rules, and Isolation Forest inference |
| Offline Python training | Synthetic datasets, chronological evaluation, versioned artifacts |

## Event flow

1. A visitor authenticates through Supabase Auth.
2. A trusted server-side source captures authentication activity.
3. Ingestion validates and deduplicates records before saving pending events.
4. A worker claims pending events using database transactions and expiring leases.
5. The shared feature builder calculates context using only prior events.
6. Security rules and the active model score the event.
7. The worker atomically saves results and creates or updates an incident.
8. Authorized administrators inspect incidents through React.

Authentication must not depend on model availability. Retried processing must not create duplicate results. A database-backed polling worker is sufficient initially; Redis/Celery can be introduced when measured workload requires it.

## Authentication telemetry decision gate

Verify successful and failed login coverage, source IP semantics, timestamps, retention, and ingestion access with the actual Supabase project before implementing production ingestion. Auth audit logs must be inspected rather than assumed to include every required feature. Browser callbacks are untrusted telemetry and cannot establish authoritative authentication outcomes.

If required events are unavailable, document the gap and choose a controlled backend authentication adapter or narrower supported scope. Keep native Supabase protections independent of project monitoring.

## Planned entities

- `security_events`: event ID, observed/received timestamps, nullable account ID, hashed attempted-account key, source, optional browser context, outcome, processing state.
- `feature_snapshots`: event ID, feature schema version, historical feature values.
- `model_versions`: artifact reference, training ranges, threshold, package versions, validation metrics, activation state.
- `detection_results`: event ID, model version, raw score, decision, triggered rules.
- `incidents` and `incident_events`: grouped investigation records and supporting evidence.
- `audit_entries`: administrator status changes and model activation actions.

Use UTC, stable event ordering, account/time and source/time indexes, and unique constraints for deduplication. Scenario labels belong in evaluation-only data.

## Access boundaries

The browser receives a publishable Supabase key only. Enable explicit database grants and Row Level Security for exposed tables. Users may view permitted account data; investigator access must be enforced by server-managed roles and database/API policy. Users cannot assign themselves administrator privileges or write authoritative events, scores, or models.

FastAPI sends the bearer token to the fixed project's Supabase Auth `/auth/v1/user` endpoint for validation, rejects unconfirmed/anonymous accounts, then reads the caller's current database role through an authenticated-only RPC. It does not trust locally decoded claims, user metadata, or stale JWT role metadata. Both requests use the same token; transport failures deny access. `GET /api/v1/me` requires a confirmed account; `GET /api/v1/admin/status` additionally requires an admin assignment. Both are non-cacheable. No privileged API key is required.

Profiles have owner-scoped SELECT/UPDATE RLS and column-level update grants; browser users cannot insert or delete profiles or reassign their IDs. A trusted trigger creates profiles. Administrator assignments live in an unexposed private schema with no client grants. Role changes apply on the next API request. Direct API and Data API calls retain the same restrictions as the interface.

The SPA uses PKCE email callbacks and browser-persisted, auto-refreshed sessions. Tokens travel in Authorization headers and never enter event logs. Hosted email delivery and rate-limit behavior require verification after project creation. Treat caller-provided source headers and device identifiers as untrusted; trust forwarding headers only from configured proxies.

## Deferred extensions

External website integration, automatic remediation, geolocation enrichment, transformer log analysis, and multi-tenant organization support are outside the initial release.
