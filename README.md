# Sherlock Logs

**The case of the suspicious sign-in.**

An ML-powered website security monitoring project that learns login behavior, flags unusual activity, and helps administrators investigate suspicious sign-ins.

## Status

Repository foundation. Architecture, roadmap, contribution guidance, and configuration examples are included. The application is not yet implemented or benchmarked.

## Project guide

- [Architecture](ARCHITECTURE.md): components, event flow, and access boundaries.
- [Roadmap](ROADMAP.md): implementation milestones and acceptance criteria.
- [Contributing](CONTRIBUTING.md): development and review conventions.
- [Security](SECURITY.md): reporting guidance and operational boundaries.
- [Frontend](frontend/README.md): React application plan.
- [Backend](backend/README.md): API and worker plan.
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

## Planned stack

| Component | Technology |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| UI | Tailwind CSS, shadcn/ui, Recharts |
| Authentication and database | Supabase Auth and PostgreSQL |
| Custom API | Python and FastAPI |
| Detection | Python background worker |
| Machine learning | pandas, NumPy, scikit-learn, Isolation Forest |
| Testing | pytest, Vitest, Playwright |
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

- [ ] Scaffold frontend, API, and local development services.
- [ ] Configure Supabase Auth, database migrations, and access policies.
- [ ] Verify authentication event coverage and implement trusted ingestion.
- [ ] Build synthetic normal activity and local attack scenarios.
- [ ] Implement historical features and security-rule baselines.
- [ ] Train, validate, and evaluate the anomaly detector.
- [ ] Add durable background scoring and incident grouping.
- [ ] Build the security dashboard and investigation timeline.
- [ ] Add automated checks, benchmark results, and a recorded demo.

## Security boundaries

Established authentication and rate-limiting controls operate independently of ML. The first release generates investigation alerts rather than automatically blocking accounts.

Privileged Supabase credentials stay on the server. Database access policies and API authorization enforce administrator access. Passwords, access tokens, and raw session secrets must never enter event logs. Simulators run only against controlled development environments, and model artifacts must come from trusted training runs.

## Local setup

Clone the repository:

```bash
git clone https://github.com/Mamdouhelzein/sherlock-logs.git
cd sherlock-logs
```

The repository is private initially, so cloning requires account access. Review `.env.example` for planned configuration. Install and startup commands will be added with the first runnable implementation; dependency manifests and Docker services are not present yet.

## License

[MIT](LICENSE).
