"""Operate a separate loopback-only Auth realm; never read hosted .env credentials.

Run with backend/.venv/bin/python. All generated secrets stay in ignored local
configuration. The production migration/cutover is a separate operation.
"""

import argparse
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

import psycopg
from dotenv import dotenv_values, set_key
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env.free-auth.local"
COMPOSE = ROOT / "compose.auth.yaml"
PROJECT = "sherlock-free-auth"


def configuration(*, create=False):
    if ENV_FILE.is_symlink():
        raise ValueError("Local credentials must be a regular private file")
    if not ENV_FILE.exists():
        if not create:
            raise ValueError("Run tools/free_auth.py up before using this local realm")
        existing = subprocess.run(
            ["docker", "volume", "inspect", PROJECT + "_auth-data"],
            check=False,
            capture_output=True,
            timeout=15,
        )
        if existing.returncode == 0:
            raise ValueError(
                "Existing local database has no credential file; restore its backup first"
            )
        values = {
            name: secrets.token_hex(32)
            for name in (
                "LOCAL_DB_PASSWORD",
                "LOCAL_AUTH_DB_PASSWORD",
                "LOCAL_REST_DB_PASSWORD",
                "LOCAL_API_DB_PASSWORD",
                "LOCAL_AUDIT_DB_PASSWORD",
                "LOCAL_WORKER_DB_PASSWORD",
                "LOCAL_JWT_SECRET",
                "INGESTION_SIGNING_KEY",
            )
        }
        values["LOCAL_PUBLIC_KEY"] = "sb_publishable_" + secrets.token_urlsafe(24)
        values.update(
            {
                "ENVIRONMENT": "development",
                "ALLOWED_ORIGINS": "http://127.0.0.1:5180",
                "VITE_API_BASE_URL": "http://127.0.0.1:8001",
                "VITE_SUPABASE_URL": "http://127.0.0.1:54421",
                "SUPABASE_URL": "http://127.0.0.1:54421",
                "VITE_SUPABASE_PUBLISHABLE_KEY": values["LOCAL_PUBLIC_KEY"],
                "SUPABASE_PUBLISHABLE_KEY": values["LOCAL_PUBLIC_KEY"],
                "DETECTION_ENABLED": "false",
                "AUTH_LOGS_TOKEN": "",
                "AUTH_LOGS_PROJECT_REF": "",
            }
        )
        for setting, role, password in (
            ("DATABASE_URL", "sl_local_api", "LOCAL_API_DB_PASSWORD"),
            ("COLLECTOR_DATABASE_URL", "sl_local_audit", "LOCAL_AUDIT_DB_PASSWORD"),
            ("WORKER_DATABASE_URL", "sl_local_worker", "LOCAL_WORKER_DB_PASSWORD"),
        ):
            values[setting] = (
                f"postgresql://{role}:{values[password]}@127.0.0.1:54322/sherlock"
            )
        descriptor = os.open(ENV_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(
                "# Private local Auth realm; never commit or use for a public deployment.\n"
            )
            stream.write("".join(f"{key}={value}\n" for key, value in values.items()))
    os.chmod(ENV_FILE, 0o600)
    values = dict(dotenv_values(ENV_FILE))
    # Reject missing/corrupt generated credentials before any container mutation.
    for name in (
        "LOCAL_DB_PASSWORD",
        "LOCAL_AUTH_DB_PASSWORD",
        "LOCAL_REST_DB_PASSWORD",
        "LOCAL_API_DB_PASSWORD",
        "LOCAL_AUDIT_DB_PASSWORD",
        "LOCAL_WORKER_DB_PASSWORD",
        "LOCAL_JWT_SECRET",
    ):
        if (
            not values.get(name)
            or len(values[name]) != 64
            or any(c not in "0123456789abcdef" for c in values[name])
        ):
            raise ValueError(
                "Local configuration is incomplete; do not rotate an existing volume blindly"
            )
    if values.get("SUPABASE_URL") != "http://127.0.0.1:54421":
        raise ValueError("This utility supports only the isolated local Auth realm")
    for setting, role_name, password in (
        ("DATABASE_URL", "sl_local_api", "LOCAL_API_DB_PASSWORD"),
        ("COLLECTOR_DATABASE_URL", "sl_local_audit", "LOCAL_AUDIT_DB_PASSWORD"),
        ("WORKER_DATABASE_URL", "sl_local_worker", "LOCAL_WORKER_DB_PASSWORD"),
    ):
        expected = (
            f"postgresql://{role_name}:{values[password]}@127.0.0.1:54322/sherlock"
        )
        if values.get(setting) != expected:
            raise ValueError("Local runtime connections must match this isolated realm")
    public_key = values.get("LOCAL_PUBLIC_KEY") or ""
    if not re.fullmatch(r"sb_publishable_[A-Za-z0-9_-]{24,64}", public_key) or any(
        values.get(name) != public_key
        for name in ("VITE_SUPABASE_PUBLISHABLE_KEY", "SUPABASE_PUBLISHABLE_KEY")
    ):
        raise ValueError("Local publishable-key configuration is inconsistent")
    values["SELF_HOSTED_GUARD"] = "true"
    if values.get("LOCAL_CLEANUP_DB_PASSWORD") is not None and not re.fullmatch(
        r"[a-f0-9]{64}", values["LOCAL_CLEANUP_DB_PASSWORD"]
    ):
        raise ValueError("Local cleanup credential is incomplete")
    # Explicitly override Settings' optional hosted .env fallback for model settings.
    for name, default in (
        ("MODEL_ARTIFACT_DIR", ""),
        ("WORKER_MODEL_VERSION", ""),
        ("WORKER_TRUST_LOCAL_ARTIFACT", "false"),
    ):
        values.setdefault(name, default)
    return values


def compose(values, *arguments):
    # Explicit env file and project prevent accidental use of hosted .env or services.
    subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            PROJECT,
            "--env-file",
            str(ENV_FILE),
            "-f",
            str(COMPOSE),
            *arguments,
        ],
        cwd=ROOT,
        env={**os.environ, **values},
        check=True,
        timeout=300,
    )


