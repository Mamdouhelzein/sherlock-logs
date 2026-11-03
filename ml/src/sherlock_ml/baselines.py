"""Fixed security rules and a robust statistical reference; no trained ML model yet."""

import math
from dataclasses import asdict, dataclass
from statistics import median

from sherlock_ml.features import FEATURE_NAMES, FEATURE_VERSION, Snapshot


@dataclass(frozen=True)
class RuleConfig:
    account_failures: int = 5
    source_attempts: int = 20
    source_accounts: int = 8
    unusual_hour: float = 4.0
    minimum_success_history: int = 5

    def __post_init__(self):
        if (
            min(
                self.account_failures,
                self.source_attempts,
                self.source_accounts,
                self.minimum_success_history,
            )
            < 1
            or not 0 < self.unusual_hour <= 12
        ):
            raise ValueError("Invalid rule thresholds")


DEFAULT_RULES = RuleConfig()


def rule_signals(snapshot: Snapshot, config: RuleConfig = DEFAULT_RULES) -> list[str]:
    snapshot.vector()
    values = snapshot.values
    signals = []
    if values["account_failures_15m"] >= config.account_failures:
        signals.append("account_failure_burst")
    if values["source_attempts_5m"] >= config.source_attempts:
        signals.append("source_attempt_burst")
    if values["source_accounts_5m"] >= config.source_accounts:
        signals.append("source_account_spread")
    if (
        values["current_failure"] == 0
        and values["account_successes_30d"] >= config.minimum_success_history
        and values["browser_novel"] == 1
        and values["hour_deviation"] >= config.unusual_hour
    ):
        signals.append("unfamiliar_browser_and_hour")
    return signals


STAT_FEATURES = (
    "account_failures_15m",
    "source_attempts_5m",
    "source_accounts_5m",
    "hour_deviation",
)


@dataclass(frozen=True)
class StatisticalBaseline:
    centers: dict[str, float]
    scales: dict[str, float]

    def __post_init__(self):
        if set(self.centers) != set(STAT_FEATURES) or set(self.scales) != set(STAT_FEATURES):
            raise ValueError("Unexpected statistical feature schema")
        if not all(math.isfinite(value) for value in self.centers.values()) or not all(
            math.isfinite(value) and value >= 1 for value in self.scales.values()
        ):
            raise ValueError("Invalid statistical parameters")

    @classmethod
    def fit(cls, training: list[Snapshot]) -> "StatisticalBaseline":
        if not training:
            raise ValueError("Training partition is empty")
        for row in training:
            row.vector()
        centers = {}
        scales = {}
        for name in STAT_FEATURES:
            values = [row.values[name] for row in training]
            centers[name] = median(values)
            # A unit floor avoids infinite scores for sparse count features.
            scales[name] = max(1.0, 1.4826 * median(abs(x - centers[name]) for x in values))
        return cls(centers, scales)

    def score(self, snapshot: Snapshot) -> float:
        snapshot.vector()
        return max(
            0.0,
            *(
                max(0.0, snapshot.values[name] - self.centers[name]) / self.scales[name]
                for name in STAT_FEATURES
            ),
        )


def calibrate(benign_validation_scores: list[float], false_alert_budget: float) -> float:
    """Use validation negatives only; ties at the threshold are not alerts."""
    if not 0 <= false_alert_budget < 1000 or not benign_validation_scores:
        raise ValueError("Need benign validation data and a budget from 0 to below 1000")
    if not all(math.isfinite(value) for value in benign_validation_scores):
        raise ValueError("Calibration scores must be finite")
    ordered = sorted(benign_validation_scores)
    allowed = math.floor(len(ordered) * false_alert_budget / 1000)
    return ordered[len(ordered) - allowed - 1]


def reference_record(model: StatisticalBaseline, threshold: float, rules: RuleConfig) -> dict:
    return {
        "kind": "robust-statistical-baseline",
        "feature_version": FEATURE_VERSION,
        "feature_names": list(FEATURE_NAMES),
        "centers": model.centers,
        "scales": model.scales,
        "threshold": threshold,
        "decision": "score > threshold",
        "rules": asdict(rules),
    }
