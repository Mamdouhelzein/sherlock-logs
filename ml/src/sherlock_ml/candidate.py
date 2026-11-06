"""Offline candidate training followed by a separate, pinned frozen holdout command."""

import argparse
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

from sherlock_ml.artifacts import ARTIFACT_FILES, load_experiment, save_experiment, sha256
from sherlock_ml.baselines import calibrate
from sherlock_ml.candidate_data import (
    BENIGN_PROFILES,
    HOLDOUT_SEEDS,
    TRAIN_SEED,
    VALIDATION_SEED,
    CandidateData,
    generate_candidate,
)
from sherlock_ml.evaluation import metrics
from sherlock_ml.features import FEATURE_VERSION, build_features
from sherlock_ml.stress import (
    bundle_version,
    evaluate_view,
    json_lines,
    operating_checks,
    record,
    summarize,
)
from sherlock_ml.stress_data import PROFILES, project
from sherlock_ml.training import TrainingOptions, aligned, fit_experiment, predictions


def dataset(config, directory):
    events, labels = generate_candidate(config)
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {
        "config": asdict(config),
        "start": config.start.isoformat(),
        "measured_start": config.evaluation_start.isoformat(),
        "end": config.end.isoformat(),
        "events_sha256": json_lines(directory / "events.jsonl", (e.record() for e in events)),
        "labels_sha256": json_lines(
            directory / "labels.jsonl", (asdict(label) for label in labels)
        ),
    }
    visible = project(events, "local_guard")
    rows = [row for row in build_features(visible) if row.occurred_at >= config.evaluation_start]
    by_id = {label.event_id: label for label in labels}
    return events, labels, rows, [by_id[row.event_id] for row in rows], manifest


def fit_candidate(training, validation, validation_labels, groups, options):
    """Only development snapshots/labels enter fitting or group calibration."""
    truth = aligned(validation, validation_labels)
    if len(groups) != len(validation) or not groups:
        raise ValueError("Every validation row needs an observation-workload group")
    names = sorted(set(groups))
    benign_indices = {
        name: [
            i
            for i, row in enumerate(validation)
            if groups[i] == name and not truth[row.event_id].is_attack
        ]
        for name in names
    }
    if any(not indices for indices in benign_indices.values()):
        raise ValueError("Every workload needs benign validation observations")
    candidates, selection = [], []
    for size in sorted(set(options.sample_sizes)):
        experiment = fit_experiment(
            training, validation, validation_labels, replace(options, sample_sizes=(size,))
        )
        _, scores = predictions(experiment, validation)

        def cutoff(detector, budget, scores=scores):
            return max(
                calibrate([scores[detector][i] for i in indices], budget)
                for indices in benign_indices.values()
            )

        budget = options.false_alert_budget
        experiment.thresholds = {
            "ml": cutoff("ml", budget),
            "rules": cutoff("rules", budget),
            "statistical": cutoff("statistical", budget),
            "combined_ml": cutoff("ml", budget / 2),
            "combined_rules": cutoff("rules", budget / 2),
        }
        experiment.options = options
        decisions, _ = predictions(experiment, validation)
        grouped = {}
        for name in names:
            indices = [i for i, group in enumerate(groups) if group == name]
            grouped[name] = {
                detector: metrics(
                    [validation[i] for i in indices], truth, [flags[i] for i in indices]
                )
                for detector, flags in decisions.items()
            }
        attacked = [value["ml"] for value in grouped.values() if value["ml"]["attack_events"]]
        key = (
            mean(row["incident_recall"] for row in attacked) if attacked else 0.0,
            mean(row["recall"] for row in attacked) if attacked else 0.0,
            -sum(value["ml"]["false_positives"] for value in grouped.values()),
            -experiment.forest.max_samples_,
        )
        selection.append(
            {
                "max_samples": experiment.forest.max_samples_,
                "thresholds": dict(experiment.thresholds),
                "selection_key": list(key),
                "validation_by_workload": grouped,
            }
        )
        candidates.append((key, experiment))
    result = max(candidates, key=lambda pair: pair[0])[1]
    result.selection = selection
    result.validate()
    return result


def train_candidate(output, *, users=100, history_days=35, evaluation_days=21, options=None):
    if output.exists():
        raise ValueError("Use a new candidate directory")
    # Validate parameters before creating output; this entry point cannot request holdout seeds.
    CandidateData("train", TRAIN_SEED, "routine", users, history_days, evaluation_days)
    options = options or TrainingOptions()
    output.mkdir(parents=True)
    training, validation, labels, groups, manifests = [], [], [], [], []
    for phase, seed, profiles in (
        ("train", TRAIN_SEED, BENIGN_PROFILES),
        ("validation", VALIDATION_SEED, PROFILES),
    ):
        for profile in profiles:
            config = CandidateData(phase, seed, profile, users, history_days, evaluation_days)
            _, _, rows, visible_labels, manifest = dataset(
                config, output / "data" / phase / profile
            )
            manifests.append(manifest)
            if phase == "train":
                # No training label argument/filter enters the fitting boundary.
                training.extend(rows)
            else:
                validation.extend(rows)
                labels.extend(visible_labels)
                groups.extend([profile] * len(rows))
    experiment = fit_candidate(training, validation, labels, groups, options)
    metadata = save_experiment(
        output / "model",
        experiment,
        {
            "protocol": "local-observation-candidate-v2",
            "observation_contract": "local_guard",
            "calibration": "maximum benign validation quantile over all six workloads",
            "training_range": [
                min(r.occurred_at for r in training).isoformat(),
                max(r.occurred_at for r in training).isoformat(),
            ],
            "validation_range": [
                min(r.occurred_at for r in validation).isoformat(),
                max(r.occurred_at for r in validation).isoformat(),
            ],
            "training_rows": len(training),
            "validation_rows": len(validation),
            "datasets": manifests,
            "generator_sha256": sha256(Path(__file__).with_name("candidate_data.py")),
            "candidate_code_sha256": sha256(Path(__file__)),
        },
    )
    report = {
        "protocol": "local-observation-candidate-v2",
        "synthetic_only": True,
        "live_model_changed": False,
        "holdout_generated": False,
        "candidate_bundle_version": bundle_version(metadata),
        "model_id": metadata["model_id"],
        "options": asdict(options),
        "thresholds": experiment.thresholds,
        "selected_samples": experiment.forest.max_samples_,
        "provenance": metadata["provenance"],
        "selection": experiment.selection,
    }
    record(output / "training.json", report)
    return report


