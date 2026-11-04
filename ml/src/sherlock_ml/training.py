"""Training and frozen evaluation. Only train/validation inputs enter model selection."""

import math
from dataclasses import asdict, dataclass

import numpy as np
from sklearn.ensemble import IsolationForest

from sherlock_ml.baselines import (
    DEFAULT_RULES,
    RuleConfig,
    StatisticalBaseline,
    calibrate,
    rule_signals,
)
from sherlock_ml.evaluation import metrics, partition
from sherlock_ml.events import Label
from sherlock_ml.features import FEATURE_NAMES, Snapshot
from sherlock_ml.synthetic import Config


@dataclass(frozen=True)
class TrainingOptions:
    seed: int = 42
    trees: int = 200
    sample_sizes: tuple[int, ...] = (128, 256, 512)
    false_alert_budget: float = 5.0

    def __post_init__(self):
        if not 0 <= self.seed < 2**32 or not 16 <= self.trees <= 1000:
            raise ValueError("Invalid training seed or tree count")
        if (
            not self.sample_sizes
            or len(self.sample_sizes) > 8
            or any(not 2 <= size <= 4096 for size in self.sample_sizes)
        ):
            raise ValueError("Use up to eight sample sizes between 2 and 4096")
        if not math.isfinite(self.false_alert_budget) or not 0 <= self.false_alert_budget < 1000:
            raise ValueError("Invalid false-alert budget")


@dataclass
class Experiment:
    forest: IsolationForest
    statistical: StatisticalBaseline
    thresholds: dict[str, float]
    options: TrainingOptions
    rules: RuleConfig
    selection: list[dict]

    def validate(self):
        expected = {"ml", "rules", "statistical", "combined_ml", "combined_rules"}
        if set(self.thresholds) != expected or not all(
            math.isfinite(value) and value >= 0 for value in self.thresholds.values()
        ):
            raise ValueError("Invalid operating thresholds")
        if type(self.forest) is not IsolationForest or self.forest.n_features_in_ != len(
            FEATURE_NAMES
        ):
            raise ValueError("Unexpected fitted model")


def matrix(rows: list[Snapshot]) -> np.ndarray:
    if not rows:
        raise ValueError("Feature partition is empty")
    values = np.asarray([row.vector() for row in rows], dtype=np.float32)
    if values.shape != (len(rows), len(FEATURE_NAMES)) or not np.isfinite(values).all():
        raise ValueError("Feature matrix is invalid")
    return values


def anomaly_scores(forest: IsolationForest, values: np.ndarray) -> list[float]:
    # sklearn gives lower scores to anomalies. Negation makes larger scores riskier.
    result = -forest.score_samples(values)
    if not np.isfinite(result).all():
        raise ValueError("Non-finite model scores")
    return [float(score) for score in result]


def rule_score(row: Snapshot, rules: RuleConfig = DEFAULT_RULES) -> float:
    values = row.values
    unusual_success = (
        values["current_failure"] == 0
        and values["account_successes_30d"] >= rules.minimum_success_history
        and values["browser_novel"] == 1
    )
    return max(
        values["account_failures_15m"] / rules.account_failures,
        values["source_attempts_5m"] / rules.source_attempts,
        values["source_accounts_5m"] / rules.source_accounts,
        values["hour_deviation"] / rules.unusual_hour if unusual_success else 0.0,
    )


def aligned(rows: list[Snapshot], labels: list[Label]) -> dict[str, Label]:
    by_id = {label.event_id: label for label in labels}
    ids = {row.event_id for row in rows}
    if len(by_id) != len(labels) or len(ids) != len(rows) or ids != set(by_id):
        raise ValueError("Features and labels must have matching unique IDs")
    return by_id


