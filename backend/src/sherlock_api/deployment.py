"""Small-process supervision for the two-container public beta.

Each child receives only its own credentials. This is an operational boundary,
not isolation from another compromised process in the same container. A child
exit stops the whole service so the hosting platform can restart it. Never log
configuration, subprocess exceptions, or provider request bodies here.
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from threading import Event
from urllib.parse import parse_qs, urlsplit

from sherlock_api.config import Settings

MODEL_VERSION = "deafc493f2d8f5507885534f2bfc3ddb09f3ccd171104c0968deec7519f0ea7c"
BASE_ENV = {
    "PATH",
    "PYTHONPATH",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONUNBUFFERED",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "LANG",
    "HOME",
    "TMPDIR",
}


def required(env, name):
    value = env.get(name, "")
    if not value or any(char in value for char in "\r\n\x00"):
        raise ValueError("Missing or invalid deployment setting")
    return value


def database_url(env, name):
    value = required(env, name)
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or not parsed.hostname
        or not parsed.username
        or not parsed.password
        or not parsed.path.strip("/")
        or parsed.fragment
        or parse_qs(parsed.query).get("sslmode") != ["verify-full"]
    ):
        raise ValueError("Deployment connections require verified database TLS")
    return value


def common(env):
    origin = required(env, "PUBLIC_ORIGIN")
    if not re.fullmatch(r"https://[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", origin):
        raise ValueError("Set one exact public HTTPS origin")
    if urlsplit(origin).hostname.endswith(".supabase.co"):
        raise ValueError("The public beta requires its own protected Auth realm")
    key = required(env, "PUBLIC_KEY")
    if not re.fullmatch(r"sb_publishable_[A-Za-z0-9_-]{24,64}", key):
        raise ValueError("Use a new opaque public configuration key")
    return {
        **{name: env[name] for name in BASE_ENV if name in env},
        "ENVIRONMENT": "production",
        "ALLOWED_ORIGINS": origin,
        "SUPABASE_URL": origin,
        "SUPABASE_PUBLISHABLE_KEY": key,
        "DATABASE_URL": "",
        "COLLECTOR_DATABASE_URL": "",
        "WORKER_DATABASE_URL": "",
        "INGESTION_SIGNING_KEY": "",
        "AUTH_LOGS_TOKEN": "",
        "AUTH_LOGS_PROJECT_REF": "",
        "DETECTION_ENABLED": "true",
        "EVENT_RETENTION_DAYS": "30",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }


def runtime_children(env):
    base = common(env)
    api = {**base, "DATABASE_URL": database_url(env, "API_DATABASE_URL")}
    collector = {
        **base,
        "DATABASE_URL": database_url(env, "INGEST_DATABASE_URL"),
        "COLLECTOR_DATABASE_URL": database_url(env, "AUDIT_DATABASE_URL"),
        "SELF_HOSTED_GUARD": "true",
        "COLLECTION_INTERVAL_SECONDS": "30",
    }
    worker = {
        **base,
        "WORKER_DATABASE_URL": database_url(env, "SCORING_DATABASE_URL"),
        "MODEL_ARTIFACT_DIR": "/models",
        "WORKER_MODEL_VERSION": MODEL_VERSION,
        "WORKER_TRUST_LOCAL_ARTIFACT": "true",
    }
    # No ignored dotenv file is copied into these images. Validate production
    # settings before starting any listener, not after accepting a user request.
    for values in (api, collector, worker):
        Settings(_env_file=None, **{key.lower(): value for key, value in values.items()})
    return [
        (
            [
                sys.executable,
                "-m",
                "uvicorn",
                "sherlock_api.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--no-access-log",
                "--no-proxy-headers",
            ],
            api,
        ),
        ([sys.executable, "-m", "sherlock_api.telemetry.scheduler", "run"], collector),
        ([sys.executable, "-m", "sherlock_api.detection.cli", "run"], worker),
    ]


def portal_children(env):
    base = common(env)
    origin, key = base["SUPABASE_URL"], base["SUPABASE_PUBLISHABLE_KEY"]
    jwt = required(env, "JWT_SECRET")
    if not re.fullmatch(r"[a-f0-9]{64,128}", jwt):
        raise ValueError("Use a fresh strong signing secret")
    smtp_host = required(env, "SMTP_HOST")
    if smtp_host in {"mail", "localhost", "127.0.0.1"} or smtp_host.endswith(".test"):
        raise ValueError("A public beta requires a real transactional email provider")
    port = int(required(env, "SMTP_PORT"))
    if port not in {465, 587, 2525}:
        raise ValueError("Use a supported authenticated SMTP port")
    if env.get("REGISTRATION_ENABLED", "false") not in {"true", "false"}:
        raise ValueError("Registration must be explicitly enabled after verification")
    auth = {
        **base,
        "GOTRUE_API_HOST": "127.0.0.1",
        "GOTRUE_API_PORT": "9999",
        "API_EXTERNAL_URL": origin,
        "GOTRUE_SITE_URL": origin,
        "GOTRUE_URI_ALLOW_LIST": f"{origin}/auth/callback,{origin}/reset-password",
        "GOTRUE_DB_DRIVER": "postgres",
        "GOTRUE_DB_NAMESPACE": "auth",
        "GOTRUE_DB_DATABASE_URL": database_url(env, "AUTH_DATABASE_URL"),
        "GOTRUE_DB_MAX_POOL_SIZE": "5",
        "GOTRUE_DB_MAX_IDLE_POOL_SIZE": "2",
        "GOTRUE_JWT_SECRET": jwt,
        "GOTRUE_JWT_AUD": "authenticated",
        "GOTRUE_JWT_ADMIN_ROLES": "service_role",
        "GOTRUE_JWT_DEFAULT_GROUP_NAME": "authenticated",
        "GOTRUE_JWT_EXP": "3600",
        "GOTRUE_JWT_ISSUER": origin + "/auth/v1",
        "GOTRUE_DISABLE_SIGNUP": "false" if env.get("REGISTRATION_ENABLED") == "true" else "true",
        "GOTRUE_EXTERNAL_EMAIL_ENABLED": "true",
        "GOTRUE_EXTERNAL_PHONE_ENABLED": "false",
        "GOTRUE_EXTERNAL_ANONYMOUS_USERS_ENABLED": "false",
        "GOTRUE_MAILER_AUTOCONFIRM": "false",
        "GOTRUE_MAILER_SECURE_EMAIL_CHANGE_ENABLED": "true",
        "GOTRUE_PASSWORD_MIN_LENGTH": "8",
        "GOTRUE_PASSWORD_REQUIRED_CHARACTERS": "",
        "GOTRUE_SECURITY_REFRESH_TOKEN_ROTATION_ENABLED": "true",
        "GOTRUE_SECURITY_REFRESH_TOKEN_REUSE_INTERVAL": "10",
        "GOTRUE_RATE_LIMIT_HEADER": "X-Real-IP",
        "GOTRUE_RATE_LIMIT_TOKEN_REFRESH": "150",
        "GOTRUE_RATE_LIMIT_EMAIL_SENT": "12",
        "GOTRUE_SMTP_MAX_FREQUENCY": "1m",
        "GOTRUE_SMTP_ADMIN_EMAIL": required(env, "SMTP_FROM"),
        "GOTRUE_SMTP_SENDER_NAME": "Sherlock Logs",
        "GOTRUE_SMTP_HOST": smtp_host,
        "GOTRUE_SMTP_PORT": str(port),
        "GOTRUE_SMTP_USER": required(env, "SMTP_USER"),
        "GOTRUE_SMTP_PASS": required(env, "SMTP_PASSWORD"),
        "GOTRUE_HOOK_PASSWORD_VERIFICATION_ATTEMPT_ENABLED": "true",
        "GOTRUE_HOOK_PASSWORD_VERIFICATION_ATTEMPT_URI": "pg-functions://postgres/auth_guard/check_password_attempt",
        "GOTRUE_LOG_LEVEL": "error",
    }
    for action in ("CONFIRMATION", "RECOVERY", "EMAIL_CHANGE", "INVITE"):
        auth["GOTRUE_MAILER_URLPATHS_" + action] = "/auth/v1/verify"
    rest = {
        **base,
        "PGRST_DB_URI": database_url(env, "REST_DATABASE_URL"),
        "PGRST_DB_SCHEMAS": "public",
        "PGRST_DB_ANON_ROLE": "anon",
        "PGRST_JWT_SECRET": jwt,
        "PGRST_JWT_AUD": "authenticated",
        "PGRST_DB_MAX_ROWS": "1000",
        "PGRST_DB_POOL": "5",
        "PGRST_SERVER_HOST": "127.0.0.1",
        "PGRST_SERVER_PORT": "3000",
        "PGRST_LOG_LEVEL": "error",
    }
    upstream = required(env, "API_UPSTREAM")
    if not re.fullmatch(r"http://[a-z0-9][a-z0-9.-]*:8000", upstream):
        raise ValueError("API_UPSTREAM must identify the private API service on port 8000")
    if json.loads(Path("/app/public-config.json").read_text()) != {"origin": origin, "key": key}:
        raise ValueError("Rebuild the frontend for this exact public Auth configuration")
    template = Path("/app/deploy/northflank/nginx.conf.template").read_text()
    Path("/tmp/nginx.conf").write_text(
        template.replace("@@PUBLIC_KEY@@", key).replace("@@API_UPSTREAM@@", upstream)
    )
    return [
        (["auth"], auth),
        (["postgrest"], rest),
        (["nginx", "-c", "/tmp/nginx.conf", "-g", "daemon off;"], base),
    ]


def supervise(children):
    stopping = Event()
    processes = []
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stopping.set())
    status = 0
    try:
        for command, env in children:
            # Suppress provider logs: errors may otherwise persist credentials
            # from confirmation URLs. Health and exit status remain observable.
            private = command[0] in {"auth", "postgrest", "nginx"}
            processes.append(
                subprocess.Popen(
                    command,
                    env=env,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL if private else None,
                    stderr=subprocess.DEVNULL,
                )
            )
        while not stopping.wait(0.5):
            if any(process.poll() is not None for process in processes):
                print('{"status":"child_exited"}', flush=True)
                status = 1
                break
    finally:
        for process in processes:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + 10
        for process in processes:
            try:
                process.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
    return status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=("portal", "runtime"))
    args = parser.parse_args(argv)
    try:
        if os.environ.get("ADMIN_DATABASE_URL"):
            raise ValueError("The database owner credential must never enter a running service")
        children = (
            portal_children(os.environ)
            if args.service == "portal"
            else runtime_children(os.environ)
        )
        return supervise(children)
    except Exception:
        print(json.dumps({"status": "deployment_configuration_or_startup_failed"}), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