def checked_load(path, expected, trusted):
    if not trusted:
        raise ValueError("Explicitly trust local model artifacts")
    metadata = json.loads((path / "metadata.json").read_text())
    if bundle_version(metadata) != expected:
        raise ValueError("Model bundle pin does not match")
    return load_experiment(path, trusted=True)


def evaluate_candidate(
    candidate,
    reference,
    output,
    *,
    candidate_pin,
    reference_pin,
    trusted=False,
    seeds=HOLDOUT_SEEDS,
    users=100,
    history_days=35,
    evaluation_days=21,
):
    if output.exists() or any(
        output.resolve().is_relative_to(p.resolve()) for p in (candidate, reference)
    ):
        raise ValueError("Use a fresh evaluation directory outside both model bundles")
    if (
        not seeds
        or len(seeds) != len(set(seeds))
        or any(seed in (TRAIN_SEED, VALIDATION_SEED) for seed in seeds)
    ):
        raise ValueError("Evaluation must use distinct non-development seeds")
    first = CandidateData("holdout", seeds[0], "routine", users, history_days, evaluation_days)
    # Pins and artifact validation precede final data generation.
    experiment, metadata = checked_load(candidate, candidate_pin, trusted)
    original, reference_metadata = checked_load(reference, reference_pin, trusted)
    if metadata["provenance"].get("observation_contract") != "local_guard":
        raise ValueError("Candidate does not declare the supported observation contract")
    if metadata["provenance"].get("generator_sha256") != sha256(
        Path(__file__).with_name("candidate_data.py")
    ) or metadata["provenance"].get("candidate_code_sha256") != sha256(Path(__file__)):
        raise ValueError("Candidate generator/evaluator code changed after fitting")
    if first.start <= datetime.fromisoformat(metadata["provenance"]["validation_range"][1]):
        raise ValueError("Holdout must follow the validation period")
    paths = {"candidate": candidate, "reference": reference}
    before = {
        name: {file: sha256(path / file) for file in (*ARTIFACT_FILES, "metadata.json")}
        for name, path in paths.items()
    }
    output.mkdir(parents=True)
    runs = {"candidate": [], "reference": []}
    manifests = []
    for seed in seeds:
        for profile in PROFILES:
            config = CandidateData("holdout", seed, profile, users, history_days, evaluation_days)
            directory = output / str(seed) / profile
            events, labels, _, _, manifest = dataset(config, directory)
            manifests.append(manifest)
            for name, model in (("candidate", experiment), ("reference", original)):
                result, rows = evaluate_view(model, events, labels, config, "local_guard")
                result["predictions_sha256"] = json_lines(
                    directory / f"{name}-predictions.jsonl", rows
                )
                runs[name].append(result)
    for name, path in paths.items():
        if before[name] != {file: sha256(path / file) for file in before[name]}:
            raise RuntimeError("A model bundle changed during frozen evaluation")
    report = {
        "protocol": "local-observation-candidate-v2",
        "synthetic_only": True,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "feature_version": FEATURE_VERSION,
        "live_model_changed": False,
        "fit_or_calibration_performed": False,
        "automatic_enforcement_approved": False,
        "candidate_bundle_version": candidate_pin,
        "reference_bundle_version": reference_pin,
        "candidate_model_id": metadata["model_id"],
        "reference_model_id": reference_metadata["model_id"],
        "artifact_sha256": before,
        "candidate_provenance": metadata["provenance"],
        "generator_sha256": sha256(Path(__file__).with_name("candidate_data.py")),
        "candidate_code_sha256": sha256(Path(__file__)),
        "datasets": manifests,
        "runs": runs,
        "summary": {name: summarize(results) for name, results in runs.items()},
        "operating_checks": {name: operating_checks(results) for name, results in runs.items()},
    }
    record(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("train")
    train.add_argument("--output", type=Path, required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--candidate", type=Path, required=True)
    evaluate.add_argument("--reference", type=Path, required=True)
    evaluate.add_argument("--candidate-pin", required=True)
    evaluate.add_argument("--reference-pin", required=True)
    evaluate.add_argument("--trust-local-artifact", action="store_true")
    evaluate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "train":
        result = train_candidate(args.output)
        print(
            json.dumps(
                {
                    k: result[k]
                    for k in ("candidate_bundle_version", "selected_samples", "holdout_generated")
                }
            )
        )
    else:
        result = evaluate_candidate(
            args.candidate,
            args.reference,
            args.output,
            candidate_pin=args.candidate_pin,
            reference_pin=args.reference_pin,
            trusted=args.trust_local_artifact,
        )
        print(
            json.dumps(
                {
                    "checks": {
                        name: value["passed"] for name, value in result["operating_checks"].items()
                    },
                    "live_model_changed": False,
                }
            )
        )


if __name__ == "__main__":
    main()
