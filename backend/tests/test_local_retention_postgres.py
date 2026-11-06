"""Destructive cleanup checks only in a disposable TEST_DATABASE_URL database."""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

DSN = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="Needs disposable PostgreSQL")
ROOT = Path(__file__).resolve().parents[2]


def connect():
    return psycopg.connect(DSN, row_factory=dict_row)


@pytest.fixture(autouse=True)
def local_realm():
    if not DSN:
        return
    with connect() as c:
        c.execute("""do $$ begin if not exists(select 1 from pg_roles
          where rolname='supabase_auth_admin') then create role supabase_auth_admin nologin;
          end if; end $$""")
        c.execute((ROOT / "supabase/self-hosted/password_guard.sql").read_text())
        c.execute((ROOT / "supabase/self-hosted/retention.sql").read_text())
        c.execute(
            "truncate private.security_events,auth.audit_log_entries,"
            "auth_guard.password_rejections,private.incidents cascade"
        )
        c.execute(
            "update private.retention_state set enabled=false,keep_days=30,status='disabled',"
            "last_success_at=null,backlog=false"
        )
        c.execute("update private.local_retention_state set next_run_at=null,last_success_at=null")
    yield
    with connect() as c:
        c.execute(
            "truncate private.security_events,auth.audit_log_entries,"
            "auth_guard.password_rejections,private.incidents cascade"
        )
        c.execute("update private.retention_state set enabled=false,status='disabled'")


def run():
    with connect() as c:
        c.execute("set local role sherlock_local_cleanup")
        return c.execute("select private.run_local_retention_cleanup() as result").fetchone()[
            "result"
        ]


def seed(c):
    account = uuid4()
    c.execute("insert into auth.users(id) values(%s)", (account,))
    c.execute(
        """insert into auth_guard.password_attempts(user_id,failures,blocked_until)
      values(%s,5,clock_timestamp()+interval '15 minutes')""",
        (account,),
    )
    for age in (31, 1):
        c.execute(
            """insert into private.security_events
          (source,source_event_id,occurred_at,outcome,user_id,payload_digest)
          values('supabase_audit',%s,now()-make_interval(days=>%s),'success',%s,%s)""",
            (uuid4(), age, account, "a" * 64),
        )
        c.execute(
            """insert into auth_guard.password_rejections(id,created_at,user_id,reason)
          values(%s,now()-make_interval(days=>%s),%s,'invalid_password')""",
            (uuid4(), age, account),
        )
        c.execute(
            """insert into auth.audit_log_entries(id,created_at,payload)
          values(%s,now()-make_interval(days=>%s),'{}')""",
            (uuid4(), age),
        )
    return account


def test_opt_in_expiry_cascades_and_preserves_accounts_profiles_and_cooldown():
    with connect() as c:
        identity = seed(c)
        before = c.execute(
            "select * from auth_guard.password_attempts where user_id=%s", (identity,)
        ).fetchone()
    assert run() == {"status": "disabled"}
    with connect() as c:
        assert c.execute("select count(*) as n from private.security_events").fetchone()["n"] == 2
        c.execute("update private.retention_state set enabled=true")
    result = run()
    assert result == {
        "status": "ready",
        "events_deleted": 1,
        "journal_deleted": 1,
        "audit_deleted": 1,
        "incidents_deleted": 0,
    }
    with connect() as c:
        for table in (
            "private.security_events",
            "private.scoring_jobs",
            "auth_guard.password_rejections",
            "auth.audit_log_entries",
        ):
            assert c.execute(f"select count(*) as n from {table}").fetchone()["n"] == 1
        assert (
            c.execute(
                "select * from auth_guard.password_attempts where user_id=%s", (identity,)
            ).fetchone()
            == before
        )
        assert c.execute("select id from public.profiles where id=%s", (identity,)).fetchone()
        assert c.execute("select id from auth.users where id=%s", (identity,)).fetchone()
        assert c.execute("select private.local_retention_healthy() as ok").fetchone()["ok"]
        c.execute("delete from auth.users where id=%s", (identity,))


