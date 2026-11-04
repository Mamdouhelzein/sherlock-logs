"""Real PostgreSQL leases/transactions. TEST_DATABASE_URL must be disposable."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest

from sherlock_api.detection.store import DetectionReader, WorkerStore
from sherlock_api.telemetry.models import LoginEvent
from sherlock_api.telemetry.store import EventStore, connect

DSN = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="Needs disposable PostgreSQL")
VERSION = "a" * 64
FEATURES = {
    name: 0.0
    for name in (
        "current_failure",
        "account_failures_15m",
        "account_attempts_15m",
        "source_attempts_5m",
        "source_accounts_5m",
        "source_failure_ratio_5m",
        "account_history_30d",
        "account_successes_30d",
        "browser_novel",
        "hour_deviation",
        "seconds_since_previous",
        "has_previous",
        "account_missing",
        "source_missing",
        "browser_missing",
    )
}


class RestrictedStore(WorkerStore):
    def connection(self):
        connection = connect(self.dsn)
        connection.autocommit = True
        connection.execute("set role sherlock_worker")
        connection.autocommit = False
        return connection


@pytest.fixture
def worker():
    with connect(DSN) as connection:
        connection.execute(
            "truncate private.security_events,private.incidents,"
            "private.model_versions,private.scoring_workers cascade"
        )
    store = RestrictedStore(DSN, 30, 60, 10000)
    store.register(
        SimpleNamespace(
            version=VERSION,
            label="fixture-model",
            feature_version="login-history-v1",
            digests={
                "model.joblib": "b" * 64,
                "experiment.json": "c" * 64,
                "feature_schema.json": "d" * 64,
            },
            ml_threshold=0.5,
            rule_threshold=0.6,
        )
    )
    yield store
    with connect(DSN) as connection:
        connection.execute(
            "truncate private.security_events,private.incidents,"
            "private.model_versions,private.scoring_workers cascade"
        )


def insert(count=1, **changes):
    events = [
        LoginEvent(
            event_id=uuid4(),
            occurred_at=datetime.now(UTC) - timedelta(seconds=5),
            outcome="failure",
            **changes,
        )
        for _ in range(count)
    ]
    EventStore(DSN, 30).insert(events, "trusted_auth_adapter")


def result(flagged=True):
    return SimpleNamespace(
        features=FEATURES,
        ml_score=0.9 if flagged else 0.1,
        rule_score=0.0,
        signals=["ml_outlier"] if flagged else [],
        warnings=[],
    )


def test_concurrent_claims_finalize_once_and_group_one_incident(worker):
    insert(8, user_id=uuid4())
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda _: worker.claim(VERSION), range(8)))
    assert len({claim.event["id"] for claim in claims}) == 8
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pool.map(lambda claim: worker.complete(claim, result()), claims))
    assert not worker.complete(claims[0], result())
    assert worker.claim(VERSION) is None
    with connect(DSN) as connection:
        assert (
            connection.execute("select count(*) as n from private.detection_results").fetchone()[
                "n"
            ]
            == 8
        )
        assert (
            connection.execute("select count(*) as n from private.incidents").fetchone()["n"] == 1
        )


def test_expiry_recovery_rejects_stale_finalization_and_failure(worker):
    insert()
    first = worker.claim(VERSION)
    with connect(DSN) as connection:
        connection.execute(
            "update private.scoring_jobs set lease_expires_at=now()-interval '1 second'"
        )
    second = worker.claim(VERSION)
    assert first.token != second.token
    assert not worker.complete(first, result())
    assert not worker.fail(first, "scoring_failed")
    assert worker.complete(second, result(False))
    assert DetectionReader(DSN, 30).status()["scored"] == 1
    assert DetectionReader(DSN, 30).status()["flagged"] == 0


def test_retry_backoff_and_final_attempt_expiry(worker):
    insert()
    for _attempt in range(4):
        claim = worker.claim(VERSION)
        assert worker.fail(claim, "history_limit")
        assert worker.claim(VERSION) is None
        with connect(DSN) as connection:
            connection.execute("update private.scoring_jobs set next_attempt_at=now()")
    worker.claim(VERSION)
    with connect(DSN) as connection:
        connection.execute(
            "update private.scoring_jobs set lease_expires_at=now()-interval '1 second'"
        )
    assert worker.claim(VERSION) is None
    with connect(DSN) as connection:
        assert connection.execute(
            "select state,last_error from private.scoring_jobs"
        ).fetchone() == {"state": "failed", "last_error": "lease_exhausted"}


def test_history_is_prior_only_and_overflow_is_explicit(worker):
    user = uuid4()
    now = datetime.now(UTC)
    times = [
        now - timedelta(minutes=2),
        now - timedelta(minutes=1),
        now - timedelta(seconds=5),
        now + timedelta(seconds=10),
    ]
    with connect(DSN) as connection:
        ids = []
        for at in times:
            ids.append(
                connection.execute(
                    """insert into private.security_events
              (source,source_event_id,occurred_at,outcome,user_id,payload_digest,source_ip)
              values('trusted_auth_adapter',%s,%s,'failure',%s,%s,'192.0.2.1') returning id""",
                    (uuid4(), at, user, "f" * 64),
                ).fetchone()["id"]
            )
        connection.execute(
            "update private.scoring_jobs set state='failed' where event_id=any(%s)",
            ([ids[0], ids[1], ids[3]],),
        )
    worker.history_limit = 1
    claim = worker.claim(VERSION)
    assert claim.event["id"] == str(ids[2])
    assert claim.event["source_ip"] == "192.0.2.1"
    assert claim.history_overflow
    assert {row["id"] for row in claim.history} == {str(ids[0]), str(ids[1])}


def test_invalid_snapshot_rolls_back_then_retention_removes_incident_identifiers(worker):
    insert(user_id=uuid4())
    claim = worker.claim(VERSION)
    bad = result()
    bad.features = {**FEATURES, "secret": 123}
    with pytest.raises(psycopg.errors.CheckViolation):
        worker.complete(claim, bad)
    assert DetectionReader(DSN, 30).status()["scored"] == 0
    assert worker.complete(claim, result())
    reader = DetectionReader(DSN, 30)
    record = reader.event(claim.event["id"])
    assert record["job_state"] == "processed" and record["mode"] == "shadow"
    assert "lease_token" not in record
    incident = reader.incidents(1)["rows"][0]
    assert len(reader.incident(incident["id"], 1)["rows"]) == 1
    worker.heartbeat(uuid4(), VERSION, "ready")
    assert reader.status()["worker_ready"]
    with connect(DSN) as connection:
        connection.execute(
            "update private.security_events set occurred_at=now()-interval '31 days'"
        )
    assert EventStore(DSN, 30).purge() == 1
    with connect(DSN) as connection:
        for table in ("scoring_jobs", "detection_results", "incident_events", "incidents"):
            assert (
                connection.execute(f"select count(*) as n from private.{table}").fetchone()["n"]
                == 0
            )


def test_investigation_reader_filters_accounts_decisions_and_keyset_pages(worker, monkeypatch):
    account, other = uuid4(), uuid4()
    pseudonym = "c" * 64
    now = datetime.now(UTC) - timedelta(minutes=2)
    facts = [
        LoginEvent(
            event_id=uuid4(),
            occurred_at=now + timedelta(seconds=i),
            outcome="failure" if i < 2 else "success",
            user_id=identity,
            account_key=pseudonym,
            source_ip="192.0.2.10",
        )
        for i, identity in enumerate([account, account, other, None])
    ]
    EventStore(DSN, 30).insert(facts, "trusted_auth_adapter")
    for i in range(4):
        claim = worker.claim(VERSION)
        assert worker.complete(claim, result(i == 0))

    def restricted_reader(dsn):
        connection = connect(dsn)
        connection.autocommit = True
        connection.execute("set role sherlock_reader")
        connection.autocommit = False
        return connection

    monkeypatch.setattr("sherlock_api.detection.store.connect", restricted_reader)
    reader = DetectionReader(DSN, 30)
    first = reader.events(1, user_id=account)
    assert first["has_more"] and len(first["rows"]) == 1
    row = first["rows"][0]
    second = reader.events(1, (row["occurred_at"], row["id"]), user_id=account)
    assert not second["has_more"] and len(second["rows"]) == 1
    assert row["id"] != second["rows"][0]["id"]
    assert {row["user_id"] for row in first["rows"] + second["rows"]} == {account}
    flagged = reader.events(30, flagged=True, outcome="failure", user_id=account)["rows"]
    assert len(flagged) == 1 and flagged[0]["source_ip"] == "192.0.2.10"
    assert reader.events(30, flagged=True, outcome="success")["rows"] == []
    anonymous = reader.events(30, account_key=pseudonym)["rows"]
    assert len(anonymous) == 1 and anonymous[0]["user_id"] is None
    assert reader.events(30, user_id=uuid4())["rows"] == []
    detail = reader.event(row["id"])
    assert detail["source_ip"] == "192.0.2.10" and detail["user_id"] == account
    assert detail["job_state"] == "processed" and detail["model_version_id"] == VERSION
