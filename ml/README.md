# Machine learning

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

Status: no dataset, trained model, or benchmark is included yet. Hugging Face publication is optional after a reproducible model exists.
