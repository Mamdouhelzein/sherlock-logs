# Background inference, step 7

Status: implemented and activated locally against development Supabase on 2026-11-04. The restricted worker scored one real collected login; an immediate second run claimed/processed zero events. A separate local daemon has a fresh ready heartbeat. The login was not flagged, so no hosted incident was created. Incident creation, concurrency, and retry behavior were checked separately on disposable PostgreSQL. Synthetic model metrics are not a production-readiness claim. Existing authentication remains independent of scoring.

## Boundaries

The worker loads an explicitly trusted, fingerprint-pinned local artifact in its own Python process. API startup does not import NumPy/scikit-learn or load model binaries. Model unavailability leaves queued events untouched; database outages are reported without leaking connection strings. The API can report detection storage unavailable while sign-in and other features continue.

New immutable event facts enqueue separate `private.scoring_jobs` rows through an owner trigger; the migration also queues existing facts. The old `security_events.processing_status` remains a legacy ingestion field and is not the scoring queue state. Read `/admin/events/{id}/detection` for authoritative job state.

The `sherlock_worker` NOLOGIN group has SELECT on event facts and EXECUTE on narrow claim/finalize/failure/model-registration/heartbeat functions. It cannot modify original events, directly insert/update/delete result tables, read Auth users, or assign administrator roles. Dedicated server logins must remain separate from API, browser, and collector roles. API readers receive read access only; all HTTP detection endpoints require the current server-verified admin role. Normal authenticated browser roles have no SQL access or function execution rights.

## Leases, history, and retries

Each claim locks one eligible job with `FOR UPDATE SKIP LOCKED`, issues a fresh token, and sets an expiring lease (60 seconds by default). Claim plus history reads run in a repeatable-read transaction. Serialization conflicts retry the whole claim transaction, with up to six attempts and bounded randomized backoff to prevent synchronized workers from repeatedly colliding. This avoids concurrent ingestion changing a context snapshot during construction. Raw event facts are never updated by scoring.

Only earlier `(occurred_at, internal_event_id)` facts enter history: the target account's preceding 30 days and the target source's preceding 5 minutes, bounded by retention. Internal event IDs prevent collisions between equal provider IDs from different sources. Missing accounts/sources never share a catch-all identity. A bounded row limit fails the job with `history_limit` rather than silently scoring truncated history. Results record snapshot time and context warnings for cold starts, missing context, short account histories, and meaningful retention truncation.

Late earlier events committed after a claim do not rewrite an existing score. Future claims see newly committed history. These are online event-time features using the history visible at claim time, not retroactively perfect knowledge. Events dated in the future wait until their observation time. Expired events are outside the worker's retention window.

Finalization locks the job and validates its current token/lease. Result insertion, optional incident linking, and processed state commit together. A stale token cannot finalize or mark a newer lease as failed. An uncertain successful commit is safe to retry: the processed job cannot produce another result. Failures back off exponentially and stop after five claims. Expiry on the fifth claim marks the job failed rather than leaving a permanent processing state. Failed jobs need operator review; no automatic endless replay is installed.

## Shadow incidents

The registered model stores both weights and calibration/schema fingerprints; different thresholds therefore create distinct version IDs even with identical weights. Thresholds come from immutable model registration. Shadow alerts follow the calibrated combined detector, with recorded scores, feature version, observed features, rule/ML signals, and context warnings. These are anomaly signals, not proof of compromise. They do not block accounts or send notifications.

Source burst/spread alerts group by source; other alerts prefer account, then source, then event. Grouping uses model version, entity, and a fixed UTC 15-minute bucket. A unique constraint makes concurrent links retry-safe. Bucket boundaries may split a related attack and account grouping may combine different activity in one window; this is an initial grouping policy, not an attack classifier. Retention deletion cascades jobs/results/links and removes empty incident identifiers. Model metadata and operational heartbeats are separate from login history.

## Hosted setup

1. Apply `supabase/migrations/202611040001_inference.sql` once as the trusted database owner after the existing identity/telemetry migrations. The CI bootstrap is for disposable test databases only.
2. Create a dedicated LOGIN with a strong random password and grant it only `sherlock_worker`. Do not expand the API login's memberships. Save its verified-TLS connection URL as `WORKER_DATABASE_URL` in the ignored root `.env` (mode 0600).
3. Reproduce or use the locally trained artifact, install the separate ML and backend runtime locks in a Python 3.13 environment, and calculate its version fingerprint:

