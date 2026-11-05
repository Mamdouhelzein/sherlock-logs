# Sherlock Logs

**The case of the suspicious sign-in.**

An ML-powered website security monitoring project that learns login behavior, flags unusual activity, and helps administrators investigate suspicious sign-ins.

## Status

The investigation dashboard and background scoring worker are implemented, tested, and connected locally to development Supabase. Automatic successful-login collection runs locally every 30 seconds after a cycle completes. An owner-approved Supabase Cron job performs hourly cleanup of collected records older than 30 days. Local collection and scoring pause when the laptop sleeps; an always-on deployment remains pending. Identity integration includes registration, login, confirmation/recovery, private profiles, and server-enforced administrator access. The worker uses leased jobs, pinned model versions, retry-safe results, and shadow incident grouping.

Development Supabase is connected locally with restricted server roles, private schemas, and exact local Auth redirects. Real sign-in, profile loading/saving, session restoration, and the member-only UI boundary were checked. Successful-login capture and retry deduplication are verified. After owner approval, a project-scoped Logs Read token enabled provider-confirmed password-failure collection from the recent hour. Timed reads are healthy; a bounded historical import of two controlled failures inserted each once, produced two model results, and grouped them into a source incident. Two fresh owner-approved invalid-password attempts were then automatically collected, matched by provider request ID, scored, and shown in the dashboard in about 40 seconds in this check. A later scheduled rescan reported two duplicates and inserted nothing. The source does not identify attempted accounts, and longer outages can leave coverage gaps. See the [failed-login guide](docs/FAILED_LOGINS.md).

The administrator investigation desk at `/investigations` displays the real retained records and their evidence. The model's flags on controlled failures are not proof of attacks or real-world accuracy. Recovery, two-account isolation, direct member/admin API checks, role revocation, per-account brute-force protection, and always-on deployment remain outstanding; see the [verification record](docs/DEVELOPMENT_VERIFICATION.md). Local credentials are untracked, so new clones still require the [setup guide](supabase/README.md).

## Project guide

Steps 5–6 include a reproducible dataset generator, 15 chronological features, rule/statistical baselines, and trained Isolation Forest experiments. Three synthetic evaluations and their limitations are documented in the [model card](ml/reports/iforest-v1.md). The model was trained offline; the separate background worker reuses its feature code and frozen calibration. Neither the experiments nor shadow scoring change live authentication.

- [Architecture](ARCHITECTURE.md): components, event flow, and access boundaries.
- [Roadmap](ROADMAP.md): implementation milestones and acceptance criteria.
- [Contributing](CONTRIBUTING.md): development and review conventions.
- [Security](SECURITY.md): reporting guidance and operational boundaries.
- [Frontend](frontend/README.md): React setup, UI structure, and checks.
- [Backend](backend/README.md): API configuration, endpoints, and checks.
- [ML](ml/README.md): training and evaluation protocol.
- [Supabase](supabase/README.md): project creation, migration, email setup, and administrator assignment.
- [Telemetry](docs/TELEMETRY.md): trusted event sources, coverage gaps, service signatures, collector, and retention.
- [Background inference](docs/INFERENCE.md): worker setup, model pinning, leases, shadow incidents, and administrator reads.
- [Failed-login adapter](docs/FAILED_LOGINS.md): provider-confirmed password failures, recent-hour scope, restricted access, and verification limits.
- [Automatic collection](docs/AUTOMATIC_COLLECTION.md): scheduled collection, operational monitoring, and approved physical retention.
- [Per-account protection plan](docs/BRUTE_FORCE_PROTECTION.md): enforcement boundary, proposed cooldown policy, Supabase plan prerequisite, and activation tests. Not active yet.

## Repository layout

```text
sherlock-logs/
├── frontend/          # React + TypeScript application
├── backend/           # FastAPI and detection worker
├── ml/                # Features, training, and evaluation
├── supabase/          # Database migrations and access policies
├── .env.example       # Configuration names; no credentials
├── ARCHITECTURE.md
├── ROADMAP.md
├── CONTRIBUTING.md
└── SECURITY.md
```

