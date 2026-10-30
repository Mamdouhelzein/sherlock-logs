# Backend

FastAPI system endpoints, Supabase identity verification, private event storage, signed service ingestion, and audit collection. Hosted setup and coverage verification are pending. The detection worker remains planned.

## Run

Follow the repository-root README to create `backend/.venv`, install the development lock, install this package in editable mode, and start `sherlock_api.main:app` on port 8000. Python 3.12+ is supported; 3.13 is recommended and used by CI and Docker.

## Endpoints

| Method | Path | Meaning |
| --- | --- | --- |
| GET | `/healthz` | Process liveness and service version |
| GET | `/api/v1/system` | Current check timestamp, uptime, version, and unconfigured integrations |
| GET | `/docs` | Interactive API documentation in development/test |
| GET | `/api/v1/me` | Verified confirmed-account identity and current database role |
| GET | `/api/v1/admin/status` | Requires a verified account with a current admin assignment |
| POST | `/api/v1/internal/events` | Service-signed, bounded event batches; user/admin bearer tokens cannot ingest |
| GET | `/api/v1/admin/events` | Administrator-only event reads with bounded keyset pagination |

A healthy process does not establish database or model readiness. Status endpoints are public; account/admin endpoints require bearer authentication. CORS is not authorization. The server validates tokens through Supabase Auth, then reads roles from SQL using the same user token. Metadata never grants admin. Auth/Data API failures deny access. See the [Supabase setup guide](../supabase/README.md).

## Configuration

Settings read environment variables and the optional repository-root `.env`:

- `ENVIRONMENT`: development (default), test, or production.
- `ALLOWED_ORIGINS`: explicit comma-separated HTTP(S) origins. Defaults include localhost and 127.0.0.1 on port 5173. Paths, wildcard origins, and embedded credentials are rejected.
- `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`: configure both or neither. Only publishable keys are accepted. HTTPS is required except for local development. The application does not need a secret key or database password.
- `DATABASE_URL`: optional server-only event database connection. Use the dedicated ingest/read groups.
- `COLLECTOR_DATABASE_URL`: separate read-only Auth audit connection for the collector command.
- `INGESTION_SIGNING_KEY`: separate random service secret, at least 32 bytes. Required with the event database for HTTP ingestion.
- `EVENT_RETENTION_DAYS`: 1–365, default 30. Schedule the maintenance command for physical cleanup.

For telemetry roles, signatures, collection commands, coverage limits, and integration tests, read [the telemetry guide](../docs/TELEMETRY.md). Production database connections require `sslmode=verify-full` with the appropriate trusted root certificate. Event settings are optional and do not affect native Supabase sign-in.

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

Verify the hosted event sources and connect a trusted failed-login publisher. Durable pending-event processing, shared historical features, versioned inference, and incident grouping follow. Model unavailability must never break authentication.
