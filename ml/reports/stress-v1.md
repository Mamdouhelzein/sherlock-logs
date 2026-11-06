# Frozen-model stress evaluation v1

Evaluated 2026-11-06. **The existing detector fails the prespecified false-alert checks. Keep ML in shadow mode.** This run improves our evidence about the model; it does not improve or retrain the model. The deterministic password cooldown is independent and unchanged.

The [protocol](../../docs/ML_STRESS_PROTOCOL.md), generator, evaluator and tests were committed as `faf3ce562ecf6fb46e7ee8969d5bdce201aa3f3f` before inspecting these full results. [Aggregate JSON](stress-v1.json) includes all detector summaries, per-seed metrics, observation coverage, scenario counts, operating-check failures and fingerprints. Generated event/prediction rows and model weights remain local and ignored.

## What was tested

An independently implemented simulator creates six workloads on seeds 1101–1103: routine activity, legitimate bursts, behavior changes, fast guessing, evasive attacks and mixed traffic. Each uses 100 fictional accounts, July 1–August 5 for causal warm-up, then August 5–19, 2026 UTC for evaluation. These periods follow the original experiment. No real accounts, network requests or database reads are involved.

There are 18 generated seed/workload datasets and 54 paired evaluations across three observation views. The evaluation periods contain 31,484 event instances, including 5,124 attack-labeled instances, counted once per seed/workload rather than once per observation view. Workloads share background habits, views share events, and burst events are correlated; these counts are not independent statistical samples. Warm-up rows are excluded from reported evaluation metrics.

- **Complete:** optimistic generated account, source and browser facts.
- **Local guard:** known-account failures and successes with IP/browser removed; unknown-account failures are absent. This approximates the current hook's observation boundary.
- **Failure logs:** account/browser removed from failures, with generated IP optimistically retained; successes retain complete generated context. This is a sensitivity experiment, not a faithful reconstruction of every hosted field.

History is rebuilt from each visible stream, including its warm-up. Hidden events never enter model history. End-to-end attack recall counts invisible attacks as unalerted; false alerts use only observed benign events. The frozen Isolation Forest, calibrated rules, statistical baseline, combined detector and fixed-rule reference receive the same feature snapshots. No fitting or threshold calibration occurs.

## Combined detector results

Each false-alert cell pools counts across three seeds; JSON also provides each seed and its range. Episode recall is the fraction of labeled episodes with at least one alert. A dash means there were no attacks in that workload.

| Workload | False alerts / 1,000 benign: complete | Local guard | Failure logs | Local end-to-end attack-event recall | Local end-to-end episode recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| Routine | 8.09 | 0.00 | 138.35 | — | — |
| Legitimate bursts | 321.80 | 60.59 | 415.97 | — | — |
| Behavior changes | 30.95 | 3.23 | 164.62 | — | — |
| Fast guessing | 8.09 | 0.00 | 138.35 | 56.85% | 100.00% |
| Evasive attacks | 8.09 | 0.00 | 138.35 | 19.54% | 41.07% |
| Mixed traffic | 358.95 | 94.24 | 433.55 | 32.59% | 57.14% |

**Forty of 54 runs exceeded the combined detector's limit of 5 false alerts per 1,000 observed benign events.** All three local fast-guessing runs passed the separate 80% episode-recall minimum: 42/42 episodes detected, with a median event-time delay of 60 seconds in each seed. This excludes collection, processing and dashboard delay. Conditional detection delays say nothing about undetected episodes.

Benign local bursts caused 345 alerts among 5,694 observed benign events. Per-seed rates were 51.66–69.19 per 1,000. Behavior changes averaged 3.23 per 1,000 locally, but one seed reached 6.37 and failed the per-run limit. An aggregate average cannot override that failure.

The local evasive workload had 2,226 attack events: 435 alerted, including 353/504 slow-guessing events and 82/840 distributed-spray events. None of 42 familiar-credential misuse events alerted. All 840 unknown-account attack events were invisible to the local guard, and therefore unalerted, rather than successfully classified as safe. Familiar-credential misuse can resemble an ordinary successful login; its threat label alone cannot make it observable.

