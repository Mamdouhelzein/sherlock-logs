# Local-observation candidate v2 protocol

Specified 2026-11-06 before fitting the candidate or generating final holdout data.
The previous stress suite is now development evidence. It is not a fresh test.
This experiment is synthetic only, offline, and cannot replace the active model.

## Fixed design

Keep `login-history-v1` and all 15 features unchanged. Use the **local-guard**
observation contract: successes and known-account failures with no IP/browser;
unknown-account failures are invisible and count as misses in end-to-end recall.
Do not claim hosted-provider applicability or recovery of missing information.

Implement a new scenario generator with ordinary multiple-session activity,
weekends, typos, new users, shifted schedules, office login waves and stale-password
retries (including retries rejected during cooldown). Simulated successful
recovery occurs after cooldown expiry. Keep scenario labels separate from events.
Familiar-credential misuse is included without a guaranteed observable anomaly.

Use 100 fictional accounts and 35 warm-up days followed by 21 measured days.
Separate streams by phase/workload, including account/event/episode identifiers.
The timestamps are simulation coordinates, including future fictional dates:

| Phase | Seed(s) | Warm-up begins | Measured window, UTC | Workloads |
| --- | --- | --- | --- | --- |
| Training | 2201 | 2026-07-01 | Aug 5–26, exclusive end | routine, legitimate_bursts, behavior_drift |
| Validation | 2202 | 2026-09-01 | Oct 6–27, exclusive end | all six |
| Final holdout | 4401, 4402, 4403 | 2026-11-01 | Dec 6–27, exclusive end | all six |

The six workloads are routine, legitimate_bursts, behavior_drift, fast_guessing,
evasive and mixed. Training intentionally uses benign control workloads: retain
every measured training row, with **no training-label filtering**. Validation
includes attacks for candidate selection and benign labels for calibration.
Build histories independently for every phase/workload. Warm-up is not fitted or
included in reported measured-period metrics, but supplies causal history.

Final scenarios change distributions fixed in code before evaluation: broader
login-hour jitter, different retry counts/spacings, larger schedule shifts,
different office-wave sizes, variable fast bursts, and varied slow/distributed
attacks. They are variants from the same new simulator, not independent real data.
Never generate final seeds during training/selection. Unit tests use other seeds.

## Fitting, calibration and comparison

Isolation Forest candidates: 200 trees, max_samples 128/256/512, random_state 42,
single process, unchanged float32 preprocessing. Fit only training rows. For each
candidate, calibrate ML, continuous rules and statistical thresholds separately
on benign validation scores. For each detector take the **maximum of the six
workload-specific thresholds**, each targeting at most 5 alerts/1,000 benign.
Combined OR branches use half that budget each. These are validation constraints,
not guarantees on new traffic. The fixed rules reference stays uncalibrated.

Select the forest by macro-average observed validation episode recall across
attack-bearing workloads, then macro observed event recall, fewer benign false alerts, then smaller sample
size. Use the grouped-calibrated ML branch for selection; combined detection and
all baselines are reported. No final rows or labels enter fitting, thresholds or
selection. Persist the selected candidate, validation results, hashes and options
before loading final data. Commit the protocol/code before reading full results.

Evaluate the pinned candidate and pinned existing v1 model on exactly the same
final streams, rebuilding visible causal history. No fitting or calibration is
permitted in the final evaluation command. Record both models' per-seed/per-scenario
results, event/episode recall, observed false alerts, conditional time to alert and
coverage. Unobserved benign events never count as safe true negatives. Record
dataset, code and model fingerprints; leave raw rows/weights ignored.

## Prespecified decision

Candidate combined detection must stay at or below 5 false alerts/1,000 observed
benign events **in every final workload/seed** and detect at least 80% of fast
guessing episodes in each seed. Report comparison with v1, including reduced
recall, and publish failures without retuning on the holdout. Unknown-account and
familiar-credential blind spots remain explicit even if checks pass. Do not claim
universal detection or deploy/activate the candidate. Real labeled operational
evidence remains required; this run can only justify further shadow evaluation.
