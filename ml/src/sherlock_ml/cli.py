"""Generate local datasets, extract features, and evaluate baselines without network access."""

import argparse
import csv
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path

from sherlock_ml import __version__
from sherlock_ml.baselines import RuleConfig, StatisticalBaseline, reference_record
from sherlock_ml.evaluation import evaluate
from sherlock_ml.events import Event, Label, timestamp
from sherlock_ml.features import FEATURE_NAMES, FEATURE_VERSION, Snapshot, build_features
from sherlock_ml.synthetic import Config, generate


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_dataset(path: Path) -> tuple[Config, list[Event], list[Label]]:
    manifest = json.loads((path / "manifest.json").read_text())
    if (
        manifest.get("synthetic_only") is not True
        or manifest.get("generator_version") != __version__
    ):
        raise ValueError("Unsupported synthetic dataset manifest")
    for name in ("events.jsonl", "labels.jsonl"):
        if manifest["sha256"][name] != digest(path / name):
            raise ValueError("Dataset checksum mismatch")
    config = Config(**manifest["config"])
    events = [
        Event.from_record(json.loads(line))
        for line in (path / "events.jsonl").read_text().splitlines()
    ]
    labels = [
        Label(**json.loads(line)) for line in (path / "labels.jsonl").read_text().splitlines()
    ]
    return config, events, labels


def generate_files(config: Config, output: Path) -> dict:
    events, labels = generate(config)
    output.mkdir(parents=True, exist_ok=False)
    for name, records in (
        ("events.jsonl", (event.record() for event in events)),
        ("labels.jsonl", (asdict(label) for label in labels)),
    ):
        with (output / name).open("w") as stream:
            for record in records:
                stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
    manifest = {
        "synthetic_only": True,
        "generator_version": __version__,
        "config": asdict(config),
        "events": len(events),
        "attack_events": sum(label.is_attack for label in labels),
        "sha256": {name: digest(output / name) for name in ("events.jsonl", "labels.jsonl")},
        "splits": {
            "train": [config.start_at.isoformat(), config.train_end.isoformat()],
            "validation": [config.train_end.isoformat(), config.validation_end.isoformat()],
            "test": [config.validation_end.isoformat(), config.end.isoformat()],
            "interval": "start inclusive, end exclusive",
        },
    }
    write_json(output / "manifest.json", manifest)
    return {"synthetic_only": True, "events": len(events), "output": str(output)}