Missing fields materially change the measured results. The optimistic failure-log projection yields high attack recall alongside very high benign alert rates. Neither improved recall nor fewer alerts under a restricted view proves a better detector: losing observations can also remove both false alerts and attacks.

## Where ML adds value, and its cost

This comparison uses the local-guard view. Branch thresholds differ between standalone and combined detectors because combined detection allocates half the original validation budget to each branch; its output need not contain every standalone ML alert.

| Detector | Legitimate-burst false alerts / 1,000 benign | Fast-guessing episode recall | Evasive episode recall | Mixed false alerts / 1,000 benign | Mixed episode recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| Calibrated rules | 22.13 | 100.00% | 0.00% | 22.16 | 20.00% |
| Statistical baseline | 173.69 | 100.00% | 50.00% | 270.16 | 60.95% |
| Isolation Forest | 72.18 | 85.71% | 44.64% | 109.95 | 55.71% |
| Combined | 60.59 | 100.00% | 41.07% | 94.24 | 57.14% |
| Fixed-rule reference | 14.75 | 100.00% | 0.00% | 14.83 | 20.00% |

ML detects some evasive episodes missed by rules in this simulator, at the cost of more benign alerts. The statistical baseline has higher evasive recall but still more false alerts. None meets the false-alert target in the legitimate-burst workload. This experiment does not establish that ML is the best operational choice.

## Limits and next candidate

All labels are simulator assumptions. Attack prevalence is deliberately artificial, so precision in the JSON is specific to these workloads. Independent implementation reduces dependence on the original simulator but is still synthetic evidence, created with knowledge of the feature system. Observation contracts are not measured provider missing-field distributions, and this suite omits delayed/out-of-order delivery, outages and live retention effects. It evaluates telemetry and detection, not password-guard enforcement or successful account compromise.

Before choosing another model or threshold, reserve new evaluation scenarios and seeds. Use this now-inspected suite as development evidence, expand benign retry/shared-source/schedule-change examples in training and validation, and evaluate calibration for each supported observation contract. Compare simpler rules/statistics at the same validation budget. Improve trusted event coverage independently; model training cannot recover unknown-account events the feed never supplies. Real labeled data and measured operational behavior remain necessary before claims of deployment readiness. No candidate is selected or activated by this report.

## Reproduction and verification

First reproduce the trusted original bundle using the [ML guide](../README.md). The evaluated model is `iforest-027e70e789fd5e28`, feature version `login-history-v1`, with runtime bundle pin `deafc493f2d8f5507885534f2bfc3ddb09f3ccd171104c0968deec7519f0ea7c`.

```sh
PYTHONPATH=ml/src ml/.venv/bin/python -m sherlock_ml.stress \
  --artifact artifacts/models/iforest-v1 \
  --expected-model-version deafc493f2d8f5507885534f2bfc3ddb09f3ccd171104c0968deec7519f0ea7c \
  --trust-local-artifact \
  --output artifacts/evaluations/stress-v1-20261106
```

Use a new output directory for reruns. Only explicitly trust locally created model files; a checksum does not make an untrusted joblib safe. The command pins the bundle, checks date separation and compatibility before deserialization, and verifies artifact files remain unchanged. Successful execution returns exit code zero even when diagnostic operating checks fail; inspect `operating_checks.passed` in its report. The report timestamp and its resulting hash differ across reruns; the published JSON preserves this run's exact detailed-report hash and dataset/code/artifact fingerprints.

All 50 ML tests passed locally, including causal observation projection, hidden-event handling, label isolation, frozen evaluation with fitting/calibration disabled, pin compatibility and unchanged model bytes. Lint and formatting passed. [GitHub CI for the evaluation code](https://github.com/Mamdouhelzein/sherlock-logs/actions/runs/42244332715) also passed. The live model, authentication policy and user roles were unchanged.