def owner_connection(values):
    return psycopg.connect(
        host="127.0.0.1",
        port=54322,
        dbname="sherlock",
        user="postgres",
        password=values["LOCAL_DB_PASSWORD"],
        connect_timeout=5,
        autocommit=True,
    )


def role(connection, name, password):
    exists = connection.execute(
        "select 1 from pg_roles where rolname=%s", (name,)
    ).fetchone()
    if not exists:
        connection.execute(
            sql.SQL("create role {} nologin").format(sql.Identifier(name))
        )
    connection.execute(
        sql.SQL("alter role {} login noinherit password {}").format(
            sql.Identifier(name), sql.Literal(password)
        )
    )


def bootstrap(values):
    with owner_connection(values) as c:
        for name in ("anon", "authenticated"):
            if not c.execute(
                "select 1 from pg_roles where rolname=%s", (name,)
            ).fetchone():
                c.execute(
                    sql.SQL("create role {} nologin").format(sql.Identifier(name))
                )
        role(c, "supabase_auth_admin", values["LOCAL_AUTH_DB_PASSWORD"])
        role(c, "authenticator", values["LOCAL_REST_DB_PASSWORD"])
        c.execute("grant anon, authenticated to authenticator")
        c.execute("create schema if not exists auth authorization supabase_auth_admin")
        c.execute("alter role supabase_auth_admin set search_path = auth")
        c.execute("revoke create on schema public from public")
        c.execute("grant usage on schema public,auth to anon,authenticated")