## Stack

| Component | Technology |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| UI | Tailwind CSS, shadcn-style button primitives, Lucide; Recharts planned |
| Authentication and database | Supabase Auth and PostgreSQL |
| Custom API | Python and FastAPI |
| Detection | Python background worker |
| Machine learning | pandas, NumPy, scikit-learn, Isolation Forest |
| Testing | pytest, Vitest, Testing Library, Playwright |
| Development and CI | Docker Compose, GitHub Actions |

## Planned capabilities

- Registration, login, and protected account pages (integration built; Supabase setup required).
- Trusted collection of authentication events.
- Historical features for failed-login bursts, source activity, browser familiarity, and unusual login timing.
- Rule-based detection compared against an Isolation Forest model.
- Incident grouping and an administrator investigation dashboard.
- Reproducible synthetic scenarios and chronological model evaluation.

## Architecture

```text
React frontend -> Supabase Auth / authorized application data
Trusted authentication events -> PostgreSQL pending events
Python worker -> historical features -> rules + Isolation Forest
Detection results -> incidents -> administrator dashboard
FastAPI -> restricted custom backend operations
```

An early implementation milestone is verifying Supabase authentication telemetry coverage, especially failed attempts and available source context. Browser-reported events will not be treated as authoritative.

## ML approach

Train Isolation Forest on mostly benign historical activity. Select an alert threshold on a separate validation period and evaluate on a later held-out period. Compare rules-only, model-only, and combined detection at comparable false-alert budgets.

Report precision, recall, false alerts per 1,000 benign logins, incident detection rate, time to first alert, and processing latency. Features must use only information available at the event timestamp. Scenario labels remain separate from model inputs.

Anomaly scores are not probabilities of account compromise. Synthetic benchmarks do not establish real-world effectiveness.

## Roadmap

- [x] Scaffold frontend, API, and local development services.
- [x] Implement Supabase Auth integration, database migrations, and access policies.
- [x] Provision development Supabase, apply schemas, and connect restricted server logins.
- [ ] Verify hosted sign-in, recovery, and rate limits.
- [x] Implement private event storage, signed ingestion, deduplication, and the audit collector.
- [x] Connect restricted provider failure-log reads and verify historical failure ingestion, deduplication, scoring and investigation.
- [x] Verify two fresh failures through the scheduled reader, scoring worker and live investigation dashboard.
- [ ] Complete the remaining hosted authorization, recovery and rate-limit checks.
- [x] Build synthetic normal activity and local attack scenarios.
- [x] Implement historical features and security-rule/statistical baselines.
- [x] Train, validate, and evaluate an offline synthetic-data anomaly detector.
- [x] Implement durable background scoring and incident grouping.
- [x] Activate and verify the restricted local worker against hosted events.
- [x] Build the protected investigation dashboard, incident timeline, and account history.
- [x] Verify a hosted administrator session in the dashboard.
- [ ] Add automated checks, benchmark results, and a recorded demo.

## Security boundaries

Authentication controls operate independently of telemetry and ML. Protected API reads validate the bearer token with Supabase and read the caller's current role from SQL. Ingestion instead requires a separate server-held signing key; browser/user/admin tokens cannot author events. Browser guards are navigation conveniences; API authorization, private schemas, grants, and RLS enforce access. The first detection release will generate investigation alerts rather than automatically blocking accounts.

Privileged Supabase credentials stay on the server. Database access policies and API authorization enforce administrator access. Passwords, access tokens, and raw session secrets must never enter event logs. Simulators run only against controlled development environments, and model artifacts must come from trusted training runs.

## Local setup

Clone the repository:

```bash
git clone https://github.com/Mamdouhelzein/sherlock-logs.git
cd sherlock-logs
```

The repository is public. Use **Node.js 22.12+ (24 recommended)** and **Python 3.12+ (3.13 recommended)**.

### Start the API — terminal 1

