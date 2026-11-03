# Offline datasets and detection baselines

## Objective

Test whether behavioral anomaly detection identifies suspicious login incidents beyond simple rules at a comparable false-alert rate.

## Features

Account failures, source attempts, and distinct accounts per source in preceding windows; browser familiarity; deviation from historical login hours; time since previous login; failure ratio; and available history count. Use prior events only, deterministic ordering, and explicit cold-start defaults. Do not input raw IDs, scenario labels, or future outcomes.

## Experimental protocol

1. Generate approximately 200 fictional users over 90 days, with configurable habits and seeds.
2. Include normal mistakes, new browsers, and legitimate schedule changes.
3. Keep scenario labels in evaluation-only metadata.
4. Use days 1-50 for training, 51-70 for validation, and 71-90 for final evaluation.
5. Fit preprocessing and Isolation Forest using training data only.
6. Tune thresholds on validation data against a false-alert budget.
7. Compare rules, a statistical baseline, Isolation Forest, and combined detection.
8. Evaluate fresh seeds and scenario variations without retuning on final test labels.

Report precision, recall, false alerts per 1,000 benign events, incident recall, time to alert, latency, and failure examples. Record attack prevalence and event-versus-incident label definitions so results are interpretable.

## Artifacts

Each trained release should contain `model.joblib`, `metadata.json`, `feature_schema.json`, and `metrics.json`. Record package versions, data configuration, feature version, seed, date ranges, and threshold. Generated artifacts belong outside Git; publish a model card with actual results when available.

Step 5 is implemented: seeded fictional events, separate labels, causal features, fixed configurable rules, and a robust statistical baseline. **No Isolation Forest model has been trained or connected to the app.** Hugging Face publication is optional after reproducible training exists.

## Reproduce step 5

Use Python 3.12+ from the repository root. This package uses only the standard library; it does not load `.env`, make network requests, use production credentials, or write to Supabase. Generated data and artifacts stay in Git-ignored directories. No login attempts are sent to any website.

```sh
PYTHONPATH=ml/src python3 -m sherlock_ml generate \
  --seed 42 --output data/generated/seed-42
PYTHONPATH=ml/src python3 -m sherlock_ml features \
  --dataset data/generated/seed-42 --output artifacts/baselines/seed-42/features
PYTHONPATH=ml/src python3 -m sherlock_ml baseline \
  --dataset data/generated/seed-42 --features artifacts/baselines/seed-42/features \
  --false-alert-budget 5 --output artifacts/baselines/seed-42/results
```

Output directories must be new: existing experiments are never overwritten. Choose new names for reruns. `--help` lists parameters. Optional installation with `python3 -m pip install -e ml` exposes `sherlock-ml`.

Default generation uses 200 users over 90 days. Individual habits include daily activity probability, UTC login hours, browser family, home/shared office source, ordinary password mistakes, weekends, new browsers, travel-like source changes, and legitimate schedule changes. Attacks include brute force, password spraying with unknown accounts, and unusual successful logins. Both populations use ordinary browser strings and documentation-only IP ranges; raw IDs/addresses are excluded from model inputs. `--attack-episodes 0` creates a benign control. Seeds, dates, partition lengths, user counts, episode counts, and `--attack-scale` are configurable. The initial training period receives a small share of attacks without label-based filtering.

| File | Contents |
| --- | --- |
| `events.jsonl` | Observable telemetry fields, no passwords/emails/labels |
| `labels.jsonl` | Event ID, attack flag, scenario, evaluation-only episode ID |
| `manifest.json` | Version, full config, counts, chronological ranges, SHA-256 hashes |
| `features.csv` | ID/time join metadata, followed by ordered numeric features |
| `feature_schema.json` | Feature allowlist/version and dataset/feature hashes |
| `baseline.json` | Safe JSON statistical parameters, threshold, rules, calibration provenance |
| `metrics.json` | Split metrics, confusion counts, scenario breakdowns, error-example IDs |

`Snapshot.vector()` is the exclusive numeric input boundary: it enforces feature names and finite values. IDs/time are metadata only. The feature builder accepts no scenario fields. Hash checks catch accidental edits/mix-ups, not malicious forgery.

The 15 features cover current failure status; preceding account failures/attempts over 15 minutes; source attempts, distinct accounts, and failure ratio over 5 minutes; account history/successes over 30 days; browser novelty relative to prior successful browser families; circular deviation from past successful UTC hours; previous-event gap/history availability; and account/source/browser missing-context flags.

Order is `(occurred_at, event_id)`, including deterministic ties. Windows exclude their left boundary, and state updates after the current snapshot. Cold starts use zero history/deviation/novelty/gap plus explicit flags. Missing accounts/sources do not share a catch-all history. Browser family is not device identity. Context-loss behavior is tested but real provider-specific loss rates are not simulated. This is offline code; no live feature worker is running.

The statistical baseline fits medians and median absolute deviations on training features only, with a unit scale floor. Its score is the maximum positive standardized deviation across account failures, source attempts/accounts, and hour deviation. Calibration uses benign validation scores only; `score > threshold` handles ties conservatively. The validation budget is not guaranteed on later traffic. Rules have fixed configurable thresholds and are not optimized to that budget.

Earlier validation/test events may enter later history as they would online; their labels never do. Successful malicious logins can contaminate history. Episode recall means any alert within a generator-labeled episode; time to alert starts at its first event. This does not implement runtime incident grouping. Undefined metrics are JSON `null`.

Evaluate another seed with smaller bursts using frozen first-run parameters and rules:

```sh
PYTHONPATH=ml/src python3 -m sherlock_ml generate \
  --seed 43 --attack-scale 0.6 --output data/generated/seed-43
PYTHONPATH=ml/src python3 -m sherlock_ml features \
  --dataset data/generated/seed-43 --output artifacts/baselines/seed-43/features
PYTHONPATH=ml/src python3 -m sherlock_ml baseline \
  --dataset data/generated/seed-43 --features artifacts/baselines/seed-43/features \
  --reference artifacts/baselines/seed-42/results/baseline.json \
  --output artifacts/baselines/seed-43/results
```

See [actual baseline results and limitations](reports/baseline-v1.md). Step 6 will compare rules-only, ML-only, and combined detection at comparable false-alert budgets. Record actual latency in that experiment; offline time to alert is not processing latency. Real failed-login capture and per-account protection remain separate unfinished security tasks. Synthetic results cannot establish real-world effectiveness.

## Development checks

Reuse the backend development lockfile's tools:

```sh
backend/.venv/bin/ruff check ml
backend/.venv/bin/ruff format --check ml
PYTHONPATH=ml/src backend/.venv/bin/python -m pytest ml/tests -q
```

CI covers seed/byte reproducibility, scenario coverage, account isolation, time windows, midnight, missing context, ties, future-data leakage, test-label/feature isolation from fitting/calibration, frozen references, hashes, and the CLI pipeline.
