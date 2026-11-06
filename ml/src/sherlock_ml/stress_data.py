"""Independent fictional stress scenarios. No fitting, labels-as-features or network I/O."""

import random
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sherlock_ml.events import Event, Label

PROFILES = ("routine", "legitimate_bursts", "behavior_drift", "fast_guessing", "evasive", "mixed")
VIEWS = ("complete", "local_guard", "failure_logs")
AGENTS = ("Mozilla/5.0 Chrome/131.0 Safari/537.36", "Mozilla/5.0 Firefox/133.0")


@dataclass(frozen=True)
class StressConfig:
    seed: int = 1101
    users: int = 100
    history_days: int = 35
    evaluation_days: int = 14
    profile: str = "mixed"

    def __post_init__(self):
        if not 1000 <= self.seed < 2**32 or not 10 <= self.users <= 500:
            raise ValueError("Use a fresh seed >=1000 and 10–500 accounts")
        if not 7 <= self.history_days <= 60 or not 3 <= self.evaluation_days <= 60:
            raise ValueError("Use bounded warm-up and evaluation windows")
        if self.profile not in PROFILES:
            raise ValueError("Unknown stress workload")

    @property
    def start(self):
        return datetime(2026, 7, 1, tzinfo=UTC)

    @property
    def evaluation_start(self):
        return self.start + timedelta(days=self.history_days)

    @property
    def end(self):
        return self.evaluation_start + timedelta(days=self.evaluation_days)


def generate_stress(config: StressConfig) -> tuple[list[Event], list[Label]]:
    # Separate streams keep background people/habits paired across workloads.
    people_rng = random.Random(config.seed)
    scenario_rng = random.Random(config.seed + 100000)
    ids = random.Random(config.seed + 200000)
    events, labels = [], []

    def uid():
        return str(UUID(int=ids.getrandbits(128), version=4))

    # More than 254 accounts still use only documentation networks.
    people = [
        (uid(), people_rng.uniform(7, 20), people_rng.randrange(2), f"192.0.2.{index % 254 + 1}")
        for index in range(config.users)
    ]

    def add(at, outcome, person, source, browser, scenario, incident=None):
        event = Event(
            uid(),
            at,
            outcome,
            person[0] if person else None,
            source_ip=source,
            user_agent=AGENTS[browser],
        )
        events.append(event)
        labels.append(Label(event.event_id, incident is not None, scenario, incident))

    drift = config.profile in {"behavior_drift", "mixed"}
    bursts = config.profile in {"legitimate_bursts", "mixed"}
    for day in range(config.history_days + config.evaluation_days):
        date = config.start + timedelta(days=day)
        evaluating = day >= config.history_days
        for index, person in enumerate(people):
            # A new cohort has no pre-evaluation account history.
            if drift and index >= config.users * 0.85 and not evaluating:
                continue
            if people_rng.random() > (0.55 if date.weekday() >= 5 else 0.85):
                continue
            hour = person[1] + people_rng.gauss(0, 0.5)
            scenario = "benign_routine"
            if drift and evaluating and index % 5 == 0:
                hour += 6
                scenario = "benign_schedule_shift"
            browser = person[2]
            if drift and day >= config.history_days + 2:
                browser = 1 - browser
                scenario = "benign_browser_rollout"
            if drift and index >= config.users * 0.85:
                scenario = "benign_new_account"
            at = max(date + timedelta(minutes=1), date + timedelta(seconds=int((hour % 24) * 3600)))
            if people_rng.random() < 0.15:
                add(
                    at - timedelta(seconds=25), "failure", person, person[3], browser, "benign_typo"
                )
            if people_rng.random() < 0.01:
                add(
                    at - timedelta(seconds=40),
                    "failure",
                    None,
                    person[3],
                    browser,
                    "benign_unknown_identifier",
                )
            add(at, "success", person, person[3], browser, scenario)

        if not evaluating:
            continue
        episode_day = day - config.history_days
        if bursts:
            for index, person in enumerate(people[: min(40, config.users)]):
                at = date + timedelta(hours=9, seconds=index * 3)
                add(at, "success", person, "198.51.100.10", person[2], "benign_shared_nat_rush")
            person = people[episode_day % len(people)]
            for index in range(7):
                add(
                    date + timedelta(hours=12, seconds=index * 20),
                    "failure",
                    person,
                    person[3],
                    person[2],
                    "benign_stale_password" if index < 5 else "benign_cooldown_retry",
                )
            add(
                date + timedelta(hours=12, minutes=18),
                "success",
                person,
                person[3],
                person[2],
                "benign_recovered_password",
            )

        if config.profile in {"fast_guessing", "mixed"}:
            person = scenario_rng.choice(people)
            for index in range(8):
                add(
                    date + timedelta(hours=15, seconds=index * 15),
                    "failure",
                    person,
                    "203.0.113.20",
                    person[2],
                    "attack_fast_guessing",
                    f"fast-{episode_day}",
                )
        if config.profile in {"evasive", "mixed"}:
            person = scenario_rng.choice(people)
            for index in range(12):
                add(
                    date + timedelta(hours=1, minutes=index * 20),
                    "failure",
                    person,
                    f"203.0.113.{index + 30}",
                    person[2],
                    "attack_slow_guessing",
                    f"slow-{episode_day}",
                )
            for index, target in enumerate(scenario_rng.sample(people, min(20, config.users))):
                add(
                    date + timedelta(hours=16, minutes=index * 2),
                    "failure",
                    target,
                    f"198.51.100.{index + 50}",
                    target[2],
                    "attack_distributed_spray",
                    f"distributed-{episode_day}",
                )
            for index in range(20):
                add(
                    date + timedelta(hours=17, seconds=index * 10),
                    "failure",
                    None,
                    "203.0.113.90",
                    0,
                    "attack_unknown_accounts",
                    f"unknown-{episode_day}",
                )
            # No anomalous observation is guaranteed for misuse of a known credential.
            person = scenario_rng.choice(people)
            add(
                date + timedelta(seconds=int(person[1] * 3600)),
                "success",
                person,
                person[3],
                person[2],
                "attack_familiar_credential",
                f"familiar-{episode_day}",
            )
    pairs = sorted(
        zip(events, labels, strict=True), key=lambda pair: (pair[0].occurred_at, pair[0].event_id)
    )
    if any(not config.start <= event.occurred_at < config.end for event, _ in pairs):
        raise ValueError("Generated event escaped its reserved period")
    return [pair[0] for pair in pairs], [pair[1] for pair in pairs]


def project(events: list[Event], view: str) -> list[Event]:
    """Only observable facts enter; labels cannot influence visibility or masking."""
    if view not in VIEWS:
        raise ValueError("Unknown observation view")
    if view == "complete":
        return list(events)
    if view == "local_guard":
        return [
            replace(event, source_ip=None, user_agent=None)
            for event in events
            if event.outcome == "success" or event.user_id is not None
        ]
    return [
        replace(event, user_id=None, account_key=None, user_agent=None)
        if event.outcome == "failure"
        else event
        for event in events
    ]
