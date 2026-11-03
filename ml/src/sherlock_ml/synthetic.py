"""Seeded fictional users and locally simulated scenarios; no requests are sent."""

import hashlib
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sherlock_ml.events import Event, Label

AGENTS = (
    "Mozilla/5.0 Chrome/130.0 Safari/537.36",
    "Mozilla/5.0 Firefox/132.0",
    "Mozilla/5.0 Version/18.0 Safari/605.1.15",
)


@dataclass(frozen=True)
class Config:
    seed: int = 42
    users: int = 200
    days: int = 90
    train_days: int = 50
    validation_days: int = 20
    attack_episodes: int = 90
    start: str = "2026-01-05"
    attack_scale: float = 1.0

    def __post_init__(self):
        if not 10 <= self.users <= 500 or not 6 <= self.days <= 365:
            raise ValueError("Use 10–500 users and 6–365 days")
        if not 2 <= self.train_days or not 1 <= self.validation_days:
            raise ValueError("Training needs at least 2 days; validation needs at least 1")
        if self.train_days + self.validation_days >= self.days:
            raise ValueError("Reserve at least one day for final evaluation")
        if not 0 <= self.attack_episodes <= 10000 or not 0.25 <= self.attack_scale <= 4:
            raise ValueError("Invalid attack count or scale")
        datetime.strptime(self.start, "%Y-%m-%d")

    @property
    def start_at(self) -> datetime:
        return datetime.strptime(self.start, "%Y-%m-%d").replace(tzinfo=UTC)

    @property
    def train_end(self) -> datetime:
        return self.start_at + timedelta(days=self.train_days)

    @property
    def validation_end(self) -> datetime:
        return self.train_end + timedelta(days=self.validation_days)

    @property
    def end(self) -> datetime:
        return self.start_at + timedelta(days=self.days)


@dataclass(frozen=True)
class Habit:
    user_id: str
    hour: float
    activity: float
    browser: int
    home: str
    office: str
    shift_day: int | None


def generate(config: Config) -> tuple[list[Event], list[Label]]:
    rng = random.Random(config.seed)
    events: list[Event] = []
    labels: list[Label] = []

    def uid() -> str:
        return str(UUID(int=rng.getrandbits(128), version=4))

    # All sources are in documentation-only networks; both populations draw from
    # the same pool. IP addresses and IDs are never model features.
    sources = [
        f"{network}.{host}"
        for network in ("192.0.2", "198.51.100", "203.0.113")
        for host in range(1, 255)
    ]
    rng.shuffle(sources)
    offices = sources[:12]
    habits = [
        Habit(
            user_id=uid(),
            hour=rng.uniform(7, 21) if rng.random() > 0.15 else rng.uniform(0, 5),
            activity=rng.uniform(0.55, 0.95),
            browser=rng.randrange(len(AGENTS)),
            home=sources[12 + index],
            office=rng.choice(offices),
            shift_day=rng.randint(config.train_days, config.days - 1)
            if rng.random() < 0.15
            else None,
        )
        for index in range(config.users)
    ]

    def add(at, outcome, user, source, agent, scenario, incident=None, account_key=None):
        event = Event(uid(), at, outcome, user, account_key, source, agent)
        events.append(event)
        labels.append(Label(event.event_id, incident is not None, scenario, incident))

    for day in range(config.days):
        date = config.start_at + timedelta(days=day)
        for habit in habits:
            probability = habit.activity * (0.60 if date.weekday() >= 5 else 1)
            if rng.random() > probability:
                continue
            shifted = habit.shift_day is not None and day >= habit.shift_day
            hour = (habit.hour + (4 if shifted else 0) + rng.gauss(0, 0.8)) % 24
            at = date + timedelta(seconds=int(hour * 3600))
            # Reserve room for retries so no event escapes its generated day.
            at = min(at, date + timedelta(hours=23, minutes=50))
            browser = habit.browser
            scenario = "benign_schedule_change" if shifted else "benign_login"
            if rng.random() < 0.025:
                browser = (browser + rng.randint(1, 2)) % len(AGENTS)
                scenario = "benign_new_browser"
            source = rng.choices(
                [habit.home, habit.office, rng.choice(sources)], weights=[78, 18, 4]
            )[0]
            if rng.random() < 0.12:
                for _ in range(rng.randint(1, 3)):
                    add(at, "failure", habit.user_id, source, AGENTS[browser], "benign_mistake")
                    at += timedelta(seconds=rng.randint(8, 35))
            add(at, "success", habit.user_id, source, AGENTS[browser], scenario)

    for episode in range(config.attack_episodes):
        # Mostly benign training; attack prevalence differs in validation/test.
        phase = rng.choices(["train", "validation", "test"], weights=[10, 45, 45])[0]
        lower, upper = {
            "train": (1, config.train_days),
            "validation": (config.train_days, config.train_days + config.validation_days),
            "test": (config.train_days + config.validation_days, config.days),
        }[phase]
        day = rng.randrange(lower, upper)
        date = config.start_at + timedelta(days=day)
        habit = rng.choice(habits)
        source = rng.choice(sources)
        agent = AGENTS[rng.randrange(len(AGENTS))]
        incident = f"episode-{episode:05d}"
        scenario = ("brute_force", "password_spray", "suspicious_success")[episode % 3]
        at = date + timedelta(seconds=rng.randint(0, 20 * 3600))
        if scenario == "brute_force":
            for _ in range(max(3, int(rng.randint(12, 45) * config.attack_scale))):
                add(at, "failure", habit.user_id, source, agent, scenario, incident)
                at += timedelta(seconds=rng.randint(3, 20))
            if rng.random() < 0.35:
                add(at, "success", habit.user_id, source, agent, scenario, incident)
        elif scenario == "password_spray":
            targets = rng.sample(
                habits, min(config.users, max(4, int(rng.randint(10, 30) * config.attack_scale)))
            )
            for target in targets:
                unknown = rng.random() < 0.2
                account_key = hashlib.sha256(uid().encode()).hexdigest() if unknown else None
                add(
                    at,
                    "failure",
                    None if unknown else target.user_id,
                    source,
                    agent,
                    scenario,
                    incident,
                    account_key,
                )
                at += timedelta(seconds=rng.randint(8, 45))
        else:
            hour = (habit.hour + rng.uniform(8, 14)) % 24
            at = date + timedelta(seconds=int(hour * 3600))
            agent = AGENTS[(habit.browser + rng.randint(1, 2)) % len(AGENTS)]
            add(at, "success", habit.user_id, source, agent, scenario, incident)

    ordered = sorted(events, key=lambda event: (event.occurred_at, event.event_id))
    by_id = {label.event_id: label for label in labels}
    return ordered, [by_id[event.event_id] for event in ordered]
