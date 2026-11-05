"""Real transactions and role checks on disposable PostgreSQL; no hosted calls."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

DSN = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="Needs disposable PostgreSQL")
GUARD = Path(__file__).resolve().parents[2] / "supabase/self-hosted/password_guard.sql"


def connect():
    return psycopg.connect(DSN, row_factory=dict_row)


@pytest.fixture(scope="module", autouse=True)
def install_guard():
    if not DSN:
        return
    with connect() as c:
        c.execute(
            "do $$ begin if not exists (select 1 from pg_roles "
            "where rolname='supabase_auth_admin') then create role supabase_auth_admin nologin; "
            "end if; end $$"
        )
        c.execute(GUARD.read_text())
        # Setup is rerunnable and must not clear existing account state.
        c.execute(GUARD.read_text())


@pytest.fixture
def account():
    identity = uuid4()
    with connect() as c:
        c.execute("insert into auth.users(id) values(%s)", (identity,))
    yield identity
    with connect() as c:
        c.execute("delete from auth.users where id=%s", (identity,))


def attempt(identity, valid=False):
    with connect() as c:
        c.execute("set local role supabase_auth_admin")
        return c.execute(
            "select auth_guard.check_password_attempt(%s::jsonb) as result",
            (json.dumps({"user_id": str(identity), "valid": valid}),),
        ).fetchone()["result"]


def state(identity):
    with connect() as c:
        return c.execute(
            "select * from auth_guard.password_attempts where user_id=%s", (identity,)
        ).fetchone()


def test_five_failures_block_correct_password_without_extending_deadline(account):
    for count in range(1, 5):
        assert attempt(account)["decision"] == "continue"
        assert state(account)["failures"] == count
    denial = attempt(account)
    assert denial == {
        "decision": "reject",
        "message": "Invalid login credentials",
        "should_logout_user": False,
    }
    blocked = state(account)
    assert (blocked["blocked_until"] - blocked["updated_at"]).total_seconds() == 900
    assert attempt(account, True) == denial
    assert attempt(account, False) == denial
    assert state(account) == blocked


def test_valid_password_resets_only_outside_cooldown(account):
    attempt(account)
    attempt(account)
    assert attempt(account, True)["decision"] == "continue"
    assert state(account)["failures"] == 0
    for _ in range(5):
        attempt(account)
    with connect() as c:
        c.execute(
            "update auth_guard.password_attempts set blocked_until=clock_timestamp() "
            "where user_id=%s",
            (account,),
        )
    assert attempt(account, True)["decision"] == "continue"
    assert state(account)["failures"] == 0
    assert state(account)["blocked_until"] is None


def test_expired_window_and_cooldown_start_new_accounting(account):
    for _ in range(4):
        attempt(account)
    with connect() as c:
        c.execute(
            "update auth_guard.password_attempts "
            "set window_started_at=clock_timestamp()-interval '15 minutes' "
            "where user_id=%s",
            (account,),
        )
    assert attempt(account)["decision"] == "continue"
    assert state(account)["failures"] == 1
    for _ in range(4):
        attempt(account)
    with connect() as c:
        c.execute(
            "update auth_guard.password_attempts set blocked_until=clock_timestamp() "
            "where user_id=%s",
            (account,),
        )
    assert attempt(account)["decision"] == "continue"
    assert state(account)["failures"] == 1
    assert state(account)["blocked_until"] is None


def test_parallel_attempts_persist_across_connections_and_do_not_lose_updates(account):
    with ThreadPoolExecutor(max_workers=5) as pool:
        decisions = list(pool.map(lambda _: attempt(account)["decision"], range(10)))
    assert decisions.count("continue") == 4
    assert decisions.count("reject") == 6
    assert state(account)["failures"] == 5
    assert attempt(account, True)["decision"] == "reject"


def test_accounts_are_independent_and_account_deletion_cascades(account):
    other = uuid4()
    with connect() as c:
        c.execute("insert into auth.users(id) values(%s)", (other,))
    try:
        for _ in range(5):
            attempt(account)
        assert attempt(other, True)["decision"] == "continue"
        assert state(other)["failures"] == 0
    finally:
        with connect() as c:
            c.execute("delete from auth.users where id=%s", (other,))
    assert state(other) is None


@pytest.mark.parametrize(
    "event",
    [
        None,
        [],
        {},
        {"user_id": "bad", "valid": True},
        {"user_id": str(uuid4()), "valid": "false"},
        {"user_id": None, "valid": False},
    ],
)
def test_malformed_events_fail_closed(event):
    with connect() as c:
        c.execute("set local role supabase_auth_admin")
        with pytest.raises(psycopg.errors.InvalidParameterValue):
            c.execute("select auth_guard.check_password_attempt(%s::jsonb)", (json.dumps(event),))


def test_unknown_identity_cannot_create_guard_state():
    unknown = uuid4()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        attempt(unknown)
    assert state(unknown) is None


def test_non_auth_roles_cannot_read_change_or_execute_guard(account):
    attempt(account)
    for role in (
        "anon",
        "authenticated",
        "sherlock_ingest",
        "sherlock_reader",
        "sherlock_worker",
        "sherlock_audit_source",
    ):
        for sql in (
            "select * from auth_guard.password_attempts",
            "update auth_guard.password_attempts set failures=0",
            "select auth_guard.check_password_attempt('{}')",
        ):
            with connect() as c:
                c.execute(psycopg.sql.SQL("set local role {}").format(psycopg.sql.Identifier(role)))
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    c.execute(sql)


def test_row_lock_timeout_fails_closed_without_mutating_state(account):
    attempt(account)
    before = state(account)
    with connect() as c:
        c.execute(
            "select * from auth_guard.password_attempts where user_id=%s for update", (account,)
        )
        with pytest.raises(psycopg.errors.LockNotAvailable):
            attempt(account, True)
    assert state(account) == before