def application_schema(values):
    with owner_connection(values) as c:
        # PostgREST sends request.jwt.claims; Auth's initial helper uses an older GUC.
        c.execute("""create or replace function auth.uid() returns uuid language sql stable
          set search_path = '' as $$
          select coalesce(nullif(current_setting('request.jwt.claim.sub',true),''),
            nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid
          $$""")
        c.execute("grant execute on function auth.uid() to anon,authenticated")
        c.execute("create schema if not exists local_setup")
        c.execute("revoke all on schema local_setup from public,anon,authenticated")
        c.execute(
            "create table if not exists local_setup.migrations (name text primary key)"
        )
        for migration in sorted((ROOT / "supabase/migrations").glob("*.sql")):
            if c.execute(
                "select 1 from local_setup.migrations where name=%s", (migration.name,)
            ).fetchone():
                continue
            # Record success inside the migration's own transaction, including on a crash.
            body, final = migration.read_text().rsplit("commit;", 1)
            if final.strip():
                raise ValueError(
                    "Expected an atomic repository migration ending with commit;"
                )
            record = sql.SQL(
                "insert into local_setup.migrations(name) values({}); commit;"
            ).format(sql.Literal(migration.name))
            c.execute(body + record.as_string(c))
        c.execute((ROOT / "supabase/setup/collector_access.sql").read_text())
        c.execute((ROOT / "supabase/self-hosted/password_guard.sql").read_text())
        c.execute((ROOT / "supabase/self-hosted/guard_telemetry.sql").read_text())
        c.execute((ROOT / "supabase/self-hosted/retention.sql").read_text())
        for name, password, groups in (
            (
                "sl_local_api",
                "LOCAL_API_DB_PASSWORD",
                ("sherlock_ingest", "sherlock_reader"),
            ),
            ("sl_local_audit", "LOCAL_AUDIT_DB_PASSWORD", ("sherlock_audit_source",)),
            ("sl_local_worker", "LOCAL_WORKER_DB_PASSWORD", ("sherlock_worker",)),
        ):
            role(c, name, values[password])
            # Runtime server roles need inheritance of their narrow existing groups.
            c.execute(sql.SQL("alter role {} inherit").format(sql.Identifier(name)))
            for group in groups:
                c.execute(
                    sql.SQL("grant {} to {}").format(
                        sql.Identifier(group), sql.Identifier(name)
                    )
                )