From the repository root on macOS/Linux:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements-dev.lock
backend/.venv/bin/python -m pip install --no-deps -e backend
backend/.venv/bin/uvicorn sherlock_api.main:app --reload --host 127.0.0.1 --port 8000
```

Windows PowerShell equivalents:

```powershell
py -3.13 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.lock
backend/.venv/Scripts/python.exe -m pip install --no-deps -e backend
backend/.venv/Scripts/uvicorn.exe sherlock_api.main:app --reload --host 127.0.0.1 --port 8000
```

### Start the frontend — terminal 2

```bash
cd frontend
npm ci
npm run dev
```

Open [the workspace](http://127.0.0.1:5173). It should show **API reachable** after the request completes. Use **Check again** to refresh; the connection status reflects the last manual check, not a continuous monitor. Use the navigation search button or **Ctrl/Cmd + K** to jump between pages. The animated evidence trail illustrates collection and does not show live activity. Use the header's motion control to pause it; reduced-motion preferences are respected.

- [Liveness](http://127.0.0.1:8000/healthz): process status, not database/model readiness.
- [System status](http://127.0.0.1:8000/api/v1/system): version, check time, uptime, and integration configuration (not a live readiness probe).
- [Interactive API docs](http://127.0.0.1:8000/docs): available in development/test environments.

Optional: copy `.env.example` to `.env` in the root and change the API origin or allowed frontend origins. Both Vite and the backend load the root file. Vite exposes only `VITE_` values to the browser. API URLs must be HTTP(S) origins with no credentials, path, or query. Restart services after configuration changes. The Vite dev server uses a strict port so a port change cannot silently invalidate CORS settings.

### Enable accounts

Follow the [Supabase setup guide](supabase/README.md): create a development project, apply the migration, configure email redirects, and add its URL/publishable key to the root `.env`. Restart both services, then open [sign-in](http://127.0.0.1:5173/login) or [registration](http://127.0.0.1:5173/register). No service-role key is needed. Administrator roles are assigned only through trusted SQL.

### Docker alternative

With Docker and Compose available:

```bash
docker compose up --build
# Stop and remove the local containers later:
docker compose down
```

This builds the static frontend and API and binds them to loopback at ports 5173 and 8000. PostgreSQL and Supabase still require setup. The optional `inference` profile runs the worker after its dedicated credentials and trusted model are configured; see the [worker guide](docs/INFERENCE.md). `VITE_API_BASE_URL` is a build-time browser URL; changing it requires rebuilding the frontend. This Compose configuration is for local development, not public deployment.

### Checks

From the root, after backend installation:

```bash
backend/.venv/bin/pytest backend/tests -q
backend/.venv/bin/ruff check backend
backend/.venv/bin/ruff format --check backend
cd frontend
npm run lint
npm test
npm run build
```

Browser integration tests start the API and Vite automatically (on macOS/Linux):

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

Tests cover real browser-to-API connectivity and desktop/mobile navigation. Account tests use the real Supabase client with mocked provider responses, including PKCE confirmation/recovery, persistence, sign-out, and denied admin access. They use a separate frontend on port 5174. CI checks SQL authorization and transactional telemetry behavior on disposable PostgreSQL: concurrent retries, conflicts/rollback, pagination, late source records, and retention. It also builds/smoke-tests Compose services. Hosted authentication and event coverage remain separate verification steps. Windows users can use browser checks through WSL or CI.

### Troubleshooting

- **API unavailable:** start terminal 1, open `/healthz`, check `VITE_API_BASE_URL` and `ALLOWED_ORIGINS`, then select **Check again**.
- **Port already in use:** stop the conflicting process, or update the frontend/API ports and corresponding environment configuration together.
- **Imports fail:** run the editable install command after installing the locked dependencies; do not use a globally installed uvicorn.
- **Supabase not configured:** follow the project setup guide; both services need the same project URL and publishable key. Apply the migrations and restart both services. Reproduce offline training or configure a locally trusted model before enabling the separate worker.

## License

[MIT](LICENSE).
