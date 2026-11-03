"""Causal feature snapshots. Labels are not accepted by this module."""

import math
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from sherlock_ml.events import Event

FEATURE_VERSION = "login-history-v1"
FEATURE_NAMES = (
    "current_failure",
    "account_failures_15m",
    "account_attempts_15m",
    "source_attempts_5m",
    "source_accounts_5m",
    "source_failure_ratio_5m",
    "account_history_30d",
    "account_successes_30d",
    "browser_novel",
    "hour_deviation",
    "seconds_since_previous",
    "has_previous",
    "account_missing",
    "source_missing",
    "browser_missing",
)


def browser_family(agent: str | None) -> str | None:
    if not agent:
        return None
    for family, pattern in (
        ("edge", r"(?:Edg|Edge)/"),
        ("firefox", r"Firefox/"),
        ("chrome", r"(?:Chrome|CriOS)/"),
        ("safari", r"Safari/"),
    ):
        if re.search(pattern, agent, re.IGNORECASE):
            return family
    return "other"


@dataclass(frozen=True)
class Snapshot:
    # Metadata for joins/splits only; vector() is the exclusive model input.
    event_id: str
    occurred_at: datetime
    values: dict[str, float]

    def vector(self) -> list[float]:
        if set(self.values) != set(FEATURE_NAMES):
            raise ValueError("Unexpected feature schema")
        result = [self.values[name] for name in FEATURE_NAMES]
        if not all(math.isfinite(value) for value in result):
            raise ValueError("Features must be finite")
        return result


def build_features(events: list[Event]) -> list[Snapshot]:
    ordered = sorted(events, key=lambda event: (event.occurred_at, event.event_id))
    if len({event.event_id for event in ordered}) != len(ordered):
        raise ValueError("Duplicate event IDs must be resolved before feature extraction")
    accounts: dict[str, deque[Event]] = defaultdict(deque)
    sources: dict[str, deque[Event]] = defaultdict(deque)
    snapshots = []
    for event in ordered:
        at = event.occurred_at
        history = accounts[event.account] if event.account else deque()
        source = sources[event.source_ip] if event.source_ip else deque()
        while history and history[0].occurred_at <= at - timedelta(days=30):
            history.popleft()
        while source and source[0].occurred_at <= at - timedelta(minutes=5):
            source.popleft()
        recent = [item for item in history if item.occurred_at > at - timedelta(minutes=15)]
        successes = [item for item in history if item.outcome == "success"]
        browser = browser_family(event.user_agent)
        known_browsers = {browser_family(item.user_agent) for item in successes} - {None}
        # Circular mean handles midnight. No history or an ambiguous mean means
        # no deviation evidence, rather than fabricating a normal login hour.
        sine = sum(math.sin(hour_angle(item.occurred_at)) for item in successes)
        cosine = sum(math.cos(hour_angle(item.occurred_at)) for item in successes)
        deviation = 0.0
        if math.hypot(sine, cosine) > 1e-8:
            distance = abs(hour_angle(at) - math.atan2(sine, cosine)) % (2 * math.pi)
            deviation = min(distance, 2 * math.pi - distance) * 12 / math.pi
        values = {
            "current_failure": float(event.outcome == "failure"),
            "account_failures_15m": float(sum(item.outcome == "failure" for item in recent)),
            "account_attempts_15m": float(len(recent)),
            "source_attempts_5m": float(len(source)),
            "source_accounts_5m": float(len({item.account for item in source if item.account})),
            "source_failure_ratio_5m": sum(item.outcome == "failure" for item in source)
            / len(source)
            if source
            else 0.0,
            "account_history_30d": float(len(history)),
            "account_successes_30d": float(len(successes)),
            "browser_novel": float(
                bool(browser and known_browsers and browser not in known_browsers)
            ),
            "hour_deviation": deviation,
            "seconds_since_previous": (at - history[-1].occurred_at).total_seconds()
            if history
            else 0.0,
            "has_previous": float(bool(history)),
            "account_missing": float(event.account is None),
            "source_missing": float(event.source_ip is None),
            "browser_missing": float(browser is None),
        }
        snapshot = Snapshot(event.event_id, at, values)
        snapshot.vector()
        snapshots.append(snapshot)
        # Update AFTER the snapshot: the current outcome cannot count as a past failure.
        if event.account:
            history.append(event)
        if event.source_ip:
            source.append(event)
    return snapshots


def hour_angle(at: datetime) -> float:
    return (at.hour + at.minute / 60 + at.second / 3600) * math.pi / 12
