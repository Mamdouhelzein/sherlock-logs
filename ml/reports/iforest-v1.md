# Isolation Forest v1 model card

Trained and evaluated on 2026-11-04. Model ID: `iforest-027e70e789fd5e28`. This card records the original offline synthetic-data experiment. A separate worker now uses this model for development shadow monitoring; it does not enforce authentication decisions. The later [stress evaluation](stress-v1.md) documents substantial false-alert and coverage limitations. Code and this report are public; model binaries and generated rows remain local and Git-ignored. The complete recorded results are in [iforest-v1.json](iforest-v1.json), with reproduction commands in the [ML guide](../README.md).

## Data and training

Seed 42 contains 16,485 fictional login events from 200 users over 90 days. Training uses days 1–50 (8,394 events; 149 attack-labeled events, 1.78% contamination). All training features are included without attack-label filtering. Validation uses days 51–70 (3,996 events); evaluation uses days 71–90 (4,095 events, including 688 attacks). UTC boundaries are 2026-01-05, 2026-02-24, 2026-03-16, and 2026-04-05, using inclusive starts and exclusive ends.

The model consumes only the ordered 15-feature `login-history-v1` vector. No IDs, raw addresses, labels, scenario IDs, or future events enter fitting. Features are converted to float32 with no fitted scaler. History updates causally, including earlier observed validation/test events; successful attacks can contaminate later history. Context-missing indicators exist. The later stress evaluation tests explicit observation contracts, but realistic provider field-loss distributions remain unmeasured.

The preset search fitted 200-tree Isolation Forests using 128, 256, or 512 samples per tree, model seed 42, `n_jobs=1`, default full feature sampling, and `contamination="auto"`. We use a separately calibrated threshold on **negative `score_samples`**: larger scores mean more unusual behavior, not compromise probability. [Official scoring API](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html).

Candidate selection used validation episode recall, event recall, lower false alerts, then smaller sample size. The 512-sample candidate won: validation event recall was 95.92%, episode recall 95.12%, and false alerts 4.84 per 1,000 benign events. Its ML threshold is `0.5824170562321728`. No test metrics were used for selection or subsequent retuning.

Rules use a continuous strongest-signal score from normalized account/source counts and the unfamiliar-browser/hour condition. Rules, ML, and statistics each calibrate against a cap of 5 false alerts per 1,000 benign validation events. Discrete rules used less than the cap; this is a common cap, not identical realized false-positive rates. Combined detection is an OR with half the budget allocated to each branch. Its thresholds are ML `0.5901581572824343` and rules `0.6`. Validation combined false alerts were 3.32 per 1,000, with event recall 95.20%.

## Frozen evaluation results

Seed 43 uses smaller bursts (`attack_scale=0.6`), and seed 44 is a fresh default-size run. Both reuse the seed-42 model and every threshold without fitting or recalibration. All three datasets come from the same simulator; different seeds are not independent real-world validation.

| Dataset and detector | Precision | Attack-event recall | False alerts / 1,000 benign | Episode recall |
| --- | ---: | ---: | ---: | ---: |
| Seed 42, calibrated rules | 99.65% | 83.14% | 0.59 | 87.18% |
| Seed 42, statistics | 95.36% | 95.64% | 9.39 | 100.00% |
| Seed 42, ML | 94.51% | 95.06% | 11.15 | 87.18% |
| Seed 42, combined | 96.74% | 94.77% | 6.46 | 87.18% |
| Seed 43, calibrated rules | 100.00% | 70.15% | 0.00 | 95.92% |
| Seed 43, statistics | 88.33% | 90.68% | 18.76 | 100.00% |
| Seed 43, ML | 93.06% | 94.30% | 11.02 | 95.92% |
| Seed 43, combined | 94.98% | 93.54% | 7.74 | 95.92% |
| Seed 44, calibrated rules | 99.43% | 82.18% | 1.19 | 95.83% |
| Seed 44, statistics | 97.08% | 93.43% | 7.16 | 100.00% |
| Seed 44, ML | 96.77% | 94.96% | 8.05 | 100.00% |
| Seed 44, combined | 97.36% | 94.96% | 6.56 | 100.00% |

