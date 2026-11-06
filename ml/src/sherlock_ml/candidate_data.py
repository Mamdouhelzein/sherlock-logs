"""Phase-separated fictional local-observation workloads for candidate v2."""

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from sherlock_ml.events import Event, Label
from sherlock_ml.stress_data import PROFILES

TRAIN_SEED = 2201
VALIDATION_SEED = 2202
HOLDOUT_SEEDS = (4401, 4402, 4403)
BENIGN_PROFILES = PROFILES[:3]
STARTS = {"train": (2026, 7, 1), "validation": (2026, 9, 1), "holdout": (2026, 11, 1)}


@dataclass(frozen=True)
class CandidateData:
    phase: str
    seed: int
    profile: str
    users: int = 100
    history_days: int = 35
    evaluation_days: int = 21

    def __post_init__(self):
        if self.phase not in STARTS or self.profile not in PROFILES:
            raise ValueError("Unknown candidate phase/workload")
        if not 1000 <= self.seed < 2**32 or not 10 <= self.users <= 500:
            raise ValueError("Invalid candidate seed/population")
        if not 7 <= self.history_days <= 60 or not 3 <= self.evaluation_days <= 60:
            raise ValueError("Invalid candidate time windows")
        if self.phase != "holdout" and self.seed in HOLDOUT_SEEDS:
            raise ValueError("Reserved final seeds cannot enter development data")
        if self.phase == "train" and self.profile not in BENIGN_PROFILES:
            raise ValueError("Training uses entire benign control workloads only")

    @property
    def start(self):
        return datetime(*STARTS[self.phase], tzinfo=UTC)

    @property
    def evaluation_start(self):
        return self.start + timedelta(days=self.history_days)

    @property
    def end(self):
        return self.evaluation_start + timedelta(days=self.evaluation_days)


def generate_candidate(config: CandidateData) -> tuple[list[Event], list[Label]]:
    # Workload-independent habits, but phase/workload-specific identity namespaces.
    habits = random.Random(config.seed)
    activity = random.Random(config.seed + 10000)
    bursts = random.Random(config.seed + 20000)
    namespace = uuid5(
        NAMESPACE_URL, f"sherlock-candidate-v2/{config.phase}/{config.seed}/{config.profile}"
    )
    people = [
        (str(uuid5(namespace, f"person/{i}")), habits.uniform(7, 19), habits.randrange(2))
        for i in range(config.users)
    ]
    events, labels = [], []
    holdout = config.phase == "holdout"
    drift = config.profile in {"behavior_drift", "mixed"}
    rush = config.profile in {"legitimate_bursts", "mixed"}

    def add(at, outcome, person, scenario, episode=None):
        event_id = str(uuid5(namespace, f"event/{len(events)}"))
        events.append(Event(event_id, at, outcome, person[0] if person else None))
        labels.append(
            Label(
                event_id,
                episode is not None,
                scenario,
                f"{namespace}/{episode}" if episode else None,
            )
        )

    for day in range(config.history_days + config.evaluation_days):
        date = config.start + timedelta(days=day)
        measured = day >= config.history_days
        for index, person in enumerate(people):
            new = drift and index >= int(config.users * 0.85)
            if new and not measured:
                continue
            if activity.random() > (0.58 if date.weekday() >= 5 else 0.87):
                continue
            shift = (8 if holdout else 5) if drift and measured and index % 5 == 0 else 0
            hour = (person[1] + shift + activity.gauss(0, 0.9 if holdout else 0.65)) % 24
            at = max(date + timedelta(minutes=2), date + timedelta(seconds=int(hour * 3600)))
            scenario = (
                "benign_new_account" if new else "benign_shift" if shift else "benign_routine"
            )
            if activity.random() < 0.18:
                add(at - timedelta(seconds=35), "failure", person, "benign_typo")
            if activity.random() < 0.015:
                add(at - timedelta(seconds=55), "failure", None, "benign_unknown_identifier")
            add(at, "success", person, scenario)
            # A normal application can produce multiple sessions, not one login/day.
            if activity.random() < 0.35:
                later = at + timedelta(minutes=activity.randint(2, 180))
                if later < date + timedelta(days=1):
                    add(later, "success", person, "benign_second_session")
        if rush:
            # Benign retries occur during warm-up as well as measured periods.
            office_size = min(
                config.users, bursts.randint(25, 65) if holdout else bursts.randint(20, 50)
            )
            for index, person in enumerate(people[:office_size]):
                add(
                    date + timedelta(hours=9, seconds=index * 4),
                    "success",
                    person,
                    "benign_office_wave",
                )
            target = people[day % len(people)]
            count = bursts.randint(6, 11) if holdout else bursts.randint(5, 10)
            spacing = bursts.randint(12, 45) if holdout else bursts.randint(15, 40)
            for retry in range(count):
                add(
                    date + timedelta(hours=12, seconds=retry * spacing),
                    "failure",
                    target,
                    "benign_stale_password" if retry < 5 else "benign_cooldown_retry",
                )
            add(date + timedelta(hours=12, minutes=22), "success", target, "benign_recovery")
        if not measured:
            continue
        if config.profile in {"fast_guessing", "mixed"}:
            target = bursts.choice(people)
            count = bursts.randint(7, 13) if holdout else bursts.randint(8, 12)
            spacing = bursts.randint(10, 35) if holdout else 20
            for attempt in range(count):
                add(
                    date + timedelta(hours=15, seconds=attempt * spacing),
                    "failure",
                    target,
                    "attack_fast_guessing",
                    f"fast/{day}",
                )
        if config.profile in {"evasive", "mixed"}:
            target = bursts.choice(people)
            # Each attempt is outside the preceding account-failure window.
            interval = bursts.randint(17, 38) if holdout else 22
            count = bursts.randint(7, 13) if holdout else 10
            for attempt in range(count):
                add(
                    date + timedelta(hours=1, minutes=attempt * interval),
                    "failure",
                    target,
                    "attack_slow_guessing",
                    f"slow/{day}",
                )
            width = min(config.users, bursts.randint(12, 28) if holdout else 20)
            for attempt, target in enumerate(bursts.sample(people, width)):
                add(
                    date + timedelta(hours=16, minutes=attempt * 2),
                    "failure",
                    target,
                    "attack_distributed_spray",
                    f"spray/{day}",
                )
            for attempt in range(20):
                add(
                    date + timedelta(hours=18, seconds=attempt * 15),
                    "failure",
                    None,
                    "attack_unknown_accounts",
                    f"unknown/{day}",
                )
            target = bursts.choice(people)
            add(
                date + timedelta(seconds=int(target[1] * 3600)),
                "success",
                target,
                "attack_familiar_credential",
                f"familiar/{day}",
            )
    pairs = sorted(
        zip(events, labels, strict=True), key=lambda pair: (pair[0].occurred_at, pair[0].event_id)
    )
    if any(not config.start <= event.occurred_at < config.end for event, _ in pairs):
        raise ValueError("Candidate event escaped its simulation window")
    return [pair[0] for pair in pairs], [pair[1] for pair in pairs]
