from dataclasses import asdict, replace

import pytest

from sherlock_ml.events import Event
from sherlock_ml.synthetic import Config, generate


def small_config(**changes):
    return Config(users=15, days=12, train_days=6, validation_days=3, attack_episodes=18, **changes)


def test_reproduces_events_and_labels_and_varies_with_seed():
    config = small_config()
    events, labels = generate(config)
    assert (events, labels) == generate(config)
    assert events != generate(replace(config, seed=43))[0]
    assert len({event.event_id for event in events}) == len(events)
    assert events == sorted(events, key=lambda event: (event.occurred_at, event.event_id))
    assert {label.scenario for label in labels} >= {
        "benign_login",
        "benign_mistake",
        "benign_new_browser",
        "benign_schedule_change",
        "brute_force",
        "password_spray",
        "suspicious_success",
    }
    assert [event.event_id for event in events] == [label.event_id for label in labels]
    assert all(config.start_at <= event.occurred_at < config.end for event in events)
    assert all(
        "is_attack" not in event.record()
        and "scenario" not in event.record()
        and "incident_id" not in event.record()
        for event in events
    )
    assert any(event.user_id is None and event.account_key is not None for event in events)


def test_can_generate_entirely_benign_data():
    events, labels = generate(replace(small_config(), attack_episodes=0))
    assert events and not any(label.is_attack for label in labels)
    assert not any(label.incident_id for label in labels)


@pytest.mark.parametrize(
    "changes",
    [
        {"users": 1},
        {"days": 5},
        {"train_days": 0},
        {"validation_days": 0},
        {"train_days": 11},
        {"attack_episodes": -1},
        {"attack_scale": 0},
        {"start": "tomorrow"},
    ],
)
def test_rejects_invalid_generation_settings(changes):
    with pytest.raises(ValueError):
        Config(**{**asdict(small_config()), **changes})


def test_observable_event_contract_rejects_labels_and_normalizes_time():
    events, _ = generate(small_config())
    record = events[0].record()
    with pytest.raises(TypeError):
        Event.from_record({**record, "is_attack": True})
    assert Event.from_record(record) == events[0]
    with pytest.raises(ValueError):
        Event.from_record({**record, "occurred_at": "2026-01-01T00:00:00"})
