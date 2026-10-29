# Sherlock Logs

**The case of the suspicious sign-in.**

An ML-powered website security monitoring project that learns login behavior, flags unusual activity, and helps administrators investigate suspicious sign-ins.

## Status

Step 2: runnable application foundation. A React workspace connects to FastAPI and displays real connection status, recovery guidance, architecture, and local startup instructions. Backend, frontend, browser integration, and container checks are configured in GitHub Actions.

Authentication, event collection, storage, security detection, and model training are not implemented yet. The interface does not display fabricated login activity or detection results. No Supabase credentials are required to run this release.

## Project guide

- [Architecture](ARCHITECTURE.md): components, event flow, and access boundaries.
- [Roadmap](ROADMAP.md): implementation milestones and acceptance criteria.
- [Contributing](CONTRIBUTING.md): development and review conventions.
- [Security](SECURITY.md): reporting guidance and operational boundaries.
- [Frontend](frontend/README.md): React setup, UI structure, and checks.
- [Backend](backend/README.md): API configuration, endpoints, and checks.
- [ML](ml/README.md): training and evaluation protocol.
- [Supabase](supabase/README.md): schema and access-policy plan.

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

- Registration, login, and protected account pages.
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
- [ ] Configure Supabase Auth, database migrations, and access policies.
- [ ] Verify authentication event coverage and implement trusted ingestion.
- [ ] Build synthetic normal activity and local attack scenarios.
- [ ] Implement historical features and security-rule baselines.
- [ ] Train, validate, and evaluate the anomaly detector.
- [ ] Add durable background scoring and incident grouping.
- [ ] Build the security dashboard and investigation timeline.
- [ ] Add automated checks, benchmark results, and a recorded demo.

## Security boundaries

Planned authentication and rate-limiting controls will operate independently of ML. The first detection release will generate investigation alerts rather than automatically blocking accounts. The current foundation release has no authentication or event ingestion routes and is intended for local development.

Privileged Supabase credentials stay on the server. Database access policies and API authorization enforce administrator access. Passwords, access tokens, and raw session secrets must never enter event logs. Simulators run only against controlled development environments, and model artifacts must come from trusted training runs.

## Local setup

Clone the repository:

```bash
git clone https://github.com/Mamdouhelzein/sherlock-logs.git
cd sherlock-logs
```

The repository is private, so cloning requires account access. Use **Node.js 22.12+ (24 recommended)** and **Python 3.12+ (3.13 recommended)**.

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

Open [the workspace](http://127.0.0.1:5173). It should show **API reachable** after the request completes. Use **Check again** to refresh; the connection status reflects the last manual check, not a continuous monitor.

- [Liveness](http://127.0.0.1:8000/healthz): process status, not database/model readiness.
- [System status](http://127.0.0.1:8000/api/v1/system): version, check time, uptime, and explicitly unconfigured integrations.
- [Interactive API docs](http://127.0.0.1:8000/docs): available in development/test environments.

Optional: copy `.env.example` to `.env` in the root and change the API origin or allowed frontend origins. Both Vite and the backend load the root file. Vite exposes only `VITE_` values to the browser. API URLs must be HTTP(S) origins with no credentials, path, or query. Restart services after configuration changes. The Vite dev server uses a strict port so a port change cannot silently invalidate CORS settings.

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

Tests cover real browser-to-API connectivity, desktop/mobile navigation and deep links, plus unavailable-API recovery. CI also builds and smoke-tests the Compose services. Windows users can use the browser checks through WSL or CI; unit tests and manual startup work natively.

### Troubleshooting

- **API unavailable:** start terminal 1, open `/healthz`, check `VITE_API_BASE_URL` and `ALLOWED_ORIGINS`, then select **Check again**.
- **Port already in use:** stop the conflicting process, or update the frontend/API ports and corresponding environment configuration together.
- **Imports fail:** run the editable install command after installing the locked dependencies; do not use a globally installed uvicorn.
- **Supabase/ML marked unconfigured:** expected for this milestone. Setting future credential placeholders does not activate integrations.

## License

[MIT](LICENSE).
