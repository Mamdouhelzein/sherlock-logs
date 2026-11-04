# Implementation roadmap

Repository, application, identity integration, telemetry infrastructure, and offline dataset/model experiments are built. Isolation Forest has been trained, calibrated, and evaluated on synthetic data, including frozen evaluations on other seeds. Development Supabase is connected; real sign-in and successful-login collection/deduplication are verified. Remaining authorization checks, per-account brute-force protection, and the failed-login publisher remain pending. The leased background worker and private investigation records are implemented and tested. A restricted local worker is active against development Supabase and has scored the real collected login once. Synthetic results do not establish production effectiveness.

## 1. Repository foundation

- [x] Create the public repository and architecture/roadmap documentation.
- [x] Add contribution guidance, security boundaries, license, and issue templates.

## 2. Runnable foundation

- [x] Scaffold React/TypeScript with Vite and FastAPI.
- [x] Add compatible dependency manifests and lockfiles.
- [x] Add health checks and environment validation.
- [x] Add local services and documented startup commands.

Done when a new developer can start the frontend and API from the documented instructions.

## 3. Authentication and data access

- [x] Implement registration, login, PKCE confirmation/recovery, logout, and protected routes.
- [x] Define profile migrations, column grants, RLS, and server-controlled roles.
- [x] Add API/SQL checks for profile isolation, forged metadata, self-promotion, and revocation.
- [x] Create the development project, apply schemas, and configure exact local email redirects.
- [x] Review hosted password policy, email delivery, and authentication rate limits.
- [x] Verify a real hosted password sign-in, private profile loading/saving, session restoration, and member-route denial.
- [ ] Verify hosted recovery, two-account isolation, direct member/admin API access, role revocation, and rate-limit behavior.
- [ ] Enforce and verify per-account brute-force protection at an authentication boundary that cannot be bypassed through direct provider requests.
- [x] Apply equivalent access boundaries to investigation records (SQL and API tests; hosted checks pending).

Done when sign-in works and authorization checks pass independently of the ML service.

## 4. Trusted telemetry

- [x] Review upstream audit behavior and document success-only audit scope and missing context.
- [x] Implement bounded, signed service ingestion and strict allowlisted events.
- [x] Add transactional deduplication, conflict rollback, private persistence, and pending status.
- [x] Add paginated administrator-only reads and least-privilege server group roles.
- [x] Exclude secrets and implement configurable retention plus physical cleanup.
- [x] Add an idempotent audit collector that rescans to catch late source records.
- [x] Test signatures, browser write rejection, SQL access, concurrent retries, and retention.
- [x] Connect restricted server logins and inspect the hosted private audit projection.
- [x] Enable database audit writing in the development project and verify the setting persists.
- [x] Capture a real successful login and verify that collecting it again inserts no duplicate.
- [ ] Inspect controlled successes, wrong passwords, and unknown accounts in the hosted project.
- [ ] Connect and verify a trusted failed-login publisher before claiming attack-attempt coverage.
- [ ] Schedule and monitor collection and physical retention cleanup in the deployment.

Done when controlled login successes and failures produce trustworthy event records.

## 5. Dataset and baseline

- [x] Generate individual user habits and legitimate behavior changes.
- [x] Simulate brute force, spraying, and suspicious successful logins locally.
- [x] Implement chronological feature extraction and cold-start defaults.
- [x] Implement configurable rule and statistical baselines.
- [x] Verify reproducibility and leakage checks, and publish actual synthetic baseline results.

Done when scenarios reproduce with a seed and tests detect future-data leakage.

## 6. ML experiments

- [x] Train Isolation Forest on an initial mostly benign period.
- [x] Select a threshold using validation data and a false-alert budget.
- [x] Compare rules-only, ML-only, and combined detection.
- [x] Evaluate later held-out data, fresh seeds, and changed scenario parameters.
- [x] Publish actual metrics and false-positive/missed-attack examples.

Done when results reproduce from commands without tuning on the test set.

## 7. Background inference

- [x] Claim pending events with expiring leases.
- [x] Add retry-safe scoring and model version tracking.
- [x] Group related events into incidents.
- [x] Surface unavailable models and backlog without breaking sign-in through administrator APIs.
- [x] Activate a dedicated local worker against hosted Supabase and verify real collection-to-score flow.
- [ ] Deploy an always-on worker alongside scheduled collection and retention.

Done when a controlled event becomes an incident and retries do not duplicate results.

## 8. Investigation interface

- [x] Build the administrator-only overview, event ledger, incident list/timeline, and server-filtered account history.
- [x] Show observed signals, model version, anomaly/rule scores, thresholds, features, and context warnings.
- [ ] Add restricted status changes with audit records.
- [ ] Add a development-only scenario replay.

Done when an administrator can follow the full event-to-investigation flow.

## 9. Portfolio release

- [ ] Add backend, frontend, integration, and authorization checks to CI.
- [ ] Document staging deployment and production settings.
- [ ] Add screenshots, a demo recording, and benchmark reports.
- [ ] Verify a clean setup from scratch.

Done when another developer can run the demo and reproduce the reported evaluation. Synthetic results must be identified as synthetic.