def feature_files(dataset: Path, output: Path) -> dict:
    _, events, _ = load_dataset(dataset)
    snapshots = build_features(events)
    output.mkdir(parents=True, exist_ok=False)
    with (output / "features.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["event_id", "occurred_at", *FEATURE_NAMES])
        for row in snapshots:
            writer.writerow([row.event_id, row.occurred_at.isoformat(), *row.vector()])
    schema = {
        "feature_version": FEATURE_VERSION,
        "feature_names": list(FEATURE_NAMES),
        "metadata_only": ["event_id", "occurred_at"],
        "dataset_manifest_sha256": digest(dataset / "manifest.json"),
        "features_sha256": digest(output / "features.csv"),
    }
    write_json(output / "feature_schema.json", schema)
    return {"features": len(FEATURE_NAMES), "events": len(snapshots), "output": str(output)}


def load_features(path: Path, dataset: Path) -> list[Snapshot]:
    schema = json.loads((path / "feature_schema.json").read_text())
    if (
        schema["feature_version"] != FEATURE_VERSION
        or schema["feature_names"] != list(FEATURE_NAMES)
        or schema["metadata_only"] != ["event_id", "occurred_at"]
        or schema["dataset_manifest_sha256"] != digest(dataset / "manifest.json")
        or schema["features_sha256"] != digest(path / "features.csv")
    ):
        raise ValueError("Feature schema, checksum, or dataset mismatch")
    with (path / "features.csv").open(newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["event_id", "occurred_at", *FEATURE_NAMES]:
            raise ValueError("Unexpected feature columns")
        rows = [
            Snapshot(
                row["event_id"],
                timestamp(row["occurred_at"]),
                {name: float(row[name]) for name in FEATURE_NAMES},
            )
            for row in reader
        ]
    for row in rows:
        row.vector()
    return rows


def baseline_files(args) -> dict:
    config, events, labels = load_dataset(args.dataset)
    rows = load_features(args.features, args.dataset)
    facts = {event.event_id: event.occurred_at for event in events}
    if (
        len(facts) != len(rows)
        or len({row.event_id for row in rows}) != len(rows)
        or any(facts.get(row.event_id) != row.occurred_at for row in rows)
    ):
        raise ValueError("Feature IDs/timestamps do not match events")
    rules = RuleConfig(
        args.account_failures,
        args.source_attempts,
        args.source_accounts,
        args.unusual_hour,
        args.minimum_success_history,
    )
    reference = None
    budget = args.false_alert_budget
    provenance = {
        "dataset_manifest_sha256": digest(args.dataset / "manifest.json"),
        "config": asdict(config),
        "fit_population": "all training events; labels excluded",
        "calibration_population": "benign validation events only",
    }
    if args.reference:
        saved = json.loads(args.reference.read_text())
        if (
            saved["feature_version"] != FEATURE_VERSION
            or saved["feature_names"] != list(FEATURE_NAMES)
            or saved["kind"] != "robust-statistical-baseline"
        ):
            raise ValueError("Unsupported reference")
        threshold = float(saved["threshold"])
        if not math.isfinite(threshold) or threshold < 0:
            raise ValueError("Invalid reference threshold")
        reference = (StatisticalBaseline(saved["centers"], saved["scales"]), threshold)
        rules = RuleConfig(**saved["rules"])
        budget = float(saved["false_alert_budget_per_1000_benign"])
        provenance = saved["provenance"]
    if not math.isfinite(budget) or not 0 <= budget < 1000:
        raise ValueError("Invalid false-alert budget")
    report, model, threshold = evaluate(
        rows,
        labels,
        config,
        rules=rules,
        reference=reference,
        false_alert_budget=budget,
    )
    report["dataset_manifest_sha256"] = digest(args.dataset / "manifest.json")
    report["feature_version"] = FEATURE_VERSION
    report["config"] = asdict(config)
    report["reference_sha256"] = digest(args.reference) if args.reference else None
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "metrics.json", report)
    saved = reference_record(model, threshold, rules)
    saved["false_alert_budget_per_1000_benign"] = budget
    saved["provenance"] = provenance
    write_json(args.output / "baseline.json", saved)
    return {
        "synthetic_only": True,
        "output": str(args.output),
        "test_rules": compact(report["rules"]["test"]),
        "test_statistical": compact(report["statistical"]["test"]),
    }


def compact(metrics: dict) -> dict:
    return {
        key: metrics[key]
        for key in (
            "events",
            "precision",
            "recall",
            "false_alerts_per_1000_benign",
            "incident_recall",
        )
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    generate_parser = commands.add_parser(
        "generate", help="Create fictional events and separate labels"
    )
    for name, default in (
        ("seed", 42),
        ("users", 200),
        ("days", 90),
        ("train-days", 50),
        ("validation-days", 20),
        ("attack-episodes", 90),
    ):
        generate_parser.add_argument(f"--{name}", type=int, default=default)
    generate_parser.add_argument("--start", default="2026-01-05")
    generate_parser.add_argument("--attack-scale", type=float, default=1.0)
    generate_parser.add_argument("--output", type=Path, required=True)
    feature_parser = commands.add_parser(
        "features", help="Extract chronological, label-free features"
    )
    feature_parser.add_argument("--dataset", type=Path, required=True)
    feature_parser.add_argument("--output", type=Path, required=True)
    baseline_parser = commands.add_parser("baseline", help="Evaluate rules and robust statistics")
    baseline_parser.add_argument("--dataset", type=Path, required=True)
    baseline_parser.add_argument("--features", type=Path, required=True)
    baseline_parser.add_argument("--output", type=Path, required=True)
    baseline_parser.add_argument("--false-alert-budget", type=float, default=5.0)
    baseline_parser.add_argument(
        "--reference", type=Path, help="Reuse frozen parameters without retuning"
    )
    for name, default in (
        ("account-failures", 5),
        ("source-attempts", 20),
        ("source-accounts", 8),
        ("minimum-success-history", 5),
    ):
        baseline_parser.add_argument(f"--{name}", type=int, default=default)
    baseline_parser.add_argument("--unusual-hour", type=float, default=4.0)
    for command in ("train", "evaluate"):
        command_parser = commands.add_parser(
            command, help=f"{command.title()} offline Isolation Forest"
        )
        command_parser.add_argument("--dataset", type=Path, required=True)
        command_parser.add_argument("--features", type=Path, required=True)
        command_parser.add_argument("--output", type=Path, required=True)
        if command == "train":
            command_parser.add_argument("--model-seed", type=int, default=42)
            command_parser.add_argument("--trees", type=int, default=200)
            command_parser.add_argument(
                "--sample-sizes", type=int, nargs="+", default=[128, 256, 512]
            )
            command_parser.add_argument("--false-alert-budget", type=float, default=5.0)
        else:
            command_parser.add_argument("--artifact", type=Path, required=True)
            command_parser.add_argument(
                "--trust-local-artifact",
                action="store_true",
                help="Only use for artifacts you created or fully trust; joblib can execute code",
            )
    return root


def main(argv=None) -> int:
    arguments = parser()
    args = arguments.parse_args(argv)
    try:
        if args.command == "generate":
            config = Config(**{name: getattr(args, name) for name in Config.__dataclass_fields__})
            result = generate_files(config, args.output)
        elif args.command == "features":
            result = feature_files(args.dataset, args.output)
        elif args.command == "baseline":
            result = baseline_files(args)
        else:
            # Keep generation and baseline commands usable without scientific dependencies.
            from sherlock_ml.experiments import evaluate_files, train_files

            result = train_files(args) if args.command == "train" else evaluate_files(args)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ImportError):
        # Avoid echoing data records or paths from untrusted input into diagnostics.
        print(
            json.dumps(
                {
                    "error": "Experiment failed. Check input schemas, checksums, date ranges, "
                    "parameters, artifact trust/version compatibility, and installed dependencies. "
                    "Output directories must not already exist."
                }
            )
        )
        return 1
