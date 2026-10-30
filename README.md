# Sherlock Logs

**The case of the suspicious sign-in.**

An ML-powered website security monitoring project that learns login behavior, flags unusual activity, and helps administrators investigate suspicious sign-ins.

## Status

Step 3: identity and access integration. React now includes registration, login, email confirmation, password recovery, private profiles, sign-out, and administrator checks. FastAPI verifies sessions through Supabase Auth and reads current roles from a restricted database helper. A SQL migration supplies profile isolation and trusted role assignments.

A hosted Supabase project still needs to be created and configured using the [setup guide](supabase/README.md). Until then, public pages work and account forms explain the missing configuration. Event collection, security detection, and model training remain planned; the interface does not display fabricated activity or results.

## Project guide

- [Architecture](ARCHITECTURE.md): components, event flow, and access boundaries.
- [Roadmap](ROADMAP.md): implementation milestones and acceptance criteria.
- [Contributing](CONTRIBUTING.md): development and review conventions.
- [Security](SECURITY.md): reporting guidance and operational boundaries.
- [Frontend](frontend/README.md): React setup, UI structure, and checks.
- [Backend](backend/README.md): API configuration, endpoints, and checks.
- [ML](ml/README.md): training and evaluation protocol.
- [Supabase](supabase/README.md): project creation, migration, email setup, and administrator assignment.

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
- [ ] Provision Supabase and verify hosted sign-in, recovery, and rate limits.
- [ ] Verify authentication event coverage and implement trusted ingestion.
- [ ] Build synthetic normal activity and local attack scenarios.
- [ ] Implement historical features and security-rule baselines.
- [ ] Train, validate, and evaluate the anomaly detector.
- [ ] Add durable background scoring and incident grouping.
- [ ] Build the security dashboard and investigation timeline.
- [ ] Add automated checks, benchmark results, and a recorded demo.

## Security boundaries

Authentication controls operate independently of ML. Protected API routes validate the bearer token with Supabase, then read the caller's current role from SQL. Browser guards are navigation conveniences; API authorization and RLS enforce access. The first detection release will generate investigation alerts rather than automatically blocking accounts. Event ingestion is not implemented.

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

Open [the workspace](http://127.0.0.1:5173). It should show **API reachable** after the request completes. Use **Check again** to refresh; the connection status reflects the last manual check, not a continuous monitor. Use the navigation search button or **Ctrl/Cmd + K** to jump between pages. Decorative radar motion can be paused with **Ambient effects**, and reduced-motion preferences are respected. The radar is an architecture illustration, not login telemetry.

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

This builds the static frontend and API and binds them to loopback at ports 5173 and 8000. No PostgreSQL, Supabase, or ML worker is provisioned yet. `VITE_API_BASE_URL` is a build-time browser URL; changing it requires rebuilding the frontend. This Compose configuration is for local development, not public deployment.

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

Tests cover real browser-to-API connectivity and desktop/mobile navigation. Account tests use the real Supabase client with mocked provider responses, including PKCE confirmation/recovery, persistence, sign-out, and denied admin access. They use a separate frontend on port 5174. CI also checks SQL authorization on disposable PostgreSQL and builds/smoke-tests Compose services. Hosted email and rate-limit verification remains a separate setup step. Windows users can use browser checks through WSL or CI.

### Troubleshooting

- **API unavailable:** start terminal 1, open `/healthz`, check `VITE_API_BASE_URL` and `ALLOWED_ORIGINS`, then select **Check again**.
- **Port already in use:** stop the conflicting process, or update the frontend/API ports and corresponding environment configuration together.
- **Imports fail:** run the editable install command after installing the locked dependencies; do not use a globally installed uvicorn.
- **Supabase not configured:** follow the project setup guide; both services need the same project URL and publishable key. Apply the migration and restart both services. ML remains untrained.

## License

[MIT](LICENSE).
