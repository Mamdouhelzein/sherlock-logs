# Supabase

Planned services: Auth and PostgreSQL, with optional Realtime updates for authorized dashboard views.

## Setup sequence

1. Use a development project and record its public URL and publishable key.
2. Verify authentication telemetry coverage before designing ingestion around it.
3. Add versioned SQL migrations for events, feature snapshots, model versions, scores, incidents, and audit entries.
4. Define minimal grants and RLS policies for every exposed object.
5. Keep investigator roles server-controlled and privileged credentials server-side.
6. Test isolation between users, administrator authorization, and rejected client writes.
7. Define retention, indexes, deduplication constraints, and pending-event leases.

Do not automatically expose sensitive operational tables through the public Data API. Users must not be able to self-assign administrator privileges. Realtime subscriptions need the same access boundaries as ordinary reads.

Status: no Supabase project, schema migration, or policy has been provisioned. Secrets and local CLI state must not be committed.
