import json
from dataclasses import replace

import joblib
import numpy as np
import pytest
from sklearn.ensemble import IsolationForest

from sherlock_ml.artifacts import load_experiment, save_experiment, sha256
from sherlock_ml.cli import main
from sherlock_ml.evaluation import partition
from sherlock_ml.features import build_features
from sherlock_ml.synthetic import Config, generate
from sherlock_ml.training import (
    TrainingOptions,
    evaluate_experiment,
    fit_experiment,
    fit_from_partitions,
    matrix,
    predictions,
)


@pytest.fixture(scope="module")
def data():
    config = Config(users=20, days=12, train_days=6, validation_days=3, attack_episodes=18)
    events, labels = generate(config)
    rows = build_features(events)
    options = TrainingOptions(seed=7, trees=16, sample_sizes=(16, 32), false_alert_budget=5)
    return config, rows, labels, options


def fit(data):
    config, rows, labels, options = data
    return fit_from_partitions(rows, labels, config, options)


def test_reproducible_fit_and_validation_budget_including_combined(data):
    config, rows, labels, _ = data
    experiment = fit(data)
    repeated = fit(data)
    assert experiment.thresholds == repeated.thresholds
    assert experiment.selection == repeated.selection
    first, _ = predictions(experiment, rows)
    assert first == predictions(repeated, rows)[0]
    report, _ = evaluate_experiment(experiment, rows, labels, config)
    for detector in ("ml", "rules", "statistical", "combined"):
        assert report["detectors"][detector]["validation"]["false_alerts_per_1000_benign"] <= 5
    assert experiment.forest.n_features_in_ == 15
    assert len(experiment.selection) == 2


def test_training_never_receives_labels_or_final_period(data, monkeypatch):
    config, rows, _, _ = data
    expected = matrix([row for row in rows if partition(row, config) == "train"])
    original = IsolationForest.fit
    calls = []

    def spy(self, values, *args, **kwargs):
        np.testing.assert_array_equal(values, expected)
        assert args == () and kwargs == {}
        calls.append(len(values))
        return original(self, values)

    monkeypatch.setattr(IsolationForest, "fit", spy)
    fit(data)
    assert len(calls) == 2


def test_changing_test_features_and_labels_cannot_change_training_or_selection(data):
    config, rows, labels, options = data
    expected = fit(data)
    test_ids = {row.event_id for row in rows if partition(row, config) == "test"}
    changed_rows = [
        replace(row, values={name: 1_000_000.0 for name in row.values})
        if row.event_id in test_ids
        else row
        for row in rows
    ]
    changed_labels = [
        replace(label, is_attack=False, incident_id=None, scenario="changed")
        if label.event_id in test_ids
        else label
        for label in labels
    ]
    actual = fit_from_partitions(changed_rows, changed_labels, config, options)
    assert expected.thresholds == actual.thresholds
    assert expected.selection == actual.selection
    np.testing.assert_array_equal(
        expected.forest.score_samples(matrix(rows)), actual.forest.score_samples(matrix(rows))
    )


def test_training_labels_cannot_filter_the_fit_population(data):
    config, rows, labels, options = data
    training_ids = {row.event_id for row in rows if partition(row, config) == "train"}
    changed = [
        replace(label, is_attack=False, incident_id=None, scenario="ignored")
        if label.event_id in training_ids
        else label
        for label in labels
    ]
    expected = fit(data)
    actual = fit_from_partitions(rows, changed, config, options)
    assert expected.selection == actual.selection
    assert expected.thresholds == actual.thresholds


def test_roundtrip_frozen_model_keeps_scores_and_never_refits(data, tmp_path, monkeypatch):
    config, rows, labels, _ = data
    experiment = fit(data)
    output = tmp_path / "model"
    metadata = save_experiment(output, experiment, {"test": "fixture"})
    assert metadata["synthetic_only"] is True
    loaded, _ = load_experiment(output, trusted=True)
    assert predictions(loaded, rows) == predictions(experiment, rows)

    def forbidden(*args, **kwargs):
        raise AssertionError("Frozen evaluation must not fit or calibrate")

    monkeypatch.setattr(IsolationForest, "fit", forbidden)
    monkeypatch.setattr("sherlock_ml.training.calibrate", forbidden)
    report, _ = evaluate_experiment(loaded, rows, labels, config)
    assert report["thresholds"] == experiment.thresholds
    assert report["connected_to_live_auth"] is False