def test_hourly_due_check_is_durable_and_parallel_calls_do_not_repeat_deletion():
    with connect() as c:
        c.execute("update private.retention_state set enabled=true")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sorted(row["status"] for row in results) in (["busy", "ready"], ["not_due", "ready"])
    assert run()["status"] == "not_due"
    # Reinstallation preserves the persisted timer and policy.
    with connect() as c:
        c.execute((ROOT / "supabase/self-hosted/retention.sql").read_text())
    assert run()["status"] == "not_due"
    with connect() as c:
        c.execute("update private.local_retention_state set next_run_at=now()-interval '1 second'")
    assert run()["status"] == "ready"


def test_cleanup_role_has_no_direct_data_access_or_policy_control():
    with connect() as c:
        for table in (
            "private.retention_state",
            "private.local_retention_state",
            "private.security_events",
            "private.user_roles",
            "public.profiles",
            "auth.users",
            "auth.sessions",
            "auth_guard.password_attempts",
            "auth_guard.password_rejections",
            "auth.audit_log_entries",
        ):
            # The bootstrap stub used by the database CI does not include Auth sessions.
            if c.execute("select to_regclass(%s) as relation", (table,)).fetchone()["relation"]:
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    assert not c.execute(
                        "select has_table_privilege('sherlock_local_cleanup',%s,%s) as ok",
                        (table, privilege),
                    ).fetchone()["ok"]
        for role in (
            "anon",
            "authenticated",
            "supabase_auth_admin",
            "sherlock_ingest",
            "sherlock_reader",
            "sherlock_worker",
            "sherlock_audit_source",
        ):
            assert not c.execute(
                "select has_function_privilege(%s,'private.run_local_retention_cleanup()',"
                "'execute') as ok",
                (role,),
            ).fetchone()["ok"]


def test_failure_rolls_back_the_entire_pass_and_reports_no_false_success():
    with connect() as c:
        account = seed(c)
        c.execute("update private.retention_state set enabled=true")
        c.execute("""create function private.fail_test_cleanup() returns trigger
          language plpgsql as $$ begin raise exception 'private test failure'; end $$""")
        c.execute("""create trigger fail_test_cleanup before delete on auth.audit_log_entries
          for each statement execute function private.fail_test_cleanup()""")
    try:
        assert run() == {"status": "error"}
        with connect() as c:
            for table in (
                "private.security_events",
                "private.scoring_jobs",
                "auth_guard.password_rejections",
                "auth.audit_log_entries",
            ):
                assert c.execute(f"select count(*) as n from {table}").fetchone()["n"] == 2
            state = c.execute(
                "select status,error_code,last_success_at from private.retention_state"
            ).fetchone()
            assert state == {
                "status": "error",
                "error_code": "cleanup_failed",
                "last_success_at": None,
            }
            assert not c.execute("select private.local_retention_healthy() as ok").fetchone()["ok"]
    finally:
        with connect() as c:
            c.execute("drop trigger fail_test_cleanup on auth.audit_log_entries")
            c.execute("drop function private.fail_test_cleanup()")
            c.execute("delete from auth.users where id=%s", (account,))


def test_backlog_is_bounded_and_retry_is_due_after_one_minute():
    with connect() as c:
        c.execute("update private.retention_state set enabled=true")
        c.execute("""insert into auth.audit_log_entries(id,created_at,payload)
          select gen_random_uuid(),now()-interval '31 days','{}'::jsonb
          from generate_series(1,10001)""")
    result = run()
    assert result["status"] == "partial" and result["audit_deleted"] == 10000
    with connect() as c:
        assert c.execute("select count(*) as n from auth.audit_log_entries").fetchone()["n"] == 1
        assert c.execute(
            "select next_run_at<now()+interval '61 seconds' as ok "
            "from private.local_retention_state"
        ).fetchone()["ok"]
        c.execute("update private.local_retention_state set next_run_at=now()-interval '1 second'")
    assert run()["status"] == "ready"


