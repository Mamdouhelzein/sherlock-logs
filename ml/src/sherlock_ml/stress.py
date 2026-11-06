"""Frozen-artifact evaluation of independently generated, paired observation views."""

import argparse
import csv
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from sherlock_ml.artifacts import ARTIFACT_FILES, load_experiment, sha256
from sherlock_ml.evaluation import metrics
from sherlock_ml.events import timestamp
from sherlock_ml.features import FEATURE_VERSION, build_features
from sherlock_ml.stress_data import PROFILES, VIEWS, StressConfig, generate_stress, project
from sherlock_ml.training import predictions


def bundle_version(metadata):
    return hashlib.sha256(
        "|".join(
            metadata["sha256"][name]
            for name in ("model.joblib", "experiment.json", "feature_schema.json")
        ).encode()
    ).hexdigest()


def record(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def json_lines(path, rows):
    with path.open("w") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
    return sha256(path)


def evaluate_view(experiment, events, labels, config, view):
    visible = project(events, view)
    # Extract the entire visible history first; evaluate only the reserved later period.
    rows = [row for row in build_features(visible) if row.occurred_at >= config.evaluation_start]
    decisions, scores = predictions(experiment, rows)
    indices = {row.event_id: index for index, row in enumerate(rows)}
    truth = {label.event_id: label for label in labels}
    evaluation = [event for event in events if event.occurred_at >= config.evaluation_start]
    outcomes = {}
    for name, flags in decisions.items():
        # A hidden attack cannot be alerted on. Do not present unobserved benign
        # events as true negatives or include them in the operational false-alert rate.
        all_flags = [
            flags[indices[event.event_id]] if event.event_id in indices else False
            for event in evaluation
        ]
        end_to_end = metrics(evaluation, truth, all_flags)
        outcomes[name] = {
            "observed": metrics(rows, truth, flags),
            "end_to_end": {
                key: end_to_end[key]
                for key in (
                    "attack_events",
                    "true_positives",
                    "false_negatives",
                    "recall",
                    "incidents",
                    "detected_incidents",
                    "incident_recall",
                    "median_time_to_alert_seconds",
                )
            },
            "scenarios": end_to_end["by_scenario"],
        }
    output = []
    for event in evaluation:
        index = indices.get(event.event_id)
        label = truth[event.event_id]
        output.append(
            {
                "event_id": event.event_id,
                "occurred_at": event.occurred_at.isoformat(),
                "observed": index is not None,
                "is_attack": label.is_attack,
                "scenario": label.scenario,
                "incident_id": label.incident_id,
                **{
                    f"{name}_alert": flags[index] if index is not None else None
                    for name, flags in decisions.items()
                },
                **{
                    f"{name}_score": values[index] if index is not None else None
                    for name, values in scores.items()
                },
            }
        )
    observed_attack = sum(truth[row.event_id].is_attack for row in rows)
    total_attack = sum(truth[event.event_id].is_attack for event in evaluation)
    return {
        "seed": config.seed,
        "profile": config.profile,
        "view": view,
        "evaluation_events": len(evaluation),
        "observed_events": len(rows),
        "hidden_attack_events": total_attack - observed_attack,
        "hidden_benign_events": len(evaluation) - len(rows) - (total_attack - observed_attack),
        "detectors": outcomes,
    }, output


def summarize(runs):
    summary = []
    for profile in PROFILES:
        for view in VIEWS:
            selected = [run for run in runs if run["profile"] == profile and run["view"] == view]
            if not selected:
                continue
            for detector in selected[0]["detectors"]:
                observed = [run["detectors"][detector]["observed"] for run in selected]
                end_to_end = [run["detectors"][detector]["end_to_end"] for run in selected]
                tp = sum(row["true_positives"] for row in observed)
                fp = sum(row["false_positives"] for row in observed)
                benign = sum(row["benign_events"] for row in observed)
                attack = sum(row["attack_events"] for row in end_to_end)
                incidents = sum(row["incidents"] for row in end_to_end)
                rates = [
                    row["false_alerts_per_1000_benign"]
                    for row in observed
                    if row["false_alerts_per_1000_benign"] is not None
                ]
                summary.append(
                    {
                        "profile": profile,
                        "view": view,
                        "detector": detector,
                        "runs": len(selected),
                        "observed_benign_events": benign,
                        "false_alerts": fp,
                        "precision": tp / (tp + fp) if tp + fp else None,
                        "false_alerts_per_1000_benign": fp * 1000 / benign if benign else None,
                        "false_alert_rate_seed_range": [min(rates), max(rates)] if rates else None,
                        "end_to_end_attack_recall": tp / attack if attack else None,
                        "end_to_end_incident_recall": sum(
                            row["detected_incidents"] for row in end_to_end
                        )
                        / incidents
                        if incidents
                        else None,
                        "hidden_attack_events": sum(
                            run["hidden_attack_events"] for run in selected
                        ),
                    }
                )
    return summary


def operating_checks(runs):
    failures = []
    for run in runs:
        combined = run["detectors"]["combined"]
        rate = combined["observed"]["false_alerts_per_1000_benign"]
        context = {key: run[key] for key in ("seed", "profile", "view")}
        if rate is None or rate > 5:
            failures.append(
                {**context, "check": "false_alert_budget", "measured": rate, "limit": 5}
            )
        if run["profile"] == "fast_guessing" and run["view"] == "local_guard":
            recall = combined["end_to_end"]["incident_recall"]
            if recall is None or recall < 0.8:
                failures.append(
                    {**context, "check": "fast_episode_recall", "measured": recall, "minimum": 0.8}
                )
    return {
        "passed": not failures,
        "failures": failures,
        "automatic_enforcement_approved": False,
        "reason": "Synthetic diagnostics do not establish production safety or effectiveness.",
    }


def run_suite(
    artifact,
    output,
    *,
    expected_version,
    trusted=False,
    seeds=(1101, 1102, 1103),
    users=100,
    history_days=35,
    evaluation_days=14,
):
    if not trusted:
        raise ValueError("Explicitly trust your local artifact before evaluation")
    if output.exists() or output.resolve().is_relative_to(artifact.resolve()):
        raise ValueError("Use a new output directory outside the model bundle")
    if not 1 <= len(seeds) <= 10 or len(set(seeds)) != len(seeds):
        raise ValueError("Use 1–10 unique evaluation seeds")
    for seed in seeds:
        StressConfig(seed, users, history_days, evaluation_days)
    # Inspect the explicit bundle pin before the trusted deserialization boundary.
    metadata = json.loads((artifact / "metadata.json").read_text())
    if bundle_version(metadata) != expected_version:
        raise ValueError("The requested model pin does not match this bundle")
    prior_end = max(
        timestamp(metadata["provenance"][name][1])
        for name in ("training_range", "validation_range", "test_range")
    )
    if StressConfig(seeds[0], users, history_days, evaluation_days).start < prior_end:
        raise ValueError("Stress history must follow the artifact's original experiment periods")
    before = {name: sha256(artifact / name) for name in (*ARTIFACT_FILES, "metadata.json")}
    experiment, metadata = load_experiment(artifact, trusted=trusted)
    output.mkdir(parents=True, exist_ok=False)
    runs, manifests = [], []
    for seed in seeds:
        for profile in PROFILES:
            config = StressConfig(seed, users, history_days, evaluation_days, profile)
            events, labels = generate_stress(config)
            case = output / str(seed) / profile
            case.mkdir(parents=True)
            event_hash = json_lines(case / "events.jsonl", (event.record() for event in events))
            label_hash = json_lines(case / "labels.jsonl", (asdict(label) for label in labels))
            manifests.append(
                {"config": asdict(config), "events_sha256": event_hash, "labels_sha256": label_hash}
            )
            for view in VIEWS:
                result, predictions_ = evaluate_view(experiment, events, labels, config, view)
                destination = case / view
                destination.mkdir()
                with (destination / "predictions.csv").open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(predictions_[0]))
                    writer.writeheader()
                    writer.writerows(predictions_)
                result["predictions_sha256"] = sha256(destination / "predictions.csv")
                result["observed_events_sha256"] = hashlib.sha256(
                    "\n".join(
                        json.dumps(event.record(), sort_keys=True)
                        for event in project(events, view)
                    ).encode()
                ).hexdigest()
                record(destination / "metrics.json", result)
                runs.append(result)
    if any(sha256(artifact / name) != digest for name, digest in before.items()):
        raise ValueError("The evaluated artifact changed during evaluation")
    report = {
        "protocol": "frozen-stress-v1",
        "synthetic_only": True,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "live_model_changed": False,
        "fit_or_calibration_performed": False,
        "feature_version": FEATURE_VERSION,
        "model_id": metadata["model_id"],
        "bundle_version": expected_version,
        "artifact_sha256": before,
        "seeds": list(seeds),
        "users": users,
        "history_days": history_days,
        "evaluation_days": evaluation_days,
        "generator_sha256": sha256(Path(__file__).with_name("stress_data.py")),
        "evaluator_sha256": sha256(Path(__file__)),
        "datasets": manifests,
        "summary": summarize(runs),
        "operating_checks": operating_checks(runs),
        "runs": runs,
    }
    record(output / "report.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--expected-model-version", required=True)
    parser.add_argument("--trust-local-artifact", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[1101, 1102, 1103])
    parser.add_argument("--users", type=int, default=100)
    parser.add_argument("--history-days", type=int, default=35)
    parser.add_argument("--evaluation-days", type=int, default=14)
    args = parser.parse_args(argv)
    try:
        report = run_suite(
            args.artifact,
            args.output,
            expected_version=args.expected_model_version,
            trusted=args.trust_local_artifact,
            seeds=tuple(args.seeds),
            users=args.users,
            history_days=args.history_days,
            evaluation_days=args.evaluation_days,
        )
        print(
            json.dumps(
                {
                    "synthetic_only": True,
                    "runs": len(report["runs"]),
                    "diagnostic_checks_passed": report["operating_checks"]["passed"],
                    "live_model_changed": False,
                    "output": str(args.output),
                }
            )
        )
        return 0  # Diagnostic failures are findings, not a broken execution.
    except (OSError, ValueError, KeyError, TypeError, ImportError):
        print(
            json.dumps(
                {
                    "error": "Stress evaluation failed. Check local artifact trust/pin, "
                    "parameters and a new output path. No provider data is read."
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
