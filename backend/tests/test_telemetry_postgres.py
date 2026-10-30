"""Real PostgreSQL integration tests. Requires a migrated disposable test DB."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from sherlock_api.telemetry.collector import collect_once, inspect_audit_schema
from sherlock_api.telemetry.models import LoginEvent
from sherlock_api.telemetry.store import EventConflict, EventStore, connect

DSN = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="Needs a disposable PostgreSQL test database")


@pytest.fixture
def store():
    # Destructive cleanup is restricted to TEST_DATABASE_URL, never DATABASE_URL.
    with connect(DSN) as connection:
        connection.execute("truncate private.security_events, auth.audit_log_entries")
    yield EventStore(DSN, 30)
    with connect(DSN) as connection:
        connection.execute("truncate private.security_events, auth.audit_log_entries")


def event(**changes):
    return LoginEvent(event_id=uuid4(), occurred_at=datetime.now(UTC), outcome="failure", **changes)


def test_persists_facts_and_retries_without_changing_original_receipt_time(store):
    item = event(source_ip="2001:db8::1", account_key="a" * 64)
    assert store.insert([item], "trusted_auth_adapter").inserted == 1
    first = store.list(10, None).events[0]
    assert first.processing_status == "pending"
    assert first.source_ip == "2001:db8::1"
    assert store.insert([item], "trusted_auth_adapter").duplicates == 1
    assert store.list(10, None).events[0].received_at == first.received_at
    assert store.insert([item], "supabase_audit").inserted == 1


def test_conflicting_retry_rolls_back_the_entire_batch(store):
    original = event()
    store.insert([original], "trusted_auth_adapter")
    other = event()
    changed = original.model_copy(update={"outcome": "success"})
    with pytest.raises(EventConflict):
        store.insert([other, changed], "trusted_auth_adapter")
    rows = store.list(10, None).events
    assert len(rows) == 1
    assert rows[0].outcome == "failure"


def test_concurrent_retries_insert_exactly_once(store):
    item = event()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: store.insert([item], "trusted_auth_adapter"), range(4)))
    assert sum(result.inserted for result in results) == 1
    assert sum(result.duplicates for result in results) == 3
    assert len(store.list(10, None).events) == 1


def test_keyset_pages_handle_equal_timestamps_without_duplicates(store):
    timestamp = datetime.now(UTC)
    items = [event().model_copy(update={"occurred_at": timestamp}) for _ in range(5)]
    store.insert(items, "trusted_auth_adapter")
    first = store.list(2, None)
    second = store.list(2, first.next_cursor)
    third = store.list(2, second.next_cursor)
    ids = [item.id for page in [first, second, third] for item in page.events]
    assert len(ids) == len(set(ids)) == 5
    assert third.next_cursor is None


def test_expired_events_are_hidden_purged_and_cannot_be_reintroduced(store):
    fresh = event()
    old = event().model_copy(update={"occurred_at": datetime.now(UTC) - timedelta(days=31)})
    with pytest.raises(ValueError):
        store.insert([old], "trusted_auth_adapter")
    store.insert([fresh], "trusted_auth_adapter")
    with connect(DSN) as connection:
        connection.execute(
            """insert into private.security_events
            (source,source_event_id,occurred_at,outcome,payload_digest)
            values ('trusted_auth_adapter',%s,%s,'failure',%s)""",
            (old.event_id, old.occurred_at, old.digest()),
        )
    assert len(store.list(10, None).events) == 1
    assert store.purge() == 1
    assert store.purge() == 0
    assert len(store.list(10, None).events) == 1


def test_collector_paginates_retries_and_keeps_failed_login_gap_explicit(store):
    now = datetime.now(UTC) - timedelta(minutes=1)
    with connect(DSN) as connection:
        for index in range(3):
            connection.execute(
                """insert into auth.audit_log_entries(id,created_at,payload,ip_address)
                values (%s,%s,%s,'')""",
                (
                    uuid4(),
                    now + timedelta(seconds=index),
                    '{"action":"login","actor_id":"00000000-0000-4000-8000-000000000001","email":"discard@example.test","traits":{"token":"secret"}}',
                ),
            )
        connection.execute(
            """insert into auth.audit_log_entries(id,created_at,payload)
            values (%s,%s,'{"action":"token_refreshed"}')""",
            (uuid4(), now),
        )
    result = collect_once(DSN, store, batch_size=2)
    assert result.complete and result.inserted == 3 and result.scanned == 3
    assert result.failed_login_coverage == "unavailable_from_audit_adapter"
    result = collect_once(DSN, store, batch_size=2)
    assert result.inserted == 0 and result.duplicates == 3
    page = store.list(10, None)
    assert all(item.outcome == "success" and item.source_ip is None for item in page.events)
    assert "discard@example" not in page.model_dump_json()
    assert "secret" not in page.model_dump_json()


def test_rescan_catches_late_source_rows_and_reports_invalid_rows(store):
    now = datetime.now(UTC)
    with connect(DSN) as connection:
        connection.execute(
            """insert into auth.audit_log_entries(id,created_at,payload)
            values (%s,%s,'{"action":"login"}')""",
            (uuid4(), now - timedelta(minutes=1)),
        )
    assert collect_once(DSN, store).inserted == 1
    with connect(DSN) as connection:
        connection.execute(
            """insert into auth.audit_log_entries(id,created_at,payload)
            values (%s,%s,'{"action":"login"}')""",
            (uuid4(), now - timedelta(minutes=2)),
        )
        connection.execute(
            """insert into auth.audit_log_entries(id,created_at,payload)
            values (%s,%s,'{"action":"login","actor_id":"malformed"}')""",
            (uuid4(), now),
        )
    report = collect_once(DSN, store)
    assert report.inserted == 1 and report.duplicates == 1 and report.rejected == 1


def test_collection_limits_are_reported_and_schema_inspection_is_not_a_readiness_claim(store):
    with connect(DSN) as connection:
        for _ in range(2):
            connection.execute(
                """insert into auth.audit_log_entries(id,created_at,payload)
                values (%s,%s,'{"action":"login"}')""",
                (uuid4(), datetime.now(UTC)),
            )
    assert not collect_once(DSN, store, batch_size=1, max_pages=1).complete
    assert inspect_audit_schema(DSN)["live_event_coverage_verified"] is False


def test_database_constraints_reject_forged_state_and_unknown_sources(store):
    with pytest.raises(psycopg.errors.CheckViolation):
        with connect(DSN) as connection:
            connection.execute(
                """insert into private.security_events
                (source,source_event_id,occurred_at,outcome,payload_digest,processing_status)
                values ('browser',%s,now(),'success',%s,'processed')""",
                (uuid4(), "a" * 64),
            )
