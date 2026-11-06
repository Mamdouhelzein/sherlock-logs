# Local-observation candidate v2: not selected for activation

Trained and evaluated 2026-11-06. **Reject this candidate for activation.** It reduces benign alerts substantially but loses too much attack detection. The running v1 model and deterministic password cooldown are unchanged. This is a completed synthetic candidate experiment, not an approved model upgrade.

The [protocol](../../docs/ML_CANDIDATE_PROTOCOL.md), generator, pipeline and tests were fixed in [`328753d`](https://github.com/Mamdouhelzein/sherlock-logs/commit/328753d5e9b84e5b6c1fcade31b19ebf80421f0a) before fitting. The selected model, thresholds and [validation aggregates](local-v2-training.json) were frozen in [`eb074ba`](https://github.com/Mamdouhelzein/sherlock-logs/commit/eb074ba7af1fbfa519d8767f4b964f7d85ec189c) before generating the reserved holdout. [Final aggregate JSON](local-v2.json) includes all detector metrics, per-seed checks, scenario counts and fingerprints. Raw generated events, predictions and weights stay Git-ignored.

## What changed

The [previous stress evaluation](stress-v1.md) became development evidence. A new synthetic generator adds multiple ordinary sessions per day, shared office login waves, repeated stale-password/cooldown retries, new accounts and schedule changes. It generates directly for the local observation contract: known account IDs and outcomes, without IP/browser context; unknown-account failures are removed before feature extraction. Labels and episode IDs remain evaluation metadata.

Training retains every measured row from three intentionally benign control workloads, with no training-label filtering. It fits the unchanged 15-feature `login-history-v1` vector. There are 8,261 fitted training rows from seed 2201 and 18,630 observed validation rows from seed 2202, in separate populations and time periods. Each workload has 100 fictional accounts and 35 warm-up days before its 21-day measured period. Warm-up supplies history but is not fitted or counted in reported metrics.

The three candidates use 200 trees and max_samples 128, 256 or 512, with model seed 42 and float32 inputs. Each detector calibrates on benign validation scores separately for each workload; the maximum of those thresholds enforces the validation false-alert cap in every workload. Combined OR branches each receive half the cap. Grouped-calibrated ML macro episode recall, then event recall, fewer false alerts and smaller sample size select the 512-sample forest. Selection uses only observed validation episodes; final end-to-end metrics additionally include invisible attacks.

The candidate is `iforest-bc9ae015430df135`, bundle pin `5f45dcd4ab882c56f46fe5b967edef120a65e039f7549d104b38496eaed9ced7`. Thresholds are ML `0.7377886644135815`, rules `1.4`, statistics `8.116340818360154`; combined branches use ML `0.7450414034726139` and rules `1.6`. These are anomaly cutoffs, not probabilities of compromise.

All six validation workloads met the combined false-alert limit. Validation fast-guessing episode recall was 80.95%. These validation numbers selected a candidate; they did not establish generalization.

## Fresh holdout comparison

Reserved seeds 4401–4403 use different populations, broader benign timing/retry distributions, larger schedule shifts and variable attack sizes/spacings. The same generated stream is evaluated by both frozen models. No final fitting or recalibration is allowed. The 18 workload/seed cases contain 60,566 measured event instances, including 7,751 attack-labeled instances. Count events once per case, not once per compared model. Workloads share habits, burst events are correlated, and these are variants from the same new simulator.

Simulation coordinates are training August 5–26, validation October 6–27 and holdout December 6–27, 2026 UTC, with exclusive ends. Future dates are fictional simulation timestamps; these are not future traffic observations.

This table reports combined detection, pooled across three seeds. Recall counts hidden attack events/episodes as unalerted. False alerts use observed benign events only.

| Workload | v1 false alerts / 1,000 benign | Candidate false alerts / 1,000 benign | v1 episode recall | Candidate episode recall |
| --- | ---: | ---: | ---: | ---: |
| Routine | 0.27 | 0.00 | — | — |
| Legitimate bursts | 312.08 | 4.35 | — | — |
| Behavior changes | 30.87 | 0.00 | — | — |
| Fast guessing | 1.46 | 0.00 | 100.00% | 63.49% |
| Evasive attacks | 1.33 | 0.00 | 50.00% | 0.00% |
| Mixed traffic | 370.07 | 4.51 | 62.86% | 15.87% |

Legitimate bursts produce 48 candidate false alerts versus 3,440 v1 false alerts among the same 11,023 benign events. Mixed traffic produces 50 versus 4,103 among 11,087 benign events. This is a substantial alert-volume reduction, accompanied by a substantial detection regression. Since training data, observation calibration and weights changed together, the experiment cannot attribute that reduction to retraining alone.

The candidate detects only 40/63 fast-guessing episodes versus v1's 63/63, and 108/616 attack events versus 513/616. Candidate fast-episode recall is 61.90%, 57.14% and 71.43% by seed, all below the required 80%. Its median event-time alert delays for detected episodes are 207, 145.5 and 120 seconds, excluding collector/worker/dashboard latency. Undetected episodes are excluded from those delays; the delay is not a detection guarantee.

In the evasive workload the candidate combined detector alerts on zero of 3,263 attack events. The existing model alerts on 1,234: 639/652 slow-guessing events and 595/1,288 distributed-spray events. Neither alerts on the 63 familiar-credential misuse events. All 1,260 unknown-account attack events in this workload are invisible under the local contract. Missing telemetry cannot be fixed by model training, and a known-credential login can resemble an ordinary session.

## Acceptance checks and baselines

**The candidate fails all three fast-guessing recall checks and two of 18 false-alert checks.** Seed 4403 produces 5.17 false alerts per 1,000 benign events for legitimate bursts and 6.21 for mixed traffic, exceeding the limit of 5. Pooled averages below 5 do not override these failures. The existing model fails nine false-alert checks but passes fast-guessing recall; neither model satisfies the entire protocol.

Candidate baselines use the same benign validation workload caps. This is a common calibration target, not equal realized holdout false-alert rates.

| Candidate detector | Benign-burst false alerts / 1,000 | Fast episode recall | Evasive episode recall | Mixed false alerts / 1,000 | Mixed episode recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| ML | 5.53 | 61.90% | 0.00% | 6.67 | 16.51% |
| Calibrated rules | 5.72 | 68.25% | 0.00% | 4.24 | 14.92% |
| Statistics | 3.72 | 55.56% | 22.62% | 44.74 | 34.60% |
| Combined | 4.35 | 63.49% | 0.00% | 4.51 | 15.87% |

The stricter combined branch cutoffs differ from standalone ML/rules. The statistical baseline catches some evasive episodes but produces many false alerts in mixed traffic. There is no evidence here that ML delivers the best usable operating point.

## Interpretation and next work

Ordinary password-manager retries and malicious guessing can present similar account/outcome sequences. This synthetic experiment is consistent with an ambiguity in the available signals; it does not prove a fundamental impossibility or establish causal feature explanations. Raising anomaly thresholds to accommodate broader benign behavior loses attacks as well. The independent provider cooldown still applies to repeated incorrect passwords regardless of the ML score.

This data is entirely fictional. Attack prevalence is artificial, precision depends on that prevalence, and validation has only one seed. The generator does not execute the full Auth state machine, simulate every concurrent cooldown/session interaction, or reproduce delayed delivery, outages or retention loss. It cannot measure real-world accuracy or password-guard enforcement. Unknown-account misses and familiar-credential limits remain explicit even when a detector reports zero benign alerts.

Do not tune again against these now-inspected final seeds. The next useful model iteration needs better evidence: reviewable labeled behavior from a controlled test application, measured event coverage/context, and a new reserved evaluation set. Any feature/schema change or new artifact must be evaluated separately before shadow activation. This candidate remains an offline comparison artifact; no automatic ML blocking, model replacement, role change or external traffic test was performed.

## Reproduce and verify

Use the hash-locked ML environment and the code revision above. Reproduce the trusted [v1 bundle](../README.md) first. From the repository root:

```sh
PYTHONPATH=ml/src ml/.venv/bin/python -m sherlock_ml.candidate train \
  --output artifacts/candidates/local-v2

PYTHONPATH=ml/src ml/.venv/bin/python -m sherlock_ml.candidate evaluate \
  --candidate artifacts/candidates/local-v2/model \
  --reference artifacts/models/iforest-v1 \
  --candidate-pin 5f45dcd4ab882c56f46fe5b967edef120a65e039f7549d104b38496eaed9ced7 \
  --reference-pin deafc493f2d8f5507885534f2bfc3ddb09f3ccd171104c0968deec7519f0ea7c \
  --trust-local-artifact \
  --output artifacts/evaluations/local-v2-holdout
```

Use fresh output paths. A deliberately regenerated bundle with a different fingerprint requires its own verified pin. Explicit trust is required because joblib can execute code. Final evaluation checks pins/compatibility, refuses changed generator/evaluator code and overlapping dates, then verifies both bundles' bytes remain unchanged. Exit code zero means execution succeeded; inspect the diagnostic `operating_checks` to assess acceptance.

All 63 ML tests pass locally, with lint and formatting clean. Checks include reserved-seed/phase separation, training-label independence, grouped validation budgets, selected-candidate ordering, trusted/pinned loading, unchanged artifact bytes, hidden attacks, and final evaluation with fitting/calibration disabled. [GitHub CI for the pipeline](https://github.com/Mamdouhelzein/sherlock-logs/actions/runs/42247224487) passed. The published JSON preserves the original detailed report hash plus dataset, code and artifact fingerprints.
