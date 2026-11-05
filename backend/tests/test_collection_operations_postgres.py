"""Disposable PostgreSQL only: operational leases, privilege boundaries and cleanup."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from sherlock_api.telemetry.operations import CollectionOperations
from sherlock_api.telemetry.store import connect

DSN = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="Needs disposable PostgreSQL")
COUNTS = {"scanned": 1, "inserted": 1, "duplicates": 0, "rejected": 0}


@pytest.fixture
def operations():
    with connect(DSN) as c:
        c.execute("truncate private.security_events cascade")
        c.execute("truncate private.collection_state,private.retention_state")
        c.execute("insert into private.collection_state(singleton) values(true)")
        c.execute("insert into private.retention_state(singleton) values(true)")
    yield CollectionOperations(DSN)
    with connect(DSN) as c:
        c.execute("truncate private.security_events cascade")


def test_collection_leases_fence_late_writers_and_keep_failed_full_scans_due(operations):
    first, second = uuid4(), uuid4()
    assert operations.begin(first, 30, 30)["full_scan"]
    assert operations.begin(second, 30, 30) is None
    assert not operations.progress(second)
    assert not operations.finish(second, "ready", COUNTS, None, 30)
    assert operations.finish(first, "ready", COUNTS, None, 30)
    assert not operations.finish(first, "ready", COUNTS, None, 30)
    assert operations.status()["collection"]["healthy"]
    with connect(DSN) as c:
        c.execute("update private.collection_state set next_run_at=now()-interval '1 second'")
    assert not operations.begin(second, 30, 30)["full_scan"]
    with connect(DSN) as c:
        c.execute("update private.collection_state set lease_until=now()-interval '1 second'")
    assert not operations.progress(second)
    third = uuid4()
    assert operations.begin(third, 60, 30)["full_scan"]
    assert not operations.finish(second, "ready", COUNTS, None, 30)
    assert operations.finish(third, "partial", COUNTS, "incomplete_scan", 30)
    with connect(DSN) as c:
        c.execute("update private.collection_state set next_run_at=now()-interval '1 second'")
    assert operations.begin(uuid4(), 60, 30)["full_scan"]
    assert operations.status()["collection"]["full_scan_overdue"]


def test_runtime_roles_cannot_delete_or_forge_raw_operational_state(operations):
    with connect(DSN) as c:
        for role in [
            "anon",
            "authenticated",
            "sherlock_ingest",
            "sherlock_worker",
            "sherlock_reader",
        ]:
            assert not c.execute(
                "select has_function_privilege(%s,"
                "'private.run_retention_cleanup()','execute') as allowed",
                (role,),
            ).fetchone()["allowed"]
        c.execute("set local role sherlock_ingest")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("update private.collection_state set status='ready'")
    # The failed transaction is rolled back on context exit.
    with connect(DSN) as c:
        c.execute("set local role sherlock_ingest")
        assert c.execute(
            "select private.begin_collection_run(%s,30,30) as run", (uuid4(),)
        ).fetchone()["run"]
    with connect(DSN) as c:
        c.execute("set local role authenticated")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select * from private.collection_state")


def test_cleanup_is_disabled_until_approved_and_preserves_fresh_events(operations):
    with connect(DSN) as c:
        for days in [31, 1]:
            c.execute(
                """insert into private.security_events
                (source,source_event_id,occurred_at,outcome,payload_digest)
              values('supabase_audit',%s,%s,'success',%s)""",
                (uuid4(), datetime.now(UTC) - timedelta(days=days), "a" * 64),
            )
        assert c.execute("select private.run_retention_cleanup() as n").fetchone()["n"] == 0
        assert c.execute("select count(*) as n from private.security_events").fetchone()["n"] == 2
        c.execute("update private.retention_state set enabled=true where singleton")
        assert c.execute("select private.run_retention_cleanup() as n").fetchone()["n"] == 1
        assert c.execute("select count(*) as n from private.security_events").fetchone()["n"] == 1
        assert c.execute("select count(*) as n from private.scoring_jobs").fetchone()["n"] == 1
        assert c.execute("select private.run_retention_cleanup() as n").fetchone()["n"] == 0
    status = operations.status()
    assert status["retention"]["healthy"] and status["retention"]["keep_days"] == 30
    assert not status["collection"]["healthy"]
    assert "run_id" not in status["collection"]


def test_invalid_summaries_and_wider_than_active_retention_are_rejected(operations):
    run = uuid4()
    operations.begin(run, 30, 30)
    with pytest.raises(psycopg.errors.InvalidParameterValue):
        operations.finish(
            run, "ready", {"scanned": "1", "inserted": 1, "duplicates": 0, "rejected": 0}, None, 30
        )
    with pytest.raises(psycopg.errors.InvalidParameterValue):
        operations.finish(
            run, "ready", {"scanned": 2, "inserted": 1, "duplicates": 0, "rejected": 0}, None, 30
        )
    assert operations.finish(run, "ready", COUNTS, None, 30)
    with connect(DSN) as c:
        c.execute("update private.collection_state set next_run_at=now()-interval '1 second'")
        c.execute("update private.retention_state set enabled=true where singleton")
    with pytest.raises(psycopg.errors.InvalidParameterValue):
        operations.begin(uuid4(), 60, 30)
