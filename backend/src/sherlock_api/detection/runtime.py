"""Shared offline/online feature code and the pinned, trusted local model artifact."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sherlock_api.detection.store import Claim


def artifact_version(path: Path) -> str:
    metadata = json.loads((path / "metadata.json").read_text())
    parts = [
        metadata["sha256"][name]
        for name in ("model.joblib", "experiment.json", "feature_schema.json")
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


@dataclass
class Score:
    features: dict[str, float]
    ml_score: float
    rule_score: float
    signals: list[str]
    warnings: list[str]
    flagged: bool


class ModelRuntime:
    def __init__(self, path: Path, expected_version: str, *, trusted: bool):
        if not trusted or not expected_version or artifact_version(path) != expected_version:
            raise ValueError("A trusted, explicitly pinned local model is required")
        from sherlock_ml.artifacts import load_experiment
        from sherlock_ml.features import FEATURE_VERSION

        self.experiment, metadata = load_experiment(path, trusted=True)
        self.version = expected_version
        self.label = metadata["model_id"]
        self.digests = metadata["sha256"]
        self.feature_version = FEATURE_VERSION
        self.ml_threshold = self.experiment.thresholds["combined_ml"]
        self.rule_threshold = self.experiment.thresholds["combined_rules"]

    def score(self, claim: Claim) -> Score:
        from sherlock_ml.events import Event
        from sherlock_ml.features import build_features
        from sherlock_ml.training import predictions

        def event(row):
            at = row["occurred_at"]
            return Event(
                event_id=str(row["id"]),
                occurred_at=datetime.fromisoformat(at) if isinstance(at, str) else at,
                outcome=row["outcome"],
                user_id=str(row["user_id"]) if row["user_id"] else None,
                account_key=row["account_key"],
                source_ip=row["source_ip"],
                user_agent=row["user_agent"],
            )

        target = event(claim.event)
        snapshot = build_features([*[event(row) for row in claim.history], target])[-1]
        if snapshot.event_id != target.event_id:
            raise ValueError("History must precede the target event")
        decisions, scores = predictions(self.experiment, [snapshot])
        values = snapshot.values
        signals = []
        rules = self.experiment.rules
        for name, value in (
            ("account_failure_burst", values["account_failures_15m"] / rules.account_failures),
            ("source_attempt_burst", values["source_attempts_5m"] / rules.source_attempts),
            ("source_account_spread", values["source_accounts_5m"] / rules.source_accounts),
        ):
            if value > self.rule_threshold:
                signals.append(name)
        if (
            values["current_failure"] == 0
            and values["browser_novel"] == 1
            and values["account_successes_30d"] >= rules.minimum_success_history
            and values["hour_deviation"] / rules.unusual_hour > self.rule_threshold
        ):
            signals.append("unfamiliar_browser_and_hour")
        if scores["ml"][0] > self.ml_threshold:
            signals.append("ml_outlier")
        warnings = [
            name
            for name, condition in (
                ("missing_account", values["account_missing"] == 1),
                ("missing_source_ip", values["source_missing"] == 1),
                ("missing_browser", values["browser_missing"] == 1),
                ("cold_start", values["has_previous"] == 0),
                ("limited_account_history", values["account_successes_30d"] < 5),
                ("truncated_retention_history", claim.retention_truncated),
                ("cooldown_rejection", claim.event.get("rejection_reason") == "cooldown_rejected"),
            )
            if condition
        ]
        return Score(
            values, scores["ml"][0], scores["rules"][0], signals, warnings, decisions["combined"][0]
        )