```sh
PYTHONPATH=backend/src:ml/src ml/.venv/bin/python -c \
  'from pathlib import Path; from sherlock_api.detection.runtime import artifact_version; print(artifact_version(Path("artifacts/models/iforest-v1")))'
```

4. Set `MODEL_ARTIFACT_DIR`, `WORKER_MODEL_VERSION`, and `WORKER_TRUST_LOCAL_ARTIFACT=true` only for the artifact you created/trust. Hashes do not make untrusted joblib safe. Dependency versions and feature schema/code are verified before loading.
5. Run a bounded cycle, verify status/results, then run the daemon separately:

```sh
PYTHONPATH=backend/src:ml/src ml/.venv/bin/python -m sherlock_api.detection.cli process-once --max-jobs 100
PYTHONPATH=backend/src:ml/src ml/.venv/bin/python -m sherlock_api.detection.cli run --max-jobs 100
```

Install runtime dependencies with `pip install --require-hashes -r backend/requirements.lock -r ml/requirements.lock` in the worker environment. An optional container service uses `docker compose --profile inference up --build -d worker`, a non-root process, and a read-only artifact mount. It receives no collector, API, or browser credentials.

Set `DETECTION_ENABLED=true` for the API after enabling the separate worker and restart the API. This public configuration flag is not a live readiness probe and gives the API no worker credentials. Administrator status reads check the database heartbeat separately.

The daemon polls every 2 seconds by default and refreshes its heartbeat during long batches. SIGINT/SIGTERM stops between jobs; forced termination is recovered through leases. A one-shot run records a stopped heartbeat when it exits. Restart the worker to activate a deliberately changed pinned artifact. Existing processed events are not silently rescored.

The collector still needs to run separately to bring new provider logins into event storage; scoring does not grant the worker access to raw provider logs. Source collection and physical retention scheduling remain deployment tasks.

## Administrator API

- `GET /api/v1/admin/detection/status`: retained queue counts, scores/alerts counts, heartbeat freshness/readiness, model label, and explicit failed-login coverage gap.
- `GET /api/v1/admin/events/{event_id}/detection`: job state, model/version, scores/thresholds, feature snapshot, evidence, and warnings. Lease tokens are never returned.
- `GET /api/v1/admin/incidents?limit=50&cursor=...`: bounded keyset incident pages.
- `GET /api/v1/admin/incidents/{id}?limit=50&cursor=...`: bounded keyset event/evidence pages.

Reads enforce retention and existing server-side administrator authorization. Unknown/expired event IDs return 404. Missing migration/storage returns a safe 503, not a connection error body. Incidents can change while paging; refresh the list for newly updated groups. No model activation or incident mutation is exposed to browsers in this milestone. The read-only investigation frontend is at `/investigations`; see [the investigation guide](INVESTIGATIONS.md).

## Verification

Unit tests cover fail-closed authorization, role revocation, model/database outages, overflow, retries, and stale finalization. ML adapter tests compare online snapshots/scores with the exact offline code. Disposable PostgreSQL CI checks grants, concurrent claims, atomic retry-safe results/grouping, lease expiry, retry limits, prior-only history, snapshot validation, retention cascades, and private identifiers disappearing with empty incidents. Hosted checks on 2026-11-04 verified certificate/hostname-verified TLS, only the dedicated worker membership, no elevated role flags, no Auth/account-role access, immutable original events, and RLS on all six scoring tables. The actual stored result records its pinned model, scores, feature snapshot, and missing-source/browser/cold-start/history warnings. It was inserted once; a second cycle inserted nothing. A local daemon continued with a fresh ready heartbeat.

This is a local development process: laptop sleep/shutdown pauses processing, and no boot-time service or cloud worker is installed. Collection still runs separately. The next hosted login requires collection before the worker can score it; no automatic end-to-end collection schedule or real failed-login coverage is claimed.

References: [PostgreSQL queue locking](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE), [repeatable-read snapshots](https://www.postgresql.org/docs/current/transaction-iso.html#XACT-REPEATABLE-READ), and the [prototype model card](../ml/reports/iforest-v1.md).
