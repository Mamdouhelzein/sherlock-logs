# Implementation roadmap

The repository and runnable foundations are complete. Identity integration is built; hosted Supabase setup and verification are pending. Detection milestones remain planned.

## 1. Runnable foundation

- [x] Scaffold React/TypeScript with Vite and FastAPI.
- [x] Add compatible dependency manifests and lockfiles.
- [x] Add health checks and environment validation.
- [x] Add local services and documented startup commands.

Done when a new developer can start the frontend and API from the documented instructions.

## 2. Authentication and data access

- [x] Implement registration, login, PKCE confirmation/recovery, logout, and protected routes.
- [x] Define profile migrations, column grants, RLS, and server-controlled roles.
- [x] Add API/SQL checks for profile isolation, forged metadata, self-promotion, and revocation.
- [ ] Create the hosted project, apply migrations, and configure email redirects/delivery.
- [ ] Verify hosted sign-in, recovery, two-account isolation, roles, and rate-limit behavior.
- [ ] Apply equivalent access boundaries to investigation records when those tables exist.

Done when sign-in works and authorization checks pass independently of the ML service.

## 3. Trusted telemetry

- [ ] Audit Supabase telemetry coverage, especially failed attempts.
- [ ] Document supported event sources and missing fields.
- [ ] Implement validated ingestion, deduplication, and pending-event persistence.
- [ ] Exclude secrets and define event retention.

Done when controlled login successes and failures produce trustworthy event records.

## 4. Dataset and baseline

- [ ] Generate individual user habits and legitimate behavior changes.
- [ ] Simulate brute force, spraying, and suspicious successful logins locally.
- [ ] Implement chronological feature extraction and cold-start defaults.
- [ ] Implement configurable rule and statistical baselines.

Done when scenarios reproduce with a seed and tests detect future-data leakage.

## 5. ML experiments

- [ ] Train Isolation Forest on an initial mostly benign period.
- [ ] Select a threshold using validation data and a false-alert budget.
- [ ] Compare rules-only, ML-only, and combined detection.
- [ ] Evaluate later held-out data, fresh seeds, and changed scenario parameters.
- [ ] Publish actual metrics and false-positive/missed-attack examples.

Done when results reproduce from commands without tuning on the test set.

## 6. Background inference

- [ ] Claim pending events with expiring leases.
- [ ] Add retry-safe scoring and model version tracking.
- [ ] Group related events into incidents.
- [ ] Surface unavailable models and backlog without breaking sign-in.

Done when a controlled event becomes an incident and retries do not duplicate results.

## 7. Investigation interface

- [ ] Build overview, incident list, incident timeline, and account history.
- [ ] Show observed signals, model version, and anomaly score.
- [ ] Add restricted status changes with audit records.
- [ ] Add a development-only scenario replay.

Done when an administrator can follow the full event-to-investigation flow.

## 8. Portfolio release

- [ ] Add backend, frontend, integration, and authorization checks to CI.
- [ ] Document staging deployment and production settings.
- [ ] Add screenshots, a demo recording, and benchmark reports.
- [ ] Verify a clean setup from scratch.

Done when another developer can run the demo and reproduce the reported evaluation. Synthetic results must be identified as synthetic.