def test_untrusted_or_corrupt_models_are_rejected_before_deserialization(
    data, tmp_path, monkeypatch
):
    output = tmp_path / "model"
    save_experiment(output, fit(data), {})

    def forbidden(*args, **kwargs):
        raise AssertionError("Must not deserialize this artifact")

    monkeypatch.setattr(joblib, "load", forbidden)
    with pytest.raises(ValueError, match="trust"):
        load_experiment(output)
    (output / "model.joblib").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        load_experiment(output, trusted=True)


@pytest.mark.parametrize("mismatch", ["version", "feature"])
def test_incompatible_versions_and_features_fail_before_loading(
    data, tmp_path, monkeypatch, mismatch
):
    output = tmp_path / "model"
    save_experiment(output, fit(data), {})
    metadata = json.loads((output / "metadata.json").read_text())
    if mismatch == "version":
        metadata["versions"]["scikit-learn"] = "0.0"
    else:
        schema = json.loads((output / "feature_schema.json").read_text())
        schema["feature_names"].reverse()
        (output / "feature_schema.json").write_text(json.dumps(schema))
        metadata["sha256"]["feature_schema.json"] = sha256(output / "feature_schema.json")
    (output / "metadata.json").write_text(json.dumps(metadata))

    def forbidden(*args, **kwargs):
        raise AssertionError("Compatibility must be checked before loading")

    monkeypatch.setattr(joblib, "load", forbidden)
    with pytest.raises(ValueError):
        load_experiment(output, trusted=True)


def test_fitting_rejects_overlap_and_nonchronological_partitions(data):
    _, rows, labels, options = data
    with pytest.raises(ValueError, match="precede"):
        fit_experiment(rows[:10], rows[:10], labels[:10], options)
    for changes in ({"trees": 0}, {"sample_sizes": ()}, {"false_alert_budget": -1}):
        with pytest.raises(ValueError):
            replace(options, **changes)


def test_cli_train_and_frozen_evaluation_outputs(data, tmp_path):
    dataset, features, model, evaluation = [
        tmp_path / name for name in ("data", "features", "model", "evaluation")
    ]
    assert (
        main(
            [
                "generate",
                "--users",
                "20",
                "--days",
                "12",
                "--train-days",
                "6",
                "--validation-days",
                "3",
                "--attack-episodes",
                "18",
                "--output",
                str(dataset),
            ]
        )
        == 0
    )
    assert main(["features", "--dataset", str(dataset), "--output", str(features)]) == 0
    assert (
        main(
            [
                "train",
                "--dataset",
                str(dataset),
                "--features",
                str(features),
                "--trees",
                "16",
                "--sample-sizes",
                "16",
                "32",
                "--output",
                str(model),
            ]
        )
        == 0
    )
    for name in (
        "model.joblib",
        "metadata.json",
        "feature_schema.json",
        "metrics.json",
        "selection.json",
        "examples.json",
        "predictions.csv",
        "latency.json",
    ):
        assert (model / name).is_file()
    assert (
        main(
            [
                "evaluate",
                "--dataset",
                str(dataset),
                "--features",
                str(features),
                "--artifact",
                str(model),
                "--output",
                str(evaluation),
            ]
        )
        == 1
    )
    assert not evaluation.exists()
    assert (
        main(
            [
                "evaluate",
                "--dataset",
                str(dataset),
                "--features",
                str(features),
                "--artifact",
                str(model),
                "--trust-local-artifact",
                "--output",
                str(evaluation),
            ]
        )
        == 0
    )
    report = json.loads((evaluation / "metrics.json").read_text())
    assert report["provenance"]["mode"] == "frozen artifact; no fitting or recalibration"
    assert report["detectors"] == json.loads((model / "metrics.json").read_text())["detectors"]
