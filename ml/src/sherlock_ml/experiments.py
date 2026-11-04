"""CLI orchestration for offline model fitting, reproducible evaluation, and reports."""

import csv
import platform
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from sherlock_ml.artifacts import load_experiment, save_experiment, sha256
from sherlock_ml.cli import compact, load_dataset, load_features, write_json
from sherlock_ml.features import FEATURE_VERSION
from sherlock_ml.training import (
    TrainingOptions,
    aligned,
    anomaly_scores,
    evaluate_experiment,
    fit_from_partitions,
    matrix,
)


def inputs(dataset: Path, features: Path):
    config, events, labels = load_dataset(dataset)
    rows = load_features(features, dataset)
    facts = {event.event_id: event.occurred_at for event in events}
    if (
        len(facts) != len(events)
        or len(rows) != len(events)
        or any(facts.get(row.event_id) != row.occurred_at for row in rows)
    ):
        raise ValueError("Feature IDs/timestamps must match observable events")
    aligned(rows, labels)
    # Model results/selection must not depend on CSV row order.
    rows.sort(key=lambda row: (row.occurred_at, row.event_id))
    return config, rows, labels


def latency(experiment, rows) -> dict:
    values = matrix(rows)
    anomaly_scores(experiment.forest, values[:1])  # Warm up; no fitting or calibration.
    start = time.perf_counter()
    anomaly_scores(experiment.forest, values)
    elapsed = time.perf_counter() - start
    single = []
    for index in range(min(50, len(rows))):
        start = time.perf_counter()
        anomaly_scores(experiment.forest, values[index : index + 1])
        single.append((time.perf_counter() - start) * 1000)
    return {
        "scope": "Warm in-process ML inference only; excludes I/O and feature extraction.",
        "platform": platform.platform(),
        "events_in_batch": len(rows),
        "batch_seconds": elapsed,
        "batch_amortized_ms_per_event": elapsed * 1000 / len(rows),
        "single_event_samples": len(single),
        "single_event_p50_ms": float(np.percentile(single, 50)),
        "single_event_p95_ms": float(np.percentile(single, 95)),
    }


def write_evaluation(output, experiment, rows, labels, config, provenance):
    report, predictions = evaluate_experiment(experiment, rows, labels, config)
    report["config"] = asdict(config)
    report["feature_version"] = FEATURE_VERSION
    report["provenance"] = provenance
    write_json(output / "metrics.json", report)
    with (output / "predictions.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(predictions[0]))
        writer.writeheader()
        writer.writerows(predictions)
    by_id = {row.event_id: row for row in rows}
    examples = {}
    for detector in report["detectors"]:
        example_ids = report["detectors"][detector]["test"]
        examples[detector] = {
            category: [
                {
                    "prediction": prediction,
                    "observed_features": by_id[prediction["event_id"]].values,
                }
                for prediction in predictions
                if prediction["event_id"] in example_ids[category]
            ]
            for category in ("false_positive_examples", "missed_attack_examples")
        }
    write_json(output / "examples.json", examples)
    test_rows = [row for row in rows if row.occurred_at >= config.validation_end]
    write_json(output / "latency.json", latency(experiment, test_rows))
    return {
        "synthetic_only": True,
        "output": str(output),
        "test": {name: compact(result["test"]) for name, result in report["detectors"].items()},
    }


def train_files(args) -> dict:
    if args.output.exists():
        raise ValueError("Output directory already exists")
    config, rows, labels = inputs(args.dataset, args.features)
    options = TrainingOptions(
        args.model_seed, args.trees, tuple(args.sample_sizes), args.false_alert_budget
    )
    experiment = fit_from_partitions(rows, labels, config, options)
    provenance = {
        "dataset_manifest_sha256": sha256(args.dataset / "manifest.json"),
        "features_sha256": sha256(args.features / "features.csv"),
        "dataset_config": asdict(config),
        "training_range": [config.start_at.isoformat(), config.train_end.isoformat()],
        "validation_range": [config.train_end.isoformat(), config.validation_end.isoformat()],
        "test_range": [config.validation_end.isoformat(), config.end.isoformat()],
        "fit_population": "all training features; labels never passed to fit",
        "selection_population": "validation labels/scores only; test untouched by selection",
    }
    metadata = save_experiment(args.output, experiment, provenance)
    result = write_evaluation(
        args.output,
        experiment,
        rows,
        labels,
        config,
        {"mode": "fit then freeze", "model_id": metadata["model_id"]},
    )
    result["model_id"] = metadata["model_id"]
    return result


def evaluate_files(args) -> dict:
    if args.output.exists():
        raise ValueError("Output directory already exists")
    config, rows, labels = inputs(args.dataset, args.features)
    experiment, metadata = load_experiment(args.artifact, trusted=args.trust_local_artifact)
    args.output.mkdir(parents=True, exist_ok=False)
    result = write_evaluation(
        args.output,
        experiment,
        rows,
        labels,
        config,
        {
            "mode": "frozen artifact; no fitting or recalibration",
            "model_id": metadata["model_id"],
            "dataset_manifest_sha256": sha256(args.dataset / "manifest.json"),
            "artifact_metadata_sha256": sha256(args.artifact / "metadata.json"),
        },
    )
    return result
