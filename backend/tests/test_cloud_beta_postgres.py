"""NEW disposable database only: bootstrap replay, ownership and restricted logins."""

import importlib.util
import os
from pathlib import Path

import psycopg
import pytest

DSN = os.environ.get("TEST_CLOUD_BETA_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="Requires a separate empty disposable PostgreSQL")
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("cloud_beta", ROOT / "tools/cloud_beta.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_bootstrap_only_claims_a_new_realm_and_preserves_data_on_replay():
    values = {prefix + "_PASSWORD": "a" * 64 for prefix, _ in setup.ROLES.values()}
    with psycopg.connect(DSN, autocommit=True) as c:
        setup.claim_database(c, "fixture-realm")
        with pytest.raises(ValueError):
            setup.claim_database(c, "other-realm")
        setup.roles(c, values)
        with pytest.raises(ValueError):
            setup.schema(c, values)
        # Minimal provider schema; the existing free-auth CI job exercises real GoTrue.
        c.execute("""create table auth.users(id uuid primary key,email text,
          raw_user_meta_data jsonb not null default '{}');
          create table auth.audit_log_entries(id uuid primary key,created_at timestamptz,
          payload json,ip_address varchar(64) not null default '');
          alter table auth.audit_log_entries enable row level security;""")
        setup.schema(c, values)
        identity = "00000000-0000-4000-8000-000000000001"
        c.execute("insert into auth.users(id,email) values(%s,'fixture@example.test')", (identity,))
        setup.schema(c, values)
        assert c.execute("select count(*) from public.profiles").fetchone() == (1,)
        assert c.execute("select count(*) from private.user_roles").fetchone() == (0,)
        assert c.execute("select enabled from private.retention_state").fetchone() == (False,)
        assert c.execute("select count(*) from cloud_setup.migrations").fetchone()[0] == len(
            list((ROOT / "supabase/migrations").glob("*.sql"))
        )
        for name in setup.ROLES:
            assert c.execute(
                "select rolsuper,rolcreaterole,rolcreatedb,rolbypassrls "
                "from pg_roles where rolname=%s",
                (name,),
            ).fetchone() == (False, False, False, False)
        for role in (
            "sl_beta_api",
            "sl_beta_ingest",
            "sl_beta_audit",
            "sl_beta_worker",
            "sl_beta_cleanup",
        ):
            for relation in (
                "auth.users",
                "auth_guard.password_attempts",
                "private.user_roles",
                "cloud_setup.realm",
            ):
                assert not c.execute(
                    "select has_table_privilege(%s,%s,'select')", (role, relation)
                ).fetchone()[0]
        assert c.execute(
            "select has_table_privilege('sl_beta_api','private.security_events','select')"
        ).fetchone() == (True,)
        assert c.execute(
            "select has_table_privilege('sl_beta_api','private.security_events','insert')"
        ).fetchone() == (False,)
        assert c.execute(
            "select has_table_privilege('sl_beta_ingest','private.security_events','insert')"
        ).fetchone() == (True,)
        with c.transaction():
            c.execute("set local role sl_beta_cleanup")
            assert c.execute("select private.run_local_retention_cleanup()").fetchone()[0] == {
                "status": "disabled"
            }
        c.execute(
            "update cloud_setup.migrations set digest='changed' "
            "where name=(select min(name) from cloud_setup.migrations)"
        )
        with pytest.raises(ValueError):
            setup.schema(c, values)


def test_claim_rejects_an_existing_application_without_an_owner_marker():
    # The test above leaves the marker intact. Hide just its name in a rollback
    # transaction to exercise the refusal without destroying the fixture.
    with psycopg.connect(DSN, autocommit=True) as c, c.transaction():
        c.execute("alter table cloud_setup.realm rename to hidden_realm")
        with pytest.raises(ValueError):
            setup.claim_database(c, "should-never-claim")
        c.execute("alter table cloud_setup.hidden_realm rename to realm")
