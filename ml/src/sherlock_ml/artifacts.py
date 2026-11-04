"""Versioned local artifacts. Never deserialize a model from an untrusted source."""

import hashlib
import importlib.metadata
import json
import platform
from datetime import UTC, datetime
from pathlib import Path

import joblib

from sherlock_ml.baselines import RuleConfig, StatisticalBaseline
from sherlock_ml.features import FEATURE_NAMES, FEATURE_VERSION
from sherlock_ml.training import Experiment, TrainingOptions, experiment_config

DEPENDENCIES = (
    "numpy",
    "scipy",
    "scikit-learn",
    "joblib",
    "threadpoolctl",
    "cloudpickle",
    "narwhals",
)
ARTIFACT_FILES = ("model.joblib", "feature_schema.json", "experiment.json")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_file(path: Path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def versions() -> dict:
    return {
        "python": platform.python_version(),
        **{name: importlib.metadata.version(name) for name in DEPENDENCIES},
    }


def feature_code_hash() -> str:
    return sha256(Path(__file__).with_name("features.py"))


def save_experiment(output: Path, experiment: Experiment, provenance: dict) -> dict:
    experiment.validate()
    output.mkdir(parents=True, exist_ok=False)
    joblib.dump(experiment.forest, output / "model.joblib", compress=3)
    json_file(
        output / "feature_schema.json",
        {
            "feature_version": FEATURE_VERSION,
            "feature_names": list(FEATURE_NAMES),
            "feature_code_sha256": feature_code_hash(),
            "preprocessing": "identity numeric features converted to float32; no fitted scaler",
            "higher_score_is_more_anomalous": True,
            "score_method": "-IsolationForest.score_samples",
            "decision": "score > calibrated threshold",
        },
    )
    json_file(output / "experiment.json", experiment_config(experiment))
    metadata = {
        "artifact_version": 1,
        "model_type": "IsolationForest",
        "synthetic_only": True,
        "connected_to_live_auth": False,
        "created_at": datetime.now(UTC).isoformat(),
        "versions": versions(),
        "provenance": provenance,
        "sha256": {name: sha256(output / name) for name in ARTIFACT_FILES},
        "training_code_sha256": sha256(Path(__file__).with_name("training.py")),
        "trust": "Hashes detect accidental corruption, not malicious replacement. "
        "Only load artifacts you created or fully trust; joblib can execute code.",
    }
    metadata["model_id"] = "iforest-" + metadata["sha256"]["model.joblib"][:16]
    json_file(output / "metadata.json", metadata)
    json_file(output / "selection.json", experiment.selection)
    return metadata


def load_experiment(path: Path, *, trusted: bool = False) -> tuple[Experiment, dict]:
    if not trusted:
        raise ValueError("Explicitly trust the local artifact before loading joblib")
    metadata = json.loads((path / "metadata.json").read_text())
    if (
        metadata["artifact_version"] != 1
        or metadata["model_type"] != "IsolationForest"
        or metadata["synthetic_only"] is not True
    ):
        raise ValueError("Unsupported model artifact")
    current = versions()
    recorded = metadata["versions"]
    if any(recorded.get(name) != current[name] for name in DEPENDENCIES) or (
        recorded["python"].split(".")[:2] != current["python"].split(".")[:2]
    ):
        raise ValueError("Model dependency versions do not match the training environment")
    for name in ARTIFACT_FILES:
        if (path / name).stat().st_size > 128 * 1024 * 1024:
            raise ValueError("Artifact exceeds the local size limit")
        if sha256(path / name) != metadata["sha256"][name]:
            raise ValueError("Artifact checksum mismatch")
    schema = json.loads((path / "feature_schema.json").read_text())
    if (
        schema["feature_version"] != FEATURE_VERSION
        or schema["feature_names"] != list(FEATURE_NAMES)
        or schema["feature_code_sha256"] != feature_code_hash()
    ):
        raise ValueError("Feature schema or code does not match the trained model")
    config = json.loads((path / "experiment.json").read_text())
    options = {
        **config["training_options"],
        "sample_sizes": tuple(config["training_options"]["sample_sizes"]),
    }
    # Validate JSON parameters before crossing the explicitly trusted pickle boundary.
    settings = TrainingOptions(**options)
    rules = RuleConfig(**config["rules"])
    statistical = StatisticalBaseline(**config["statistical"])
    forest = joblib.load(path / "model.joblib")
    result = Experiment(forest, statistical, config["thresholds"], settings, rules, [])
    result.validate()
    return result, metadata
