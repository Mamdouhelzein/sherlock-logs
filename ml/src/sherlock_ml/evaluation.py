"""Evaluation labels enter here, after historical features and scores exist."""

from collections import defaultdict
from statistics import median

from sherlock_ml.baselines import (
    DEFAULT_RULES,
    RuleConfig,
    StatisticalBaseline,
    calibrate,
    rule_signals,
)
from sherlock_ml.events import Label
from sherlock_ml.features import Snapshot
from sherlock_ml.synthetic import Config


def partition(row: Snapshot, config: Config) -> str:
    if not config.start_at <= row.occurred_at < config.end:
        raise ValueError("Event falls outside the dataset date range")
    if row.occurred_at < config.train_end:
        return "train"
    return "validation" if row.occurred_at < config.validation_end else "test"


def metrics(rows: list[Snapshot], labels: dict[str, Label], decisions: list[bool]) -> dict:
    if len(rows) != len(decisions):
        raise ValueError("Predictions must align with events")
    positives = sum(labels[row.event_id].is_attack for row in rows)
    negatives = len(rows) - positives
    tp = sum(
        flag and labels[row.event_id].is_attack for row, flag in zip(rows, decisions, strict=True)
    )
    fp = sum(
        flag and not labels[row.event_id].is_attack
        for row, flag in zip(rows, decisions, strict=True)
    )
    incidents = defaultdict(list)
    by_scenario = defaultdict(lambda: {"events": 0, "alerts": 0})
    for row, flag in zip(rows, decisions, strict=True):
        label = labels[row.event_id]
        by_scenario[label.scenario]["events"] += 1
        by_scenario[label.scenario]["alerts"] += int(flag)
        if label.incident_id:
            incidents[label.incident_id].append((row.occurred_at, flag))
    delays = []
    for events in incidents.values():
        alert_times = [at for at, flag in events if flag]
        if alert_times:
            delays.append((min(alert_times) - min(at for at, _ in events)).total_seconds())
    return {
        "events": len(rows),
        "attack_events": positives,
        "benign_events": negatives,
        "attack_prevalence": positives / len(rows) if rows else None,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": positives - tp,
        "true_negatives": negatives - fp,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / positives if positives else None,
        "false_alerts_per_1000_benign": fp * 1000 / negatives if negatives else None,
        "incidents": len(incidents),
        "detected_incidents": len(delays),
        "incident_recall": len(delays) / len(incidents) if incidents else None,
        "median_time_to_alert_seconds": median(delays) if delays else None,
        "by_scenario": dict(sorted(by_scenario.items())),
        "false_positive_examples": [
            row.event_id
            for row, flag in zip(rows, decisions, strict=True)
            if flag and not labels[row.event_id].is_attack
        ][:5],
        "missed_attack_examples": [
            row.event_id
            for row, flag in zip(rows, decisions, strict=True)
            if not flag and labels[row.event_id].is_attack
        ][:5],
    }


def evaluate(
    rows: list[Snapshot],
    labels: list[Label],
    config: Config,
    *,
    false_alert_budget: float = 5.0,
    rules: RuleConfig = DEFAULT_RULES,
    reference: tuple[StatisticalBaseline, float] | None = None,
) -> tuple[dict, StatisticalBaseline, float]:
    by_id = {label.event_id: label for label in labels}
    row_ids = {row.event_id for row in rows}
    if len(by_id) != len(labels) or len(row_ids) != len(rows) or set(by_id) != row_ids:
        raise ValueError("Labels and features must have exactly matching unique IDs")
    groups = {
        name: [row for row in rows if partition(row, config) == name]
        for name in ("train", "validation", "test")
    }
    if any(not group for group in groups.values()):
        raise ValueError("Every chronological partition must contain events")
    if reference is None:
        model = StatisticalBaseline.fit(groups["train"])
        threshold = calibrate(
            [model.score(row) for row in groups["validation"] if not by_id[row.event_id].is_attack],
            false_alert_budget,
        )
    else:
        model, threshold = reference
    report = {
        "synthetic_only": True,
        "scope": "Offline baselines; no trained ML model and no production effectiveness claim.",
        "calibration": "frozen reference" if reference else "benign validation events only",
        "false_alert_budget_per_1000_benign": false_alert_budget,
        "threshold": threshold,
        "rules": {},
        "statistical": {},
    }
    for name, group in groups.items():
        report["rules"][name] = metrics(
            group, by_id, [bool(rule_signals(row, rules)) for row in group]
        )
        report["statistical"][name] = metrics(
            group, by_id, [model.score(row) > threshold for row in group]
        )
    return report, model, threshold
