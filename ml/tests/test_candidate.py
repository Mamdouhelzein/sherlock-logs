import json
import shutil

import pytest
from sklearn.ensemble import IsolationForest

from sherlock_ml import baselines, candidate, training
from sherlock_ml.artifacts import ARTIFACT_FILES, load_experiment, sha256
from sherlock_ml.candidate_data import HOLDOUT_SEEDS, CandidateData, generate_candidate
from sherlock_ml.events import Label
from sherlock_ml.features import build_features
from sherlock_ml.stress_data import PROFILES, project
from sherlock_ml.training import TrainingOptions, predictions


@pytest.fixture(scope="module")
def fitted(tmp_path_factory):
    output = tmp_path_factory.mktemp("candidate") / "experiment"
    report = candidate.train_candidate(
        output,
        users=10,
        history_days=7,
        evaluation_days=3,
        options=TrainingOptions(trees=16, sample_sizes=(16, 32)),
    )
    return output, report


@pytest.mark.parametrize("profile", PROFILES)
def test_candidate_scenarios_are_deterministic_local_and_label_free(profile):
    config = CandidateData("holdout", 5501, profile, users=10, history_days=7, evaluation_days=3)
    events, labels = generate_candidate(config)
    assert (events, labels) == generate_candidate(config)
    assert events == sorted(events, key=lambda event: (event.occurred_at, event.event_id))
    assert len({event.event_id for event in events}) == len(events)
    assert all(config.start <= event.occurred_at < config.end for event in events)
    assert all(event.source_ip is None and event.user_agent is None for event in events)
    assert all(
        "is_attack" not in event.record() and "scenario" not in event.record() for event in events
    )
    assert all(
        not label.is_attack
        for event, label in zip(events, labels, strict=True)
        if event.occurred_at < config.evaluation_start
    )
    visible = project(events, "local_guard")
    rows = build_features(visible)
    assert rows and all(len(row.vector()) == 15 for row in rows)
    if profile in {"evasive", "mixed"}:
        hidden = {event.event_id for event in events} - {event.event_id for event in visible}
        assert {
            label.event_id for label in labels if label.scenario == "attack_unknown_accounts"
        } <= hidden


def test_phase_population_ids_periods_and_reserved_seeds_are_separate():
    ids, periods = [], []
    for phase in ("train", "validation", "holdout"):
        config = CandidateData(phase, 5502, "routine", users=10)
        events, _ = generate_candidate(config)
        ids.append(
            {event.event_id for event in events}
            | {event.user_id for event in events if event.user_id}
        )
        periods.append((config.start, config.end))
    assert not ids[0] & ids[1] and not ids[1] & ids[2] and not ids[0] & ids[2]
    assert periods[0][1] < periods[1][0] and periods[1][1] < periods[2][0]
    for seed in HOLDOUT_SEEDS:
        with pytest.raises(ValueError, match="Reserved"):
            CandidateData("validation", seed, "routine")
    with pytest.raises(ValueError, match="benign"):
        CandidateData("train", 5502, "mixed")


def test_training_cannot_generate_final_data_or_filter_using_training_labels(tmp_path, monkeypatch):
    calls = []
    original = candidate.generate_candidate

    def relabel_training(config):
        assert config.phase != "holdout" and config.seed not in HOLDOUT_SEEDS
        calls.append((config.phase, config.profile))
        events, labels = original(config)
        if config.phase == "train":
            labels = [
                Label(label.event_id, True, "changed", "ignored-training-label") for label in labels
            ]
        return events, labels

    monkeypatch.setattr(candidate, "generate_candidate", relabel_training)
    seen = []
    original_fit = candidate.fit_candidate

    def fit(training_rows, *args):
        seen.extend(training_rows)
        return original_fit(training_rows, *args)

    monkeypatch.setattr(candidate, "fit_candidate", fit)
    report = candidate.train_candidate(
        tmp_path / "new",
        users=10,
        history_days=7,
        evaluation_days=3,
        options=TrainingOptions(trees=16, sample_sizes=(16,)),
    )
    assert len(calls) == 9 and report["holdout_generated"] is False
    assert len(seen) == report["provenance"]["training_rows"] > 0
    for manifest in report["provenance"]["datasets"]:
        if manifest["config"]["phase"] != "train":
            continue
        config = CandidateData(**manifest["config"])
        events, _ = original(config)
        expected = [
            row
            for row in build_features(project(events, "local_guard"))
            if row.occurred_at >= config.evaluation_start
        ]
        assert {row.event_id for row in expected} <= {row.event_id for row in seen}


