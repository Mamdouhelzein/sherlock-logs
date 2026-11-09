"""Bootstrap a NEW public beta database without reading existing local credentials.

Run init locally first. Fill only the new ignored .env.public-beta.local file.
Use roles before Auth's first start and schema after Auth creates its tables.
The owner credential is for this one-off operator, never for a runtime service.
"""

import argparse
import json
import os
import re
import secrets
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

import psycopg
from dotenv import dotenv_values, set_key
from psycopg import sql
from sherlock_api.deployment import database_url

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env.public-beta.local"
ROLES = {
    "supabase_auth_admin": ("AUTH", ()),
    "authenticator": ("REST", ("anon", "authenticated")),
    "sl_beta_api": ("API", ("sherlock_reader",)),
    "sl_beta_ingest": ("INGEST", ("sherlock_ingest",)),
    "sl_beta_audit": ("AUDIT", ("sherlock_audit_source",)),
    "sl_beta_worker": ("SCORING", ("sherlock_worker",)),
    "sl_beta_cleanup": ("CLEANUP", ("sherlock_local_cleanup",)),
}


def init():
    if ENV_FILE.exists() or ENV_FILE.is_symlink():
        raise ValueError("Never replace an existing realm's configuration")
    values = {
        "REALM_ID": secrets.token_hex(16),
        "JWT_SECRET": secrets.token_hex(32),
        "PUBLIC_KEY": "sb_publishable_" + secrets.token_urlsafe(24),
        "PUBLIC_ORIGIN": "",
        "DATABASE_HOST": "",
        "DATABASE_PORT": "5432",
        "ADMIN_DATABASE_URL": "",
        "API_UPSTREAM": "",
        "SMTP_HOST": "",
        "SMTP_PORT": "587",
        "SMTP_USER": "",
        "SMTP_PASSWORD": "",
        "SMTP_FROM": "",
        "REGISTRATION_ENABLED": "false",
        **{prefix + "_PASSWORD": secrets.token_hex(32) for prefix, _ in ROLES.values()},
    }
    fd = os.open(ENV_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(
            "# NEW isolated public beta. Never commit, paste into chat, or reuse locally.\n"
        )
        for key, value in values.items():
            stream.write(f"{key}='{value}'\n")
    return values


def configuration():
    if ENV_FILE.is_symlink() or ENV_FILE.stat().st_mode & 0o077:
        raise ValueError("Use a regular private configuration file with mode 0600")
    values = dict(dotenv_values(ENV_FILE))
    realm = values.get("REALM_ID", "")
    if len(realm) != 32 or any(char not in "0123456789abcdef" for char in realm):
        raise ValueError("The new realm identifier is missing")
    dsn = database_url(values, "ADMIN_DATABASE_URL")
    hostname = urlsplit(dsn).hostname
    if hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(
        (".supabase.co", ".supabase.com")
    ):
        raise ValueError("This operator cannot target local or hosted Supabase realms")
    for prefix, _ in ROLES.values():
        value = values.get(prefix + "_PASSWORD", "")
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("Restore the new realm's generated credentials")
    return values


def claim_database(connection, realm):
    sentinel = connection.execute("select to_regclass('cloud_setup.realm')").fetchone()[
        0
    ]
    if sentinel is None:
        application_tables = connection.execute(
            "select exists(select 1 from pg_tables where schemaname "
            "in ('public','auth','private','local_setup'))"
        ).fetchone()[0]
        if application_tables or any(
            connection.execute("select to_regclass(%s)", (name,)).fetchone()[0]
            for name in (
                "auth.users",
                "private.security_events",
                "local_setup.migrations",
            )
        ):
            raise ValueError("Refusing to claim an existing application database")
        with connection.transaction():
            connection.execute("create schema cloud_setup")
            connection.execute("revoke all on schema cloud_setup from public")
            connection.execute("create table cloud_setup.realm(id text primary key)")
            connection.execute("insert into cloud_setup.realm values(%s)", (realm,))
            connection.execute(
                "create table cloud_setup.migrations(name text primary key, digest text not null)"
            )
    elif connection.execute("select id from cloud_setup.realm").fetchall() != [
        (realm,)
    ]:
        raise ValueError("Database belongs to a different deployment realm")


def create_role(c, name, *, password=None, groups=()):
    if not c.execute("select 1 from pg_roles where rolname=%s", (name,)).fetchone():
        c.execute(sql.SQL("create role {} nologin").format(sql.Identifier(name)))
    if password:
        c.execute(
            sql.SQL(
                "alter role {} login inherit nosuperuser nocreatedb nocreaterole nobypassrls password {}"
            ).format(sql.Identifier(name), sql.Literal(password))
        )
    for group in groups:
        c.execute(
            sql.SQL("grant {} to {}").format(
                sql.Identifier(group), sql.Identifier(name)
            )
        )


def roles(c, values):
    for name in ("anon", "authenticated"):
        create_role(c, name)
    for name in ("supabase_auth_admin", "authenticator"):
        prefix, groups = ROLES[name]
        create_role(c, name, password=values[prefix + "_PASSWORD"], groups=groups)
    # REST switches into browser roles explicitly; it must not inherit their access.
    c.execute("alter role authenticator noinherit")
    c.execute("create schema if not exists auth authorization supabase_auth_admin")
    c.execute("alter role supabase_auth_admin set search_path=auth")
    c.execute("revoke create on schema public from public")
    c.execute("grant usage on schema public,auth to anon,authenticated")


def schema(c, values):
    import hashlib

    if not c.execute("select to_regclass('auth.users')").fetchone()[0]:
        raise ValueError(
            "Start Auth to initialize its schema before applying the application"
        )
    c.execute("""create or replace function auth.uid() returns uuid language sql stable
      set search_path='' as $$ select coalesce(
        nullif(current_setting('request.jwt.claim.sub',true),''),
        nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid $$""")
    c.execute("grant execute on function auth.uid() to anon,authenticated")
    for migration in sorted((ROOT / "supabase/migrations").glob("*.sql")):
        content = migration.read_text()
        digest = hashlib.sha256(content.encode()).hexdigest()
        previous = c.execute(
            "select digest from cloud_setup.migrations where name=%s", (migration.name,)
        ).fetchone()
        if previous:
            if previous[0] != digest:
                raise ValueError("An applied migration changed; do not replay it")
            continue
        body, final = content.rsplit("commit;", 1)
        if final.strip():
            raise ValueError("Application migrations must end in an atomic commit")
        record = sql.SQL(
            "insert into cloud_setup.migrations values({},{}); commit;"
        ).format(sql.Literal(migration.name), sql.Literal(digest))
        c.execute(body + record.as_string(c))
    for name in (
        "setup/collector_access.sql",
        "self-hosted/password_guard.sql",
        "self-hosted/guard_telemetry.sql",
        "self-hosted/retention.sql",
    ):
        c.execute((ROOT / "supabase" / name).read_text())
    for name, (prefix, groups) in ROLES.items():
        if name in {"supabase_auth_admin", "authenticator"}:
            continue
        create_role(c, name, password=values[prefix + "_PASSWORD"], groups=groups)
    # Installation leaves retention disabled; an explicit activation is separate.
    return {"schema": "applied", "automatic_cleanup": "unchanged"}


def connections(values):
    parsed = urlsplit(values["ADMIN_DATABASE_URL"])
    # The operator can use a local tunnel and macOS CA path. Never copy its
    # tunnel port, hostaddr or filesystem paths into a cloud runtime connection.
    host = values.get("DATABASE_HOST", "")
    port = int(values.get("DATABASE_PORT", "5432"))
    if (
        not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", host)
        or host in {"localhost", "127.0.0.1"}
        or not 1 <= port <= 65535
    ):
        raise ValueError("Set the managed database's private runtime hostname and port")
    parsed = parsed._replace(
        query=urlencode(
            {
                "sslmode": "verify-full",
                "sslrootcert": "/etc/ssl/certs/ca-certificates.crt",
                "connect_timeout": "10",
            }
        )
    )
    for role, (prefix, _) in ROLES.items():
        netloc = f"{quote(role, safe='')}:{values[prefix + '_PASSWORD']}@{host}:{port}"
        set_key(
            ENV_FILE,
            prefix + "_DATABASE_URL",
            urlunsplit(parsed._replace(netloc=netloc)),
            quote_mode="always",
        )
    os.chmod(ENV_FILE, 0o600)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("init", "roles", "schema", "enable-cleanup")
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            init()
            print('{"status":"private_configuration_created"}')
            return 0
        values = configuration()
        with psycopg.connect(
            values["ADMIN_DATABASE_URL"], autocommit=True, connect_timeout=10
        ) as c:
            claim_database(c, values["REALM_ID"])
            if args.command == "roles":
                roles(c, values)
            elif args.command == "schema":
                schema(c, values)
            else:
                policy = c.execute(
                    "select keep_days from private.retention_state where singleton"
                ).fetchone()
                if policy != (30,):
                    raise ValueError(
                        "Cleanup only supports the reviewed 30-day beta policy"
                    )
                c.execute(
                    "update private.retention_state set enabled=true where singleton"
                )
        connections(values)
        print(json.dumps({"status": args.command + "_complete"}))
        return 0
    except (psycopg.Error, ValueError, OSError, KeyError, TypeError):
        print(
            '{"status":"setup_failed_check_private_configuration_and_database_permissions"}'
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
