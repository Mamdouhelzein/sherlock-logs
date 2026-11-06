import json
from dataclasses import replace

import pytest
from sklearn.ensemble import IsolationForest

from sherlock_ml import baselines, training
from sherlock_ml.artifacts import load_experiment, save_experiment, sha256
from sherlock_ml.features import FEATURE_NAMES, build_features
from sherlock_ml.stress import bundle_version, evaluate_view, run_suite
from sherlock_ml.stress_data import PROFILES, StressConfig, generate_stress, project
from sherlock_ml.synthetic import Config, generate
from sherlock_ml.training import TrainingOptions, fit_from_partitions


@pytest.fixture(scope="module")
def artifact(tmp_path_factory):
    config = Config(users=15, days=12, train_days=6, validation_days=3, attack_episodes=18)
    events, labels = generate(config)
    experiment = fit_from_partitions(
        build_features(events), labels, config, TrainingOptions(trees=16, sample_sizes=(16,))
    )
    path = tmp_path_factory.mktemp("frozen-stress") / "model"
    metadata = save_experiment(
        path,
        experiment,
        {
            "training_range": [config.start_at.isoformat(), config.train_end.isoformat()],
            "validation_range": [config.train_end.isoformat(), config.validation_end.isoformat()],
            "test_range": [config.validation_end.isoformat(), config.end.isoformat()],
        },
    )
    return path, metadata


@pytest.mark.parametrize("profile", PROFILES)
def test_independent_scenarios_are_seeded_label_free_and_in_the_reserved_period(profile):
    config = StressConfig(users=15, history_days=7, evaluation_days=3, profile=profile)
    events, labels = generate_stress(config)
    repeated, repeated_labels = generate_stress(config)
    assert events == repeated and labels == repeated_labels
    assert len({event.event_id for event in events}) == len(events)
    assert [label.event_id for label in labels] == [event.event_id for event in events]
    assert events == sorted(events, key=lambda event: (event.occurred_at, event.event_id))
    assert all(config.start <= event.occurred_at < config.end for event in events)
    assert all(
        not label.is_attack
        for event, label in zip(events, labels, strict=True)
        if event.occurred_at < config.evaluation_start
    )
    assert all(
        "scenario" not in event.record() and "is_attack" not in event.record() for event in events
    )
    assert all(set(row.values) == set(FEATURE_NAMES) for row in build_features(events))


def test_observation_views_remove_unavailable_history_not_just_the_current_fields():
    events, labels = generate_stress(StressConfig(users=15, history_days=7, evaluation_days=3))
    projected = project(events, "local_guard")
    assert all(event.source_ip is None and event.user_agent is None for event in projected)
    hidden = {event.event_id for event in events} - {event.event_id for event in projected}
    unknown_attacks = {
        label.event_id for label in labels if label.scenario == "attack_unknown_accounts"
    }
    assert unknown_attacks <= hidden
    rows = build_features(projected)
    assert all(
        row.values["source_attempts_5m"] == 0 and row.values["browser_missing"] == 1 for row in rows
    )
    failures = [event for event in project(events, "failure_logs") if event.outcome == "failure"]
    assert all(
        event.user_id is None and event.account_key is None and event.user_agent is None
        for event in failures
    )
    assert any(event.source_ip is not None for event in failures)


def test_hidden_attacks_are_counted_as_unalerted_without_scoring_invisible_rows(artifact):
    experiment, _ = load_experiment(artifact[0], trusted=True)
    config = StressConfig(users=15, history_days=7, evaluation_days=3)
    events, labels = generate_stress(config)
    result, predictions = evaluate_view(experiment, events, labels, config, "local_guard")
    unknown = [row for row in predictions if row["scenario"] == "attack_unknown_accounts"]
    assert unknown and all(not row["observed"] and row["combined_alert"] is None for row in unknown)
    observed = result["detectors"]["combined"]["observed"]
    all_attacks = result["detectors"]["combined"]["end_to_end"]
    assert all_attacks["attack_events"] > observed["attack_events"]
    assert all_attacks["true_positives"] == observed["true_positives"]
    assert all_attacks["recall"] < observed["recall"] or observed["true_positives"] == 0
    assert result["hidden_attack_events"] >= len(unknown)
    assert "true_negatives" not in all_attacks


def test_labels_cannot_change_features_scores_or_visibility(artifact):
    experiment, _ = load_experiment(artifact[0], trusted=True)
    config = StressConfig(users=15, history_days=7, evaluation_days=3)
    events, labels = generate_stress(config)
    _, first = evaluate_view(experiment, events, labels, config, "local_guard")
    benign_labels = [replace(label, is_attack=False, incident_id=None) for label in labels]
    _, second = evaluate_view(experiment, events, benign_labels, config, "local_guard")
    for a, b in zip(first, second, strict=True):
        assert a["event_id"] == b["event_id"] and a["observed"] == b["observed"]
        for key in a:
            if key.endswith(("_score", "_alert")):
                assert a[key] == b[key]


def test_suite_cannot_fit_recalibrate_modify_artifacts_or_overwrite_output(
    artifact, tmp_path, monkeypatch
):
    path, metadata = artifact
    before = {file.name: sha256(file) for file in path.iterdir()}

    def prohibited(*args, **kwargs):
        raise AssertionError("Frozen evaluation must not fit or calibrate")

    monkeypatch.setattr(IsolationForest, "fit", prohibited)
    monkeypatch.setattr(training, "fit_experiment", prohibited)
    monkeypatch.setattr(training, "calibrate", prohibited)
    monkeypatch.setattr(baselines, "calibrate", prohibited)
    output = tmp_path / "results"
    report = run_suite(
        path,
        output,
        expected_version=bundle_version(metadata),
        trusted=True,
        seeds=(1101,),
        users=10,
        history_days=7,
        evaluation_days=3,
    )
    assert len(report["runs"]) == 18
    assert report["fit_or_calibration_performed"] is False
    assert report["operating_checks"]["automatic_enforcement_approved"] is False
    assert json.loads((output / "report.json").read_text())["bundle_version"] == bundle_version(
        metadata
    )
    assert before == {file.name: sha256(file) for file in path.iterdir()}
    with pytest.raises(ValueError):
        run_suite(path, output, expected_version=bundle_version(metadata), trusted=True)


def test_untrusted_wrong_pin_and_overlapping_periods_fail_before_loading(
    artifact, tmp_path, monkeypatch
):
    import sherlock_ml.stress as stress

    def prohibited(*args, **kwargs):
        raise AssertionError("Must reject before deserialization")

    monkeypatch.setattr(stress, "load_experiment", prohibited)
    path, metadata = artifact
    for trusted, version in ((False, bundle_version(metadata)), (True, "0" * 64)):
        with pytest.raises(ValueError):
            run_suite(path, tmp_path / "unused", trusted=trusted, expected_version=version)
    clone = tmp_path / "future-model"
    clone.mkdir()
    future_metadata = json.loads(json.dumps(metadata))
    future_metadata["provenance"]["test_range"][1] = "2027-01-01T00:00:00+00:00"
    (clone / "metadata.json").write_text(json.dumps(future_metadata))
    with pytest.raises(ValueError):
        run_suite(
            clone, tmp_path / "unused", trusted=True, expected_version=bundle_version(metadata)
        )
