# Contributing

Sherlock Logs is at the repository-foundation stage. See ROADMAP.md for planned implementation work.

## Workflow

1. Create a focused branch from `main`.
2. Describe the behavior or experiment being changed.
3. Keep changes scoped and document configuration changes.
4. Run relevant checks once executable components exist.
5. Open a pull request describing the result, validation, and known limitations.

Do not commit real credentials, private login logs, generated datasets, or untrusted serialized model files. Commit environment variable names through example files only.

## Engineering conventions

Use TypeScript for frontend code and Python for backend and ML code. Keep feature generation shared between training and inference. Use UTC, stable event IDs, explicit access checks, and retry-safe background work.

Tests should verify authorization, chronological features, ingestion validation, and meaningful application behavior. Include source data configuration and random seeds with experiments. Evaluate on held-out data and report failed hypotheses as well as improvements.

Dependency manifests, formatter configuration, and exact check commands will arrive with the implementation. No automated tests or CI pipeline are claimed by this initial scaffold.
