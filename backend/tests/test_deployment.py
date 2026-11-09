"""Public packaging must fail closed and keep unrelated credentials out of children."""

import json
from pathlib import Path

import pytest

from sherlock_api import deployment
from sherlock_api.telemetry.scheduler import CollectorSettings


def config():
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PUBLIC_ORIGIN": "https://sherlock.example.test",
        "PUBLIC_KEY": "sb_publishable_" + "a" * 32,
        "JWT_SECRET": "a" * 64,
        "ADMIN_DATABASE_URL": "postgresql://owner:owner-password@db/realm?sslmode=verify-full",
        **{
            name
            + "_DATABASE_URL": f"postgresql://{name.lower()}:private@db/realm?sslmode=verify-full"
            for name in ("AUTH", "REST", "API", "INGEST", "AUDIT", "SCORING")
        },
        "API_UPSTREAM": "http://private-api:8000",
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_FROM": "sender@example.com",
        "SMTP_USER": "private-smtp-user",
        "SMTP_PASSWORD": "private-smtp-password",
        "UNRELATED_ACCESS_TOKEN": "unrelated-private-token",
    }


def test_runtime_credentials_are_restricted_to_their_process():
    children = deployment.runtime_children(config())
    api, collector, worker = [values for _, values in children]
    assert "api:private" in api["DATABASE_URL"]
    assert "ingest:private" in collector["DATABASE_URL"]
    assert "audit:private" in collector["COLLECTOR_DATABASE_URL"]
    assert "scoring:private" in worker["WORKER_DATABASE_URL"]
    assert not api["COLLECTOR_DATABASE_URL"] and not api["WORKER_DATABASE_URL"]
    assert not worker["DATABASE_URL"] and not worker["COLLECTOR_DATABASE_URL"]
    assert worker["WORKER_MODEL_VERSION"] == deployment.MODEL_VERSION
    assert worker["WORKER_TRUST_LOCAL_ARTIFACT"] == "true"
    for values in (api, collector, worker):
        assert values["ENVIRONMENT"] == "production"
        assert all(
            key not in values
            for key in (
                "JWT_SECRET",
                "ADMIN_DATABASE_URL",
                "AUTH_DATABASE_URL",
                "SMTP_PASSWORD",
                "UNRELATED_ACCESS_TOKEN",
            )
        )
    CollectorSettings(_env_file=None, **{key.lower(): value for key, value in collector.items()})


@pytest.mark.parametrize(
    "change",
    [
        {"PUBLIC_ORIGIN": "http://public.example.com"},
        {"PUBLIC_ORIGIN": "https://public.example.com/path"},
        {"PUBLIC_ORIGIN": "https://example.supabase.co"},
        {"PUBLIC_KEY": "service_role_secret"},
        {"API_DATABASE_URL": "postgresql://api:private@db/realm?sslmode=require"},
        {"SCORING_DATABASE_URL": "postgresql://worker:private@db/realm"},
    ],
)
def test_public_configuration_rejects_unprotected_or_ambiguous_realms(change):
    with pytest.raises(ValueError):
        deployment.runtime_children({**config(), **change})


def test_self_hosted_collection_cannot_mix_hosted_provider_tokens():
    base = dict(
        _env_file=None,
        environment="production",
        allowed_origins="https://beta.example.com",
        supabase_url="https://beta.example.com",
        supabase_publishable_key="sb_publishable_test",
        self_hosted_guard=True,
    )
    assert CollectorSettings(**base).self_hosted_guard
    for change in (
        {"auth_logs_token": "sbp_fc" + "a" * 30, "auth_logs_project_ref": "a" * 20},
        {"supabase_url": "https://example.supabase.co"},
        {"environment": "development"},
    ):
        with pytest.raises(ValueError):
            CollectorSettings(**{**base, **change})


def test_portal_signup_closed_and_provider_listeners_private(monkeypatch, tmp_path):
    template = Path(__file__).resolve().parents[2] / "deploy/northflank/nginx.conf.template"
    actual_read = Path.read_text
    actual_write = Path.write_text

    def read(path, *args, **kwargs):
        if str(path) == "/app/public-config.json":
            return json.dumps({"origin": config()["PUBLIC_ORIGIN"], "key": config()["PUBLIC_KEY"]})
        return actual_read(
            template if str(path) == "/app/deploy/northflank/nginx.conf.template" else path,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        Path,
        "read_text",
        read,
    )
    monkeypatch.setattr(
        Path,
        "write_text",
        lambda path, *args, **kwargs: actual_write(
            tmp_path / "nginx.conf" if str(path) == "/tmp/nginx.conf" else path, *args, **kwargs
        ),
    )
    auth, rest, gateway = [values for _, values in deployment.portal_children(config())]
    assert auth["GOTRUE_API_HOST"] == rest["PGRST_SERVER_HOST"] == "127.0.0.1"
    assert auth["GOTRUE_DISABLE_SIGNUP"] == "true"
    assert auth["GOTRUE_MAILER_AUTOCONFIRM"] == "false"
    assert auth["GOTRUE_HOOK_PASSWORD_VERIFICATION_ATTEMPT_ENABLED"] == "true"
    assert auth["GOTRUE_URI_ALLOW_LIST"] == (
        "https://sherlock.example.test/auth/callback,https://sherlock.example.test/reset-password"
    )
    for values in (auth, rest, gateway):
        assert "ADMIN_DATABASE_URL" not in values
        assert "UNRELATED_ACCESS_TOKEN" not in values
    assert "GOTRUE_SMTP_PASS" not in rest
    assert "GOTRUE_JWT_SECRET" not in gateway and "PGRST_JWT_SECRET" not in gateway
    rendered = (tmp_path / "nginx.conf").read_text()
    assert "@@" not in rendered and "http://private-api:8000" in rendered
    assert "private-smtp-password" not in rendered and "a" * 64 not in rendered
    with pytest.raises(ValueError):
        deployment.portal_children({**config(), "PUBLIC_ORIGIN": "https://wrong.example.test"})


@pytest.mark.parametrize(
    "change",
    [
        {"SMTP_HOST": "mail"},
        {"SMTP_HOST": "localhost"},
        {"SMTP_HOST": "mail.example.test"},
        {"JWT_SECRET": "weak-secret"},
        {"REGISTRATION_ENABLED": "yes"},
        {"API_UPSTREAM": "http://api:8000; malicious"},
        {"AUTH_DATABASE_URL": "postgresql://auth:private@db/realm?sslmode=disable"},
    ],
)
def test_portal_rejects_insecure_configuration_before_any_file_write(change):
    with pytest.raises(ValueError):
        deployment.portal_children({**config(), **change})


def test_unconfigured_entrypoint_does_not_expose_credentials(monkeypatch, capsys):
    monkeypatch.setattr(deployment.os, "environ", {"PUBLIC_ORIGIN": "private-input\nsecret"})
    assert deployment.main(["runtime"]) == 2
    output = capsys.readouterr().out
    assert json.loads(output)["status"] == "deployment_configuration_or_startup_failed"
    assert "secret" not in output