def test_model_results_cascade_and_only_empty_incident_groups_are_removed():
    version = "e" * 64
    old_event, fresh_event = uuid4(), uuid4()
    empty_after_expiry, fresh_group, unlinked_group = uuid4(), uuid4(), uuid4()
    with connect() as c:
        c.execute(
            """insert into private.model_versions
          (id,artifact_label,weights_digest,config_digest,schema_digest,feature_version,
           ml_threshold,rule_threshold) values(%s,'retention-fixture',%s,%s,%s,
           'login-history-v1',0.5,0.5) on conflict do nothing""",
            (version, "a" * 64, "b" * 64, "c" * 64),
        )
        for event_id, age in ((old_event, 31), (fresh_event, 1)):
            c.execute(
                """insert into private.security_events
              (id,source,source_event_id,occurred_at,outcome,payload_digest)
              values(%s,'supabase_audit',%s,now()-make_interval(days=>%s),'success',%s)""",
                (event_id, uuid4(), age, "d" * 64),
            )
            c.execute(
                """insert into private.detection_results
              (event_id,model_version_id,feature_version,features,history_as_of,ml_score,
               rule_score,flagged,signals,context_warnings)
              values(%s,%s,'login-history-v1','{}',now(),0.9,0.9,true,'{}','{}')""",
                (event_id, version),
            )
        for incident_id, key in (
            (empty_after_expiry, "old-only"),
            (fresh_group, "fresh"),
            (unlinked_group, "unlinked"),
        ):
            c.execute(
                """insert into private.incidents(id,model_version_id,entity_type,
              entity_key,window_start,first_seen,last_seen)
              values(%s,%s,'event',%s,now(),now(),now())""",
                (incident_id, version, key),
            )
        c.execute(
            "insert into private.incident_events(event_id,incident_id) values(%s,%s),(%s,%s)",
            (old_event, empty_after_expiry, fresh_event, fresh_group),
        )
        c.execute("update private.retention_state set enabled=true")
    result = run()
    assert result["events_deleted"] == 1 and result["incidents_deleted"] == 1
    with connect() as c:
        assert (
            c.execute("select event_id from private.detection_results").fetchone()["event_id"]
            == fresh_event
        )
        assert c.execute("select id from private.incidents").fetchone()["id"] == fresh_group
        assert (
            c.execute("select event_id from private.incident_events").fetchone()["event_id"]
            == fresh_event
        )


def test_provider_owned_trigger_cannot_expand_cleanup_into_account_permissions():
    with connect() as c:
        identity = seed(c)
        c.execute("update private.retention_state set enabled=true")
        owner = c.execute("""select r.rolname,r.rolsuper,r.rolcanlogin,r.rolcreaterole,
          r.rolcreatedb,r.rolbypassrls from pg_proc p join pg_roles r on r.oid=p.proowner
          where p.oid='private.run_local_retention_cleanup()'::regprocedure""").fetchone()
        assert owner["rolname"] == "sherlock_cleanup_owner"
        assert not any(
            owner[key]
            for key in ("rolsuper", "rolcanlogin", "rolcreaterole", "rolcreatedb", "rolbypassrls")
        )
        c.execute("""create function private.try_cleanup_escalation() returns trigger
          language plpgsql security invoker set search_path='' as $$ begin
          insert into private.user_roles(user_id,role) values(tg_argv[0]::uuid,'admin');
          return old; end $$""")
        c.execute(
            "create trigger try_cleanup_escalation before delete on auth.audit_log_entries "
            f"for each row execute function private.try_cleanup_escalation('{identity}')"
        )
    try:
        assert run()["status"] == "error"
        with connect() as c:
            assert not c.execute(
                "select role from private.user_roles where user_id=%s", (identity,)
            ).fetchone()
            assert (
                c.execute("select count(*) as n from auth.audit_log_entries").fetchone()["n"] == 2
            )
    finally:
        with connect() as c:
            c.execute("drop trigger try_cleanup_escalation on auth.audit_log_entries")
            c.execute("drop function private.try_cleanup_escalation()")
            c.execute("delete from auth.users where id=%s", (identity,))