def test_every_group_budget_and_selection_use_group_calibrated_metrics(fitted):
    _, report = fitted
    selection = report["selection"]
    assert (
        report["selected_samples"]
        == max(selection, key=lambda row: row["selection_key"])["max_samples"]
    )
    for entry in selection:
        assert set(entry["validation_by_workload"]) == set(PROFILES)
        for detectors in entry["validation_by_workload"].values():
            for name in ("ml", "rules", "statistical", "combined"):
                assert detectors[name]["false_alerts_per_1000_benign"] <= 5


def test_holdout_is_frozen_counts_hidden_attacks_and_preserves_model_bytes(
    fitted, tmp_path, monkeypatch
):
    output, trained = fitted
    model = output / "model"
    before = {name: sha256(model / name) for name in (*ARTIFACT_FILES, "metadata.json")}

    def prohibited(*args, **kwargs):
        raise AssertionError("Final evaluation cannot fit or calibrate")

    monkeypatch.setattr(IsolationForest, "fit", prohibited)
    monkeypatch.setattr(candidate, "fit_candidate", prohibited)
    monkeypatch.setattr(candidate, "calibrate", prohibited)
    monkeypatch.setattr(training, "fit_experiment", prohibited)
    monkeypatch.setattr(training, "calibrate", prohibited)
    monkeypatch.setattr(baselines, "calibrate", prohibited)
    report = candidate.evaluate_candidate(
        model,
        model,
        tmp_path / "holdout",
        candidate_pin=trained["candidate_bundle_version"],
        reference_pin=trained["candidate_bundle_version"],
        trusted=True,
        seeds=(5503,),
        users=10,
        history_days=7,
        evaluation_days=3,
    )
    assert before == {name: sha256(model / name) for name in before}
    assert report["fit_or_calibration_performed"] is False and report["live_model_changed"] is False
    evasive = next(run for run in report["runs"]["candidate"] if run["profile"] == "evasive")
    assert evasive["hidden_attack_events"] == 60
    observed = evasive["detectors"]["ml"]["observed"]
    end_to_end = evasive["detectors"]["ml"]["end_to_end"]
    assert end_to_end["attack_events"] - observed["attack_events"] == 60
    assert "true_negatives" not in end_to_end
    assert report["automatic_enforcement_approved"] is False
    path = tmp_path / "holdout" / "5503" / "evasive" / "candidate-predictions.jsonl"
    hidden = [row for row in map(json.loads, path.read_text().splitlines()) if not row["observed"]]
    assert all(row["ml_alert"] is None for row in hidden)
    with pytest.raises(ValueError, match="fresh"):
        candidate.evaluate_candidate(
            model, model, tmp_path / "holdout", candidate_pin="", reference_pin=""
        )


def test_untrusted_or_wrong_pin_cannot_load_or_generate_final_data(fitted, tmp_path, monkeypatch):
    model = fitted[0] / "model"

    def prohibited(*args, **kwargs):
        raise AssertionError("Must reject before loading/generating")

    monkeypatch.setattr(candidate, "load_experiment", prohibited)
    monkeypatch.setattr(candidate, "generate_candidate", prohibited)
    for trust in (False, True):
        with pytest.raises(ValueError):
            candidate.evaluate_candidate(
                model,
                model,
                tmp_path / "unused",
                candidate_pin="0" * 64,
                reference_pin="0" * 64,
                trusted=trust,
            )


def test_saved_candidate_round_trip_preserves_scores(fitted):
    output, report = fitted
    experiment, metadata = load_experiment(output / "model", trusted=True)
    config = CandidateData("validation", 5504, "mixed", users=10, history_days=7, evaluation_days=3)
    events, _ = generate_candidate(config)
    rows = build_features(project(events, "local_guard"))
    reloaded, _ = load_experiment(output / "model", trusted=True)
    assert predictions(experiment, rows) == predictions(reloaded, rows)
    assert metadata["provenance"]["observation_contract"] == "local_guard"
    assert experiment.thresholds == report["thresholds"]


def test_changed_generator_fingerprint_rejects_before_final_data(fitted, tmp_path, monkeypatch):
    model = tmp_path / "changed"
    shutil.copytree(fitted[0] / "model", model)
    metadata_path = model / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["provenance"]["generator_sha256"] = "0" * 64
    metadata_path.write_text(json.dumps(metadata))

    def prohibited(*args, **kwargs):
        raise AssertionError("Changed generator cannot produce final data")

    monkeypatch.setattr(candidate, "generate_candidate", prohibited)
    with pytest.raises(ValueError, match="code changed"):
        candidate.evaluate_candidate(
            model,
            model,
            tmp_path / "unused",
            candidate_pin=fitted[1]["candidate_bundle_version"],
            reference_pin=fitted[1]["candidate_bundle_version"],
            trusted=True,
        )