def enable_cleanup(values):
    # A new narrow credential is generated only by explicit activation, never by normal up.
    password = values.get("LOCAL_CLEANUP_DB_PASSWORD")
    if password is None:
        password = secrets.token_hex(32)
        set_key(ENV_FILE, "LOCAL_CLEANUP_DB_PASSWORD", password, quote_mode="always")
        os.chmod(ENV_FILE, 0o600)
    if not re.fullmatch(r"[a-f0-9]{64}", password):
        raise ValueError(
            "Local cleanup credential is corrupt; restore its private configuration"
        )
    values["LOCAL_CLEANUP_DB_PASSWORD"] = password
    with owner_connection(values) as c:
        c.execute((ROOT / "supabase/self-hosted/retention.sql").read_text())
        role(c, "sl_local_cleanup", password)
        c.execute("alter role sl_local_cleanup inherit")
        c.execute("grant sherlock_local_cleanup to sl_local_cleanup")
        # Rerunning activation never weakens a different existing retention policy.
        days = c.execute(
            "select keep_days from private.retention_state where singleton"
        ).fetchone()[0]
        if days != 30:
            raise ValueError(
                "Existing retention policy differs from the 30-day local policy"
            )
        c.execute("update private.retention_state set enabled=true where singleton")
    compose(
        values, "--profile", "maintenance", "up", "-d", "--build", "--wait", "cleanup"
    )
    print("Local 30-day cleanup is enabled. Only aggregate counts are logged.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "up",
            "down",
            "status",
            "api",
            "frontend",
            "collector",
            "worker",
            "pin-model",
            "enable-cleanup",
            "cleanup-plan",
        ],
    )
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--model-version", default="")
    args = parser.parse_args()
    values = configuration(create=args.action == "up")
    if args.action == "up":
        compose(values, "up", "-d", "--wait", "db", "mail")
        bootstrap(values)
        compose(values, "up", "-d", "--wait", "auth")
        application_schema(values)
        compose(values, "up", "-d", "--build", "--wait", "rest", "proxy")
        with owner_connection(values) as c:
            cleanup_enabled = c.execute(
                "select enabled from private.retention_state where singleton"
            ).fetchone()[0]
        if cleanup_enabled:
            if not values.get("LOCAL_CLEANUP_DB_PASSWORD"):
                raise ValueError(
                    "Restore the cleanup credential before starting its timer"
                )
            compose(
                values,
                "--profile",
                "maintenance",
                "up",
                "-d",
                "--build",
                "--wait",
                "cleanup",
            )
        print(
            "Free Auth ready: app port 5180, Auth 54421, local inbox 54324. Hosted realm unchanged."
        )
    elif args.action == "down":
        # Include an activated cleanup service; deliberately preserve the volume.
        compose(values, "--profile", "maintenance", "down")
    elif args.action == "status":
        compose(values, "--profile", "maintenance", "ps")
    elif args.action == "enable-cleanup":
        enable_cleanup(values)
    elif args.action == "cleanup-plan":
        import json

        with owner_connection(values) as c:
            counts = c.execute("""select
              (select count(*) from private.security_events
                where occurred_at<now()-interval '30 days'),
              (select count(*) from auth_guard.password_rejections
                where created_at<now()-interval '30 days'),
              (select count(*) from auth.audit_log_entries
                where created_at<now()-interval '30 days'),
              (select count(*) from private.incidents i where not exists(
                select 1 from private.incident_events e where e.incident_id=i.id))""").fetchone()
        print(
            json.dumps(
                dict(
                    zip(
                        (
                            "expired_events",
                            "expired_rejections",
                            "expired_audits",
                            "empty_incidents",
                        ),
                        counts,
                        strict=True,
                    )
                )
            )
        )
    elif args.action == "pin-model":
        if not args.artifact_dir or not re.fullmatch(
            r"[a-f0-9]{64}", args.model_version
        ):
            parser.error(
                "Provide your trusted artifact directory and its bundle fingerprint"
            )
        artifact = args.artifact_dir.resolve()
        sys.path.insert(0, str(ROOT / "backend/src"))
        from sherlock_api.detection.runtime import artifact_version

        if artifact_version(artifact) != args.model_version:
            raise ValueError("Artifact fingerprint does not match the explicit pin")
        for key, value in {
            "MODEL_ARTIFACT_DIR": str(artifact),
            "WORKER_MODEL_VERSION": args.model_version,
            "WORKER_TRUST_LOCAL_ARTIFACT": "true",
            "DETECTION_ENABLED": "true",
        }.items():
            set_key(ENV_FILE, key, value, quote_mode="always")
        os.chmod(ENV_FILE, 0o600)
        print(
            "Local shadow model pinned. Restart only the local API/worker to apply it."
        )
    elif args.action in {"collector", "worker"}:
        os.chdir(ROOT)
        python = (
            ROOT / "ml/.venv/bin/python"
            if args.action == "worker"
            else Path(sys.executable)
        )
        if not python.exists():
            python = Path(sys.executable)
        module = "detection.cli" if args.action == "worker" else "telemetry.scheduler"
        os.execve(
            python,
            [str(python), "-m", f"sherlock_api.{module}", "run"],
            {
                **os.environ,
                **values,
                "PYTHONPATH": os.pathsep.join(
                    (str(ROOT / "backend/src"), str(ROOT / "ml/src"))
                ),
            },
        )
    elif args.action == "api":
        os.chdir(ROOT)
        os.execve(
            sys.executable,
            [
                sys.executable,
                "-m",
                "uvicorn",
                "sherlock_api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8001",
            ],
            {**os.environ, **values, "PYTHONPATH": str(ROOT / "backend/src")},
        )
    else:
        subprocess.run(
            [
                "npm",
                "--prefix",
                "frontend",
                "run",
                "dev",
                "--",
                "--mode",
                "free-auth",
                "--port",
                "5180",
            ],
            cwd=ROOT,
            env={**os.environ, **values},
            check=True,
        )


if __name__ == "__main__":
    main()
