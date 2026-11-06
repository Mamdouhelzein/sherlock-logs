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

Steps 5 and 6 are implemented: seeded events, separate labels, causal features, rule/statistical baselines, and trained Isolation Forest experiments. The separate [background worker](../docs/INFERENCE.md) uses the frozen model to score collected development login events in shadow mode. It does not block authentication. See the original [model card](reports/iforest-v1.md) and the later [stress evaluation](reports/stress-v1.md), which fails the false-alert operating checks. Hugging Face publication remains optional.

## Reproduce step 5

Use Python 3.12+ from the repository root for generation/features/baselines. These preparation commands use only the standard library; training adds separate scientific dependencies. No experiment command loads `.env`, makes network requests, uses production credentials, or writes to Supabase. Generated data/artifacts stay in Git-ignored directories. No login attempts are sent to any website.

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

Order is `(occurred_at, event_id)`, including deterministic ties. Windows exclude their left boundary, and state updates after the current snapshot. Cold starts use zero history/deviation/novelty/gap plus explicit flags. Missing accounts/sources do not share a catch-all history. Browser family is not device identity. The later stress suite rebuilds features under three paired observation contracts; actual provider field-loss rates remain unmeasured. Offline experiment commands stay isolated from the separately configured live worker.

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

See [actual baseline results and limitations](reports/baseline-v1.md). Step 6 now compares detectors under a common validation false-alert cap and records inference latency separately from time to alert. Trusted failure capture and deterministic per-account protection have separate implementations and coverage limits; see the [failed-login adapter](../docs/FAILED_LOGINS.md) and [free local Auth realm](../docs/FREE_AUTH.md). Synthetic results cannot establish real-world effectiveness.

## Train and evaluate Isolation Forest

Create a separate environment with Python 3.13; the running API does not need ML dependencies:

```sh
python3 -m venv ml/.venv
ml/.venv/bin/python -m pip install --require-hashes --only-binary=:all: -r ml/requirements.lock
PYTHONPATH=ml/src ml/.venv/bin/python -m sherlock_ml train \
  --dataset data/generated/seed-42 --features artifacts/baselines/seed-42/features \
  --output artifacts/models/iforest-v1
```

The preset search compares 200-tree forests with 128/256/512 samples per tree, seed 42, and single-process fitting. CLI parameters can change these settings. `fit_experiment` accepts training features, validation features, and validation labels only, with no training labels or test inputs. It keeps all training events and casts the 15 numeric features to float32 without a fitted scaler. Candidates rank by validation episode recall, event recall, fewer false alerts, then smaller sample size. Test metrics never enter selection. Scores are `-IsolationForest.score_samples`; higher means more unusual, not a probability of compromise.

Continuous rule scores use the strongest normalized count/hour signal. ML, rule scores, and statistics each calibrate to the same validation false-alert cap. Discrete rules can use less of that budget. The combined OR detector gives each branch half the cap so it cannot double the validation budget. Original fixed rules remain a reference. The cap is not guaranteed on later traffic.

Outputs include `model.joblib`, `metadata.json`, `experiment.json`, `feature_schema.json`, `selection.json`, `metrics.json`, `examples.json`, `predictions.csv`, and `latency.json`. Metadata records versions, seeds, dates, dataset/feature hashes, model ID, code hashes, and provenance. Error examples contain observed features, not causal feature attributions. Latency measures warm in-process ML inference only, excluding feature extraction, I/O, and scheduling.

Reuse a frozen artifact without fitting or recalibration:

```sh
PYTHONPATH=ml/src ml/.venv/bin/python -m sherlock_ml evaluate \
  --dataset data/generated/seed-43 --features artifacts/baselines/seed-43/features \
  --artifact artifacts/models/iforest-v1 --trust-local-artifact \
  --output artifacts/models/iforest-v1-seed-43
```

`--trust-local-artifact` is required because **joblib loading can execute code**. Only load artifacts you created or fully trust. Hashes detect corruption, not malicious replacement of both a model and manifest. Dependency versions, Python major/minor, feature schema/order/code, and hashes are checked before deserialization. There is no model upload or HTTP loading endpoint. Binaries stay Git-ignored; a fresh clone must reproduce training locally.

To reproduce the fresh-seed evaluation, generate seed 44 with defaults, extract features into a new directory, and evaluate the same artifact with new output paths. See the [model card](reports/iforest-v1.md) for actual results on all three datasets. The background inference worker is configured separately; these offline commands do not activate it or replace its pinned artifact.

## Frozen-model stress evaluation

The independently implemented [stress protocol](../docs/ML_STRESS_PROTOCOL.md) was committed before inspecting its full results. It evaluates six workloads, three fresh seeds and three paired observation contracts without fitting or changing thresholds. Events and labels are separate; features use only visible prior observations. Unknown-account attempts absent from the local hook count as unalerted attacks in end-to-end recall, not safe classifications.

```sh
PYTHONPATH=ml/src ml/.venv/bin/python -m sherlock_ml.stress \
  --artifact artifacts/models/iforest-v1 \
  --expected-model-version deafc493f2d8f5507885534f2bfc3ddb09f3ccd171104c0968deec7519f0ea7c \
  --trust-local-artifact \
  --output artifacts/evaluations/stress-v1-20261106
```

The explicit pin above identifies the evaluated v1 bundle; deliberately reproduced replacement bundles require their own verified pin. Keep output paths fresh. Exit code zero means evaluation completed; consult `operating_checks.passed` for the diagnostic outcome. Full generated rows and predictions stay ignored. [Published aggregate results](reports/stress-v1.md) show excess benign alerts under legitimate bursts and gaps on evasive attacks. The current model remains in shadow mode, with no retraining or automatic ML blocking. Any candidate selected using these findings needs a newly reserved evaluation set.

## Development checks

Install the separate hash-locked training/test environment:

```sh
ml/.venv/bin/python -m pip install --require-hashes --only-binary=:all: -r ml/requirements-dev.lock
ml/.venv/bin/ruff check ml
ml/.venv/bin/ruff format --check ml
PYTHONPATH=ml/src ml/.venv/bin/python -m pytest ml/tests -q
```

CI has a dedicated ML job covering the preparation checks plus actual fitting, ignored training/test labels, test-feature isolation, combined validation budgets, reproducible selection, artifact round trips, rejection before untrusted/incompatible loading, and frozen evaluation without fitting. Locks pin exact versions and official release hashes; use `pip-compile --generate-hashes` with the corresponding `.in` file when intentionally updating dependencies.
