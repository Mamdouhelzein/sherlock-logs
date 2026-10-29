# Security

## Project status

This is a development and portfolio project. No production security guarantees or real-world detection effectiveness have been established.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting feature if it is enabled for this repository. Otherwise contact the maintainer through an existing private channel to arrange a report. Do not post credentials, private logs, exploit details, or affected personal data in public issues. A dedicated reporting channel will be documented before any public production release.

## Design requirements

- Enforce authentication and authorization independently of ML scoring.
- Keep Supabase privileged credentials on trusted servers.
- Apply explicit grants and RLS to database objects exposed to clients.
- Never log passwords, access tokens, or raw session secrets.
- Bound input lengths and reject malformed ingestion records.
- Treat device identifiers and unverified forwarding headers as untrusted.
- Restrict investigation data and record administrator changes.
- Define retention and deletion for IP addresses and other sensitive telemetry.
- Load serialized model artifacts only from our trusted training pipeline.
- Run simulators solely in controlled development environments.

The initial model produces investigation alerts. It does not automatically lock accounts. Unusual behavior is not proof of compromise, and an anomaly score is not a calibrated attack probability.