def fit_experiment(
    training: list[Snapshot],
    validation: list[Snapshot],
    validation_labels: list[Label],
    options: TrainingOptions,
) -> Experiment:
    """No test rows, training labels, or test labels are accepted by this boundary."""
    if len(training) < 2 or not validation:
        raise ValueError("Insufficient training/validation data")
    if max(row.occurred_at for row in training) >= min(row.occurred_at for row in validation):
        raise ValueError("Training must strictly precede validation")
    if {row.event_id for row in training} & {row.event_id for row in validation}:
        raise ValueError("Partitions must not overlap")
    train_values = matrix(training)
    validation_values = matrix(validation)
    labels = aligned(validation, validation_labels)
    benign = [not labels[row.event_id].is_attack for row in validation]
    if not any(benign):
        raise ValueError("Need benign validation events for calibration")

    def threshold(scores, budget):
        return calibrate(
            [score for score, keep in zip(scores, benign, strict=True) if keep], budget
        )

    candidates = []
    selection = []
    for samples in sorted({min(size, len(training)) for size in options.sample_sizes}):
        forest = IsolationForest(
            n_estimators=options.trees,
            max_samples=samples,
            contamination="auto",
            random_state=options.seed,
            n_jobs=1,
        )
        forest.fit(train_values)  # All training events; no oracle label filtering.
        scores = anomaly_scores(forest, validation_values)
        cutoff = threshold(scores, options.false_alert_budget)
        result = metrics(validation, labels, [score > cutoff for score in scores])
        key = (
            result["incident_recall"] or 0,
            result["recall"] or 0,
            -(result["false_alerts_per_1000_benign"] or 0),
            -samples,
        )
        candidates.append((key, forest, scores, cutoff))
        selection.append(
            {
                "max_samples": samples,
                "trees": options.trees,
                "threshold": cutoff,
                "validation": result,
            }
        )
    _, forest, ml_scores, ml_cutoff = max(candidates, key=lambda candidate: candidate[0])
    statistical = StatisticalBaseline.fit(training)
    rule_scores = [rule_score(row) for row in validation]
    stat_scores = [statistical.score(row) for row in validation]
    thresholds = {
        "ml": ml_cutoff,
        "rules": threshold(rule_scores, options.false_alert_budget),
        "statistical": threshold(stat_scores, options.false_alert_budget),
        # Union bound: each branch gets half of the combined false-alert budget.
        "combined_ml": threshold(ml_scores, options.false_alert_budget / 2),
        "combined_rules": threshold(rule_scores, options.false_alert_budget / 2),
    }
    result = Experiment(forest, statistical, thresholds, options, DEFAULT_RULES, selection)
    result.validate()
    return result


def predictions(experiment: Experiment, rows: list[Snapshot]) -> tuple[dict, dict]:
    experiment.validate()
    ml_scores = anomaly_scores(experiment.forest, matrix(rows))
    rules = [rule_score(row, experiment.rules) for row in rows]
    stats = [experiment.statistical.score(row) for row in rows]
    cutoffs = experiment.thresholds
    decisions = {
        "ml": [score > cutoffs["ml"] for score in ml_scores],
        "rules": [score > cutoffs["rules"] for score in rules],
        "statistical": [score > cutoffs["statistical"] for score in stats],
        "combined": [
            ml > cutoffs["combined_ml"] or rule > cutoffs["combined_rules"]
            for ml, rule in zip(ml_scores, rules, strict=True)
        ],
        "fixed_rules_reference": [bool(rule_signals(row, experiment.rules)) for row in rows],
    }
    return decisions, {"ml": ml_scores, "rules": rules, "statistical": stats}


def evaluate_experiment(
    experiment: Experiment,
    rows: list[Snapshot],
    labels: list[Label],
    config: Config,
) -> tuple[dict, list[dict]]:
    labels_by_id = aligned(rows, labels)
    decisions, scores = predictions(experiment, rows)
    groups = {
        name: [index for index, row in enumerate(rows) if partition(row, config) == name]
        for name in ("train", "validation", "test")
    }
    if any(not indices for indices in groups.values()):
        raise ValueError("Every partition must contain events")
    report = {
        "synthetic_only": True,
        "connected_to_live_auth": False,
        "score_meaning": "Higher means more unusual; not a probability of compromise.",
        "false_alert_budget_per_1000_benign": experiment.options.false_alert_budget,
        "thresholds": experiment.thresholds,
        "selected_parameters": {
            "trees": experiment.forest.n_estimators,
            "max_samples": experiment.forest.max_samples_,
        },
        "detectors": {},
    }
    for detector, flags in decisions.items():
        report["detectors"][detector] = {
            name: metrics(
                [rows[index] for index in indices],
                labels_by_id,
                [flags[index] for index in indices],
            )
            for name, indices in groups.items()
        }
    output = []
    for index, row in enumerate(rows):
        label = labels_by_id[row.event_id]
        output.append(
            {
                "event_id": row.event_id,
                "occurred_at": row.occurred_at.isoformat(),
                "split": partition(row, config),
                "is_attack": label.is_attack,
                "scenario": label.scenario,
                **{f"{name}_score": values[index] for name, values in scores.items()},
                **{f"{name}_alert": values[index] for name, values in decisions.items()},
            }
        )
    return report, output


def fit_from_partitions(
    rows: list[Snapshot],
    labels: list[Label],
    config: Config,
    options: TrainingOptions,
) -> Experiment:
    labels_by_id = aligned(rows, labels)
    training = [row for row in rows if partition(row, config) == "train"]
    validation = [row for row in rows if partition(row, config) == "validation"]
    return fit_experiment(
        training, validation, [labels_by_id[row.event_id] for row in validation], options
    )


def experiment_config(experiment: Experiment) -> dict:
    return {
        "training_options": asdict(experiment.options),
        "rules": asdict(experiment.rules),
        "thresholds": experiment.thresholds,
        "statistical": asdict(experiment.statistical),
        "selection_policy": "validation episode recall, event recall, "
        "fewer false alerts, smaller sample size",
        "combined_policy": "OR of two branches, each calibrated at half the budget",
    }
