# Frozen-model stress protocol v1

Protocol date: 2026-11-06. Specify this protocol before inspecting its results.
This is an independently implemented synthetic stress suite, not real customer
traffic and not proof of real-world effectiveness. It adds no sign-in requests,
database reads, training, calibration or model activation.

Evaluate the existing trusted, explicitly pinned v1 artifact on seeds 1101,
1102 and 1103. Use 100 fictional accounts, 35 days of causal warm-up and 14
evaluation days beginning after warm-up, from 2026-07-01 UTC. These populations
and dates are separate from the original training/validation/test datasets.
Do not call the original simulator to construct the new scenarios.

Workloads: benign routine control; legitimate shared-NAT/shift and password
manager retry bursts; schedule/browser/new-account changes; fast guessing;
slow/distributed/unknown-account attacks; and a mixed workload. Include familiar
credential misuse that may be observationally indistinguishable from an ordinary
successful login. Successful theft is a threat label, not something login logs can
prove. Keep labels/episode IDs outside observable events and feature construction.

For every workload and seed, compare paired views of the same original stream:

| View | Observable facts |
| --- | --- |
| Complete | All generated facts; an optimistic control |
| Local guard | Known-account failures and successes, without IP/browser fields; unknown-account failures are absent, matching the hook's boundary |
| Failure logs | All events, with account/browser fields removed from failures; IP is optimistically retained when generated |

The two restricted views are explicit contracts, not measured distributions of
missing fields. They do not model every provider error, log delay or outage.
Rebuild causal history from the projected stream, including the warm-up; never
score with hidden fields or hidden events. Preserve unknown values as missing.

Compare the frozen ML, calibrated rules, statistical baseline, combined detector
and fixed-rule reference. Report observed precision/recall, false alerts per 1,000
observed benign events, episode recall and conditional time to alert. Separately
report end-to-end attack-event/episode recall counting unobserved attacks as
unalerted, observation coverage, and per-scenario outcomes. Do not count unobserved
benign events as evidence of correct safe classifications. Show per-seed ranges;
do not pretend correlated burst events are independent confidence samples.

Prespecified operating checks for the combined detector: at most 5 false alerts
per 1,000 observed benign evaluation events in every workload/view/seed, and at
least 80% end-to-end episode recall for fast guessing in each local-guard run.
These are diagnostic checks, not permission to block users. Any failure, lack of
real labeled data, or known observation blind spot keeps automated ML enforcement
unapproved. Keep the current model and deterministic password guard unchanged.

Store generated rows/predictions under ignored `artifacts/`; publish aggregate
JSON and a model-evaluation note with code/data/artifact fingerprints. If results
inform a future candidate model, this suite becomes development evidence; reserve
new evaluation scenarios/seeds before selecting that candidate.

Method references: [scikit-learn leakage guidance](https://scikit-learn.org/stable/common_pitfalls),
[Isolation Forest scoring](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html).
