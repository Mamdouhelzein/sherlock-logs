"""Strict, allowlisted event contract. Raw provider payloads are never stored."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, IPvAnyAddress, field_validator

Source = Literal["supabase_audit", "trusted_auth_adapter"]


class LoginEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    schema_version: Literal[1] = 1
    event_id: UUID
    occurred_at: AwareDatetime
    outcome: Literal["success", "failure"]
    user_id: UUID | None = None
    account_key: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_ip: IPvAnyAddress | None = None
    user_agent: str | None = Field(default=None, max_length=512)

    @field_validator("occurred_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @field_validator("occurred_at", mode="before")
    @classmethod
    def explicit_timestamp(cls, value: object) -> object:
        if not isinstance(value, (str, datetime)):
            raise ValueError("Use an explicit timezone-aware timestamp")
        return value

    @field_validator("source_ip")
    @classmethod
    def no_scope_identifier(cls, value: IPvAnyAddress | None) -> IPvAnyAddress | None:
        if value is not None and "%" in str(value):
            raise ValueError("Scoped IP addresses are not supported")
        return value

    @field_validator("user_agent")
    @classmethod
    def reject_control_characters(cls, value: str | None) -> str | None:
        if value is not None and any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("User agent must not contain control characters")
        return value or None

    def validate_time(self, now: datetime, retention_days: int) -> None:
        if (
            not now - timedelta(days=retention_days)
            <= self.occurred_at
            <= now + timedelta(minutes=5)
        ):
            raise ValueError("Event timestamp is outside the collection window")

    def digest(self) -> str:
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


class EventBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    events: list[LoginEvent] = Field(min_length=1, max_length=100)


class StoredEvent(BaseModel):
    id: UUID
    source: Source
    source_event_id: UUID
    occurred_at: AwareDatetime
    received_at: AwareDatetime
    outcome: Literal["success", "failure"]
    user_id: UUID | None
    account_key: str | None
    source_ip: str | None
    user_agent: str | None
    processing_status: Literal["pending"]


class EventPage(BaseModel):
    events: list[StoredEvent]
    next_cursor: str | None


class IngestionResult(BaseModel):
    inserted: int
    duplicates: int