Seed 43 has 15,861 events total and 3,884 evaluation events (526 attacks, 13.54% prevalence). Seed 44 has 16,319 total and 4,207 evaluation events (853 attacks, 20.28% prevalence). Seed 42 evaluation prevalence is 16.80%. Attack prevalence is deliberately high and affects precision. Original fixed-rule reference results are retained in the JSON report and [baseline report](baseline-v1.md).

ML does not consistently outperform the simpler statistical baseline: statistics had better recall and fewer false alerts on seed 42. ML improved recall and reduced false alerts on the smaller-burst seed 43. Combining rules and ML reduced false alerts compared with standalone ML but still exceeded the target on all three evaluation periods. These results do not justify automatic blocking or a claim that ML is always the better detector.

## Errors and limitations

On seed 42, ML produced 38 benign alerts: 14 normal logins, 7 ordinary mistakes, 4 new-browser events, and 13 legitimate schedule changes. It missed 25/449 brute-force events, 4/225 spraying events, and 5/14 suspicious successes. Combined detection produced 22 benign alerts and missed 36 attack events. Episode recall is lower than attack-event recall because long bursts contribute many events while a missed single successful login can mean a missed episode.

Two concrete synthetic examples:

- False alert `7c0872ff-54d6-4608-bc8e-27f4fedc0961`: a benign successful login after three ordinary failures. Browser familiarity was unchanged; hour deviation was 1.84 hours. ML score `0.58474` exceeded its `0.58242` threshold. The combined detector did not flag this event.
- Miss `0770411e-e091-4e18-a230-aac6c8ddad2a`: an early password-spraying event with no preceding account failures or source attempts. Hour deviation was 5.90 hours, but ML score `0.56094` stayed below threshold. Rules also missed it; the statistical baseline flagged it. These are observed inputs/results, not causal feature attributions.

The simulator makes many count-based attacks easier to distinguish than real traffic. At the time of this experiment, broader legitimate bursts, low-and-slow/distributed attacks and independently implemented scenarios were unverified. The subsequent stress report covers synthetic versions of these cases; real missing-context distributions remain unmeasured. The evaluation budget failed to transfer exactly under schedule changes. Any future tuning needs validation-only decisions and a newly reserved evaluation set; these reported test periods must not become a hidden tuning loop.

## Latency, artifacts, and checks

On the local macOS ARM training machine, one warmed ML batch of 4,095 events took 0.0291 seconds (0.0071 ms/event amortized). Fifty individual warm scoring calls measured median 4.81 ms and p95 4.96 ms. This is one local inference measurement, excluding feature extraction, I/O, queuing, and database/API time. Time-to-alert episode metrics in the JSON report are separate; an alert on an episode's first event yields zero delay without implying zero processing latency.

Runtime: CPython 3.13.12, scikit-learn 1.9.1, NumPy 2.5.4, SciPy 1.18.1, joblib 1.6.0, threadpoolctl 3.7.0, cloudpickle 3.1.2, narwhals 2.28.0. Runtime and test dependencies are hash-locked. Model metadata stores dataset/feature hashes, code hashes, ranges, parameters, and provenance. The model SHA-256 is `027e70e789fd5e28bb9e0a1caf589b922f891a6e04749708f2096b3174ed23a5`.

Artifact loading requires explicit trust plus matching versions, feature schema/code, and checksums before joblib deserialization. Checksums do not make an untrusted pickle safe. [Official persistence guidance](https://scikit-learn.org/stable/model_persistence.html). Tests verify seeded fitting, validation budgets, no train/test label filtering, no test-feature influence on selection, score-preserving reloads, rejection before untrusted/incompatible loads, and frozen evaluation without fitting/calibration. The original experiment had 38 passing local tests; the subsequent stress suite expands the total to 50.

This offline experiment itself added no runtime enforcement. Subsequent work connected the [shadow worker](../../docs/INFERENCE.md), trusted failure capture and a separate [protected local Auth realm](../../docs/FREE_AUTH.md). Automatic ML remediation remains disabled. The later stress evaluation fails the false-alert checks; remaining hosted authorization/recovery checks and always-on deployment retain their documented limits.
