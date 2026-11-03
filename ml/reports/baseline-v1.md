# Synthetic baseline experiment v1

Run on 2026-11-03 with CPython 3.13, package 0.1.0, and feature schema `login-history-v1`. These are actual offline outputs, not production measurements or ML model results. Reproduce with the [ML guide](../README.md).

Seed 42: 200 users, 90 days, 90 attack episodes, 16,485 events, 1,524 attack-labeled events. Training has 8,394 events with 149 attacks (1.78% contamination); labels were not used to filter fitting data. Validation has 3,996 events. Evaluation has 4,095 with 688 attacks (16.80% prevalence).

Training is 2026-01-05 through 2026-02-24; validation ends 2026-03-16; evaluation ends 2026-04-05. All ranges use UTC, inclusive starts, and exclusive ends. The statistical threshold `3.488227067235486` was chosen on benign validation events at a budget of 5 false alerts per 1,000; observed validation false alerts were 4.84. Rule defaults were fixed, not tuned to that budget, so this is not a matched-budget ML comparison.

| Evaluation run | Detector | Precision | Event recall | False alerts / 1,000 benign | Episode recall | Median time to alert |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Seed 42 | Fixed rules | 100.00% | 76.31% | 0.00 | 87.18% | 60 s |
| Seed 42 | Robust statistics | 95.36% | 95.64% | 9.39 | 100.00% | 0 s |
| Seed 43, burst scale 0.6 | Fixed rules, frozen | 100.00% | 57.98% | 0.00 | 85.71% | 50.5 s |
| Seed 43, burst scale 0.6 | Robust statistics, frozen | 88.33% | 90.68% | 18.76 | 100.00% | 0 s |

Seed 43 generated 15,861 events, including 912 attack-labeled events. Its evaluation has 3,884 events with 526 attacks (13.54% prevalence). It reused seed 42's fitted statistical parameters, threshold, and rules without recalibration.

Seed 42's rules missed 70/449 brute-force events, 88/225 spraying events, and 5/14 unusual successes. Burst rules miss early events before thresholds are reached. With smaller seed-43 bursts, spraying event recall fell to 80/224.

The statistical baseline made 32 benign alerts on seed 42's evaluation: 23 schedule changes, 8 password mistakes, and 1 normal login. It missed 30 attack events. Seed 43 yielded 63 benign alerts and 49 missed attacks. The validation budget therefore did not hold on later traffic. No thresholds were retuned using these evaluation results.

Zero observed rule false positives reflects a generator whose ordinary mistakes are short sequences, not a production promise. Attack prevalence is deliberately high and affects precision. Browser families, UTC schedules, shared sources, and missing-context tests do not reproduce a real site's traffic. Zero time to alert means the first event of an episode triggered, not zero processing latency. Broader legitimate bursts, context loss, low-and-slow attacks, and independently designed stress scenarios remain future work. No live failed-attempt publisher, enforcement, ML model, or runtime incident grouping is supplied by this experiment.

SHA-256 fingerprints of `events.jsonl`:

```text
seed 42: 4f7091cfacf8c652194def84b3d2648ee3c77cafc0b793d11e82da6d235d4106
seed 43: 196b3728704f10b4306cec9590ce40e5b6b77c33230809a793043f417f558eca
```

Local manifests record full config and event/label hashes. Metrics include confusion counts, per-scenario results, and synthetic error-example IDs. Generated events, features, and fitted statistical artifacts are excluded from Git.
