"""Transactional inserts and keyset reads. Call blocking methods from a worker thread."""

import base64
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from sherlock_api.telemetry.models import (
    EventPage,
    IngestionResult,
    LoginEvent,
    Source,
    StoredEvent,
)


class EventConflict(Exception):
    """The source reused an event ID with different facts; the batch must roll back."""


def connect(dsn: str):
    return psycopg.connect(
        dsn,
        connect_timeout=5,
        row_factory=dict_row,
        options="-c statement_timeout=5000 -c lock_timeout=2000",
    )


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        if len(cursor) > 256:
            raise ValueError
        value = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
        if (
            not isinstance(value, list)
            or len(value) != 2
            or not all(isinstance(item, str) for item in value)
        ):
            raise ValueError
        timestamp = datetime.fromisoformat(value[0])
        if timestamp.tzinfo is None:
            raise ValueError
        return timestamp.astimezone(UTC), UUID(value[1])
    except (ValueError, TypeError, KeyError) as error:
        raise ValueError("Invalid event cursor") from error


def encode_cursor(event: StoredEvent) -> str:
    return base64.urlsafe_b64encode(
        json.dumps([event.occurred_at.isoformat(), str(event.id)]).encode()
    ).decode()


class EventStore:
    def __init__(self, dsn: str, retention_days: int):
        self.dsn = dsn
        self.retention_days = retention_days

    def insert(self, events: list[LoginEvent], source: Source) -> IngestionResult:
        now = datetime.now(UTC)
        for event in events:
            event.validate_time(now, self.retention_days)
        inserted = 0
        with connect(self.dsn) as connection:
            for event in events:
                digest = event.digest()
                row = connection.execute(
                    """insert into private.security_events
                    (source, source_event_id, occurred_at, outcome, user_id, account_key,
                     source_ip, user_agent, payload_digest)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    on conflict (source, source_event_id) do nothing returning id""",
                    (
                        source,
                        event.event_id,
                        event.occurred_at,
                        event.outcome,
                        event.user_id,
                        event.account_key,
                        str(event.source_ip) if event.source_ip else None,
                        event.user_agent,
                        digest,
                    ),
                ).fetchone()
                if row:
                    inserted += 1
                else:
                    existing = connection.execute(
                        """select payload_digest from private.security_events
                        where source = %s and source_event_id = %s""",
                        (source, event.event_id),
                    ).fetchone()
                    if existing is None or existing["payload_digest"] != digest:
                        raise EventConflict
        return IngestionResult(inserted=inserted, duplicates=len(events) - inserted)

    def list(self, limit: int, cursor: str | None) -> EventPage:
        before = decode_cursor(cursor) if cursor else None
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        columns = """id, source, source_event_id, occurred_at, received_at, outcome,
            user_id, account_key, host(source_ip) as source_ip, user_agent, processing_status"""
        with connect(self.dsn) as connection:
            if before:
                rows = connection.execute(
                    f"""select {columns} from private.security_events
                    where occurred_at >= %s and (occurred_at,id) < (%s,%s)
                    order by occurred_at desc,id desc limit %s""",
                    (cutoff, *before, limit + 1),
                ).fetchall()
            else:
                rows = connection.execute(
                    f"""select {columns} from private.security_events where occurred_at >= %s
                    order by occurred_at desc,id desc limit %s""",
                    (cutoff, limit + 1),
                ).fetchall()
        events = [StoredEvent.model_validate(row) for row in rows[:limit]]
        return EventPage(
            events=events,
            next_cursor=encode_cursor(events[-1]) if len(rows) > limit else None,
        )

    def purge(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        total = 0
        while True:
            with connect(self.dsn) as connection:
                result = connection.execute(
                    """delete from private.security_events where id in (
                    select id from private.security_events where occurred_at < %s
                    order by occurred_at,id limit 1000)""",
                    (cutoff,),
                )
                count = result.rowcount
                total += count
            if count < 1000:
                return total
