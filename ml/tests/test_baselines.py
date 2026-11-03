from dataclasses import replace
from datetime import timedelta

import pytest

from sherlock_ml.baselines import RuleConfig, StatisticalBaseline, calibrate, rule_signals
from sherlock_ml.evaluation import evaluate, metrics, partition
from sherlock_ml.features import build_features
from sherlock_ml.synthetic import Config, generate


@pytest.fixture
def experiment():
    config = Config(users=15, days=12, train_days=6, validation_days=3, attack_episodes=18)
    events, labels = generate(config)
    return config, build_features(events), labels


def test_baselines_detect_bursts_and_report_false_positives_and_incidents(experiment):
    config, rows, labels = experiment
    report, _, _ = evaluate(rows, labels, config)
    assert report["rules"]["test"]["true_positives"] > 0
    for detector in ("rules", "statistical"):
        result = report[detector]["test"]
        assert result["events"] == result["attack_events"] + result["benign_events"]
        assert result["true_positives"] + result["false_negatives"] == result["attack_events"]
        assert result["true_negatives"] + result["false_positives"] == result["benign_events"]
        assert 0 <= result["detected_incidents"] <= result["incidents"]
    assert report["statistical"]["validation"]["false_alerts_per_1000_benign"] <= 5


def test_test_labels_cannot_influence_fit_or_validation_threshold(experiment):
    config, rows, labels = experiment
    _, model, threshold = evaluate(rows, labels, config)
    test_ids = {row.event_id for row in rows if partition(row, config) == "test"}
    changed = [
        replace(label, is_attack=False, incident_id=None, scenario="changed")
        if label.event_id in test_ids
        else label
        for label in labels
    ]
    _, next_model, next_threshold = evaluate(rows, changed, config)
    assert model == next_model
    assert threshold == next_threshold


def test_test_feature_extremes_cannot_influence_fit_or_threshold(experiment):
    config, rows, labels = experiment
    _, model, threshold = evaluate(rows, labels, config)
    changed = [
        replace(row, values={**row.values, "account_failures_15m": 1000000})
        if partition(row, config) == "test"
        else row
        for row in rows
    ]
    _, next_model, next_threshold = evaluate(changed, labels, config)
    assert (model, threshold) == (next_model, next_threshold)


def test_frozen_reference_does_not_recalibrate_on_a_new_seed(experiment):
    config, rows, labels = experiment
    _, model, threshold = evaluate(rows, labels, config)
    events, next_labels = generate(replace(config, seed=77, attack_scale=0.6))
    report, next_model, next_threshold = evaluate(
        build_features(events), next_labels, config, reference=(model, threshold)
    )
    assert report["calibration"] == "frozen reference"
    assert (model, threshold) == (next_model, next_threshold)


def test_date_boundaries_are_chronological(experiment):
    config, rows, _ = experiment
    row = rows[0]
    assert (
        partition(replace(row, occurred_at=config.train_end - timedelta(seconds=1)), config)
        == "train"
    )
    assert partition(replace(row, occurred_at=config.train_end), config) == "validation"
    assert partition(replace(row, occurred_at=config.validation_end), config) == "test"
    with pytest.raises(ValueError):
        partition(replace(row, occurred_at=config.end), config)


def test_calibration_handles_ties_and_zero_budget():
    assert calibrate([0] * 1000 + [10], 0) == 10
    threshold = calibrate([1] * 950 + [2] * 50, 5)
    assert sum(score > threshold for score in [1] * 950 + [2] * 50) <= 5
    with pytest.raises(ValueError):
        calibrate([], 5)
    with pytest.raises(ValueError):
        calibrate([1], 1000)


def test_undefined_metrics_are_null_not_fabricated_perfect_scores(experiment):
    _, rows, labels = experiment
    benign_ids = {label.event_id for label in labels if not label.is_attack}
    benign = [row for row in rows if row.event_id in benign_ids]
    result = metrics(benign, {label.event_id: label for label in labels}, [False] * len(benign))
    assert result["precision"] is None
    assert result["recall"] is None
    assert result["incident_recall"] is None
    assert result["median_time_to_alert_seconds"] is None


def test_rule_thresholds_are_configurable_and_labels_are_not_inputs(experiment):
    _, rows, _ = experiment
    row = replace(rows[0], values={**rows[0].values, "account_failures_15m": 6})
    assert "account_failure_burst" in rule_signals(row)
    assert "account_failure_burst" not in rule_signals(row, RuleConfig(account_failures=7))
    with pytest.raises(ValueError):
        StatisticalBaseline.fit([])
