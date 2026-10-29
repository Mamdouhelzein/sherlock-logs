# Contributing

Sherlock Logs has a runnable application foundation. See ROADMAP.md for upcoming authentication and detection work.

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

See README.md for installation and check commands. Run backend pytest/Ruff checks and frontend lint, tests, and build before pushing. Use `npm exec prettier -- --write src` inside `frontend` to format UI source. CI runs these checks plus browser integration and container smoke tests.

Runtime backend packages are pinned with hashes in `backend/requirements.lock`; development packages are pinned in `backend/requirements-dev.lock`. Frontend packages use `frontend/package-lock.json`. When changing backend dependencies, update pyproject.toml and regenerate the locks with pip-compile (runtime first, then development with `--constraint requirements.lock --extra dev --strip-extras`). Do not edit generated version pins without resolving and checking the resulting environment.
