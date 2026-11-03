"""Label-free experiment events matching the telemetry boundary's observable fields."""

import ipaddress
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Timestamps must include a timezone")
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class Event:
    event_id: str
    occurred_at: datetime
    outcome: Literal["success", "failure"]
    user_id: str | None = None
    account_key: str | None = None
    source_ip: str | None = None
    user_agent: str | None = None
    schema_version: int = 1

    def __post_init__(self):
        object.__setattr__(self, "event_id", str(UUID(self.event_id)))
        if self.occurred_at.tzinfo is None:
            raise ValueError("Timestamps must include a timezone")
        object.__setattr__(self, "occurred_at", self.occurred_at.astimezone(UTC))
        if (
            self.outcome not in {"success", "failure"}
            or type(self.schema_version) is not int
            or self.schema_version != 1
        ):
            raise ValueError("Unsupported event schema or outcome")
        if self.user_id is not None:
            object.__setattr__(self, "user_id", str(UUID(self.user_id)))
        if self.account_key is not None and not re.fullmatch(r"[a-f0-9]{64}", self.account_key):
            raise ValueError("Invalid account key")
        if self.source_ip is not None:
            address = ipaddress.ip_address(self.source_ip)
            if "%" in str(address):
                raise ValueError("Scoped addresses are unsupported")
            object.__setattr__(self, "source_ip", str(address))
        if self.user_agent is not None and (
            len(self.user_agent) > 512
            or any(ord(char) < 32 or ord(char) == 127 for char in self.user_agent)
        ):
            raise ValueError("Invalid user agent")

    @property
    def account(self) -> str | None:
        # Namespaces prevent accidental collisions between the two identifier kinds.
        if self.user_id:
            return f"user:{self.user_id}"
        return f"key:{self.account_key}" if self.account_key else None

    def record(self) -> dict:
        return {**asdict(self), "occurred_at": self.occurred_at.astimezone(UTC).isoformat()}

    @classmethod
    def from_record(cls, record: dict) -> "Event":
        # Unknown fields (including scenario labels) fail closed at the feature boundary.
        return cls(**{**record, "occurred_at": timestamp(record["occurred_at"])})


@dataclass(frozen=True)
class Label:
    event_id: str
    is_attack: bool
    scenario: str
    incident_id: str | None = None

    def __post_init__(self):
        UUID(self.event_id)
        if type(self.is_attack) is not bool:
            raise ValueError("Attack labels must be booleans")
        if self.is_attack != bool(self.incident_id):
            raise ValueError("Every attack needs an incident; benign events cannot have one")
        if not self.scenario:
            raise ValueError("Scenario is required")
