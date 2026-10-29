# Backend

FastAPI application foundation. No authentication, database connection, telemetry ingestion, or detection worker is active yet.

## Run

Follow the repository-root README to create `backend/.venv`, install the development lock, install this package in editable mode, and start `sherlock_api.main:app` on port 8000. Python 3.12+ is supported; 3.13 is recommended and used by CI and Docker.

## Endpoints

| Method | Path | Meaning |
| --- | --- | --- |
| GET | `/healthz` | Process liveness and service version |
| GET | `/api/v1/system` | Current check timestamp, uptime, version, and unconfigured integrations |
| GET | `/docs` | Interactive API documentation in development/test |

A healthy process does not establish database or model readiness. Current status endpoints expose no authentication data and require no credentials. CORS is not authorization. Protected endpoints and JWT verification will be implemented with authentication.

## Configuration

Settings read environment variables and the optional repository-root `.env`:

- `ENVIRONMENT`: development (default), test, or production.
- `ALLOWED_ORIGINS`: explicit comma-separated HTTP(S) origins. Defaults include localhost and 127.0.0.1 on port 5173. Paths, wildcard origins, and embedded credentials are rejected.

Production mode requires HTTPS origins and disables developer documentation. Public deployment also needs the later security controls and deployment work; changing this flag alone is insufficient. Responses are non-cacheable and use a nosniff header.

## Checks

From the repository root:

```bash
backend/.venv/bin/pytest backend/tests -q
backend/.venv/bin/ruff check backend
backend/.venv/bin/ruff format --check backend
```

Use the corresponding Scripts executables on Windows. Runtime dependencies are pinned with hashes; development dependencies are pinned separately and constrained to those runtime versions.

## Next responsibilities

Trusted ingestion, durable pending-event processing, shared historical features, versioned inference, and incident grouping will be added after identity and telemetry coverage are established. Model unavailability must never break authentication.
