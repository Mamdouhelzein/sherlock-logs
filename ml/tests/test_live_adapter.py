from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest
from sherlock_api.detection.runtime import ModelRuntime, artifact_version
from sherlock_api.detection.store import Claim

from sherlock_ml.artifacts import save_experiment
from sherlock_ml.features import build_features
from sherlock_ml.synthetic import Config, generate
from sherlock_ml.training import TrainingOptions, fit_from_partitions, predictions


def test_online_adapter_uses_the_same_features_and_scores_as_offline(tmp_path):
    config = Config(users=10, days=6, train_days=2, validation_days=2, attack_episodes=9)
    events, labels = generate(config)
    features = build_features(events)
    experiment = fit_from_partitions(
        features, labels, config, TrainingOptions(trees=16, sample_sizes=(16,))
    )
    path = tmp_path / "model"
    save_experiment(path, experiment, {})
    version = artifact_version(path)
    with pytest.raises(ValueError):
        ModelRuntime(path, version, trusted=False)
    with pytest.raises(ValueError):
        ModelRuntime(path, "0" * 64, trusted=True)
    runtime = ModelRuntime(path, version, trusted=True)

    def row(event):
        return {
            "id": event.event_id,
            **{k: v for k, v in event.record().items() if k != "event_id"},
        }

    # Include an attack with nonzero historical activity and a missing-context case.
    attack_ids = {label.event_id for label in labels if label.is_attack}
    target_index = next(
        index for index in range(len(events) - 1, 0, -1) if events[index].event_id in attack_ids
    )
    target = events[target_index]
    claim = Claim(
        row(target),
        UUID(int=999),
        [row(item) for item in events[:target_index]],
        target.occurred_at + timedelta(seconds=5),
        False,
        False,
    )
    result = runtime.score(claim)
    flags, scores = predictions(experiment, [features[target_index]])
    assert result.features == features[target_index].values
    assert result.ml_score == scores["ml"][0]
    assert result.rule_score == scores["rules"][0]
    assert result.flagged == flags["combined"][0]
    assert bool(result.signals) == result.flagged

    unknown = replace(target, user_id=None, account_key=None, source_ip=None, user_agent=None)
    claim = replace(claim, event=row(unknown), history=[], retention_truncated=True)
    result = runtime.score(claim)
    assert set(result.warnings) == {
        "missing_account",
        "missing_source_ip",
        "missing_browser",
        "cold_start",
        "limited_account_history",
        "truncated_retention_history",
    }
