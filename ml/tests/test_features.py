import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from sherlock_ml.events import Event
from sherlock_ml.features import FEATURE_NAMES, Snapshot, build_features

START = datetime(2026, 1, 1, 8, tzinfo=UTC)
USER = str(UUID(int=101))


def event(number, seconds=0, **changes):
    values = dict(
        event_id=str(UUID(int=number)),
        occurred_at=START + timedelta(seconds=seconds),
        outcome="failure",
        user_id=USER,
        source_ip="192.0.2.1",
        user_agent="Mozilla/5.0 Firefox/132.0",
    )
    return Event(**{**values, **changes})


def test_current_event_is_excluded_and_ties_have_stable_order():
    first = event(1)
    second = event(2)
    left, right = build_features([second, first])
    assert left.values["account_failures_15m"] == 0
    assert right.values["account_failures_15m"] == 1
    assert right.values["source_attempts_5m"] == 1
    assert [left, right] == build_features([first, second])
    with pytest.raises(ValueError, match="Duplicate"):
        build_features([first, first])


def test_windows_expire_at_their_left_boundaries():
    rows = build_features([event(1), event(2, 300), event(3, 900), event(4, 30 * 86400 + 900)])
    assert rows[1].values["source_attempts_5m"] == 0
    assert rows[2].values["account_failures_15m"] == 1
    assert rows[3].values["account_history_30d"] == 0


def test_future_appends_cannot_change_earlier_features():
    prefix = [event(1, outcome="success"), event(2, 60), event(3, 120)]
    future = [event(number, 1000 + number) for number in range(4, 100)]
    assert build_features(prefix) == build_features([*reversed(future), *prefix])[: len(prefix)]


def test_accounts_do_not_share_history_even_when_their_source_is_shared():
    rows = build_features(
        [
            event(1),
            event(2, 10, user_id=str(UUID(int=102))),
            event(3, 20),
        ]
    )
    assert rows[1].values["account_failures_15m"] == 0
    assert rows[1].values["source_attempts_5m"] == 1
    assert rows[2].values["account_failures_15m"] == 1
    assert rows[2].values["source_accounts_5m"] == 2


def test_missing_context_is_explicit_and_not_shared_between_unknown_accounts():
    rows = build_features(
        [
            event(1, user_id=None, source_ip=None, user_agent=None),
            event(2, 1, user_id=None, source_ip=None, user_agent=None),
        ]
    )
    for row in rows:
        assert row.values["account_missing"] == 1
        assert row.values["source_missing"] == 1
        assert row.values["browser_missing"] == 1
        assert row.values["has_previous"] == 0
        assert row.values["hour_deviation"] == 0
        assert all(math.isfinite(value) for value in row.vector())


def test_browser_familiarity_uses_previous_successes_and_circular_hours():
    first = event(1, occurred_at=datetime(2026, 1, 1, 23, 50, tzinfo=UTC), outcome="success")
    second = event(
        2,
        occurred_at=datetime(2026, 1, 2, 0, 10, tzinfo=UTC),
        user_agent="Mozilla/5.0 Chrome/130.0 Safari/537.36",
    )
    third = replace(
        second, event_id=str(UUID(int=3)), occurred_at=second.occurred_at + timedelta(seconds=5)
    )
    rows = build_features([third, second, first])
    assert rows[1].values["browser_novel"] == 1
    assert rows[2].values["browser_novel"] == 1  # A failed attempt does not establish trust.
    assert rows[1].values["hour_deviation"] == pytest.approx(1 / 3)
    assert rows[0].values["browser_novel"] == 0  # Explicit cold start.


def test_utc_conversion_and_feature_allowlist_exclude_identifiers():
    local = event(1, occurred_at=datetime(2026, 1, 1, 10, tzinfo=timezone(timedelta(hours=2))))
    assert local.occurred_at == START
    row = build_features([local])[0]
    assert set(row.values) == set(FEATURE_NAMES)
    for forbidden in ("user_id", "source_ip", "user_agent", "event_id", "scenario", "is_attack"):
        assert forbidden not in FEATURE_NAMES
    with pytest.raises(ValueError):
        Snapshot(row.event_id, row.occurred_at, {**row.values, "scenario": 1}).vector()
    with pytest.raises(ValueError):
        Snapshot(
            row.event_id, row.occurred_at, {**row.values, "hour_deviation": float("nan")}
        ).vector()
