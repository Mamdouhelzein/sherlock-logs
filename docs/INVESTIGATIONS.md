# Investigation desk

Open `/investigations` from workspace navigation. The page first restores the Supabase session, asks the API to verify identity/current role, and checks administrator authorization. Members cannot fetch investigation records. Every investigation API read independently verifies the current server-controlled administrator role. No account is automatically promoted by the UI.

The desk shows retained scoring counts, failed/backlogged jobs, and worker readiness **at the last check**. Refresh checks again; the page does not claim to be a continuous live monitor. Coverage explicitly states the missing failed-login publisher. Shadow decisions do not block sign-ins.

The event ledger supports decision/outcome filters, keyset pages, and server-filtered account history. Search covers loaded records only. A selected event shows source facts, job state, calibrated ML/rule thresholds and scores, recorded signals, missing-context warnings, the original feature snapshot, and model/processing metadata. Model signals are not causal feature explanations or compromise probabilities.

The incident view lists retained fixed-window groups and their paginated event timelines. Selecting a timeline event opens its original evidence. Event/incident selection is deep-linkable through query parameters; credentials never enter URLs. An empty incident list does not claim all activity is safe. No sample data is displayed in the live UI.

## Read API

- `GET /api/v1/admin/investigation/events?limit=30&cursor=...` joins immutable facts with scoring jobs/results. Optional `flagged`, `outcome`, and one of `user_id` / `account_key` are server-side filters. Limits are 1–100; cursors, UUIDs, outcomes, and pseudonymous keys are validated. Queries use bound parameters and retention cutoffs.
- `GET /api/v1/admin/events/{id}/detection` includes retained event facts and scoring evidence for direct links.
- Status and incident APIs are documented in [INFERENCE.md](INFERENCE.md).

Private query keys include session identity/expiry, never bearer credentials. Requests use authorization headers, abort signals, and `cache: no-store`; private queries are removed on sign-out. Any later 401/403 investigation response replaces previously visible evidence with an access notice. Raw backend error bodies are not reflected in the UI.

## Validation and remaining scope

Browser tests use isolated fictional provider/API fixtures to exercise desktop/mobile evidence, incident timelines, account filtering, pagination, pending/empty/unavailable states, member denial, and permission revocation. These fixtures are not stored in development Supabase. Backend checks verify per-request authorization and input validation; disposable PostgreSQL tests cover combined account/decision/outcome filters, stable keyset pages, and pseudonymous account separation. Real restricted-reader checks separately verified the existing hosted event, empty flagged results, account filters, and pagination.

On 2026-11-04, the owner explicitly approved granting the existing development account application-level administrator access. The live browser then loaded the real retained successful login and its ML/rule scores, thresholds, model fingerprint, feature version, and context warnings. Server-filtered account history returned that event; the incident view correctly showed no retained groups. Member denial had been observed before promotion. Independent hosted member HTTP denial, role revocation, and two-account isolation remain separate checks. Restricted incident status changes with an audit trail and scenario replay are separate remaining roadmap items. This release is read-only; it does not add mutation controls or weaken existing grants.
