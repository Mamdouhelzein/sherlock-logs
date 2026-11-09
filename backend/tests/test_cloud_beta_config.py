import importlib.util
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from dotenv import dotenv_values

spec = importlib.util.spec_from_file_location(
    "cloud_beta_config", Path(__file__).resolve().parents[2] / "tools/cloud_beta.py"
)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_new_credentials_are_private_and_never_overwritten(monkeypatch, tmp_path):
    env = tmp_path / ".env.public-beta.local"
    monkeypatch.setattr(setup, "ENV_FILE", env)
    values = setup.init()
    assert env.stat().st_mode & 0o077 == 0
    assert values["REGISTRATION_ENABLED"] == "false"
    passwords = [values[prefix + "_PASSWORD"] for prefix, _ in setup.ROLES.values()]
    assert len(set(passwords)) == len(passwords)
    original = env.read_bytes()
    with pytest.raises(ValueError):
        setup.init()
    assert env.read_bytes() == original


def test_runtime_connections_do_not_inherit_operator_tunnel_or_owner(monkeypatch, tmp_path):
    env = tmp_path / ".env.public-beta.local"
    monkeypatch.setattr(setup, "ENV_FILE", env)
    values = setup.init()
    values.update(
        {
            "ADMIN_DATABASE_URL": "postgresql://owner:owner-secret@canonical-db:15432/realm?"
            "sslmode=verify-full&hostaddr=127.0.0.1&sslrootcert=/operator/private.pem",
            "DATABASE_HOST": "database.internal.example",
            "DATABASE_PORT": "5432",
        }
    )
    setup.connections(values)
    saved = dotenv_values(env)
    for role, (prefix, _) in setup.ROLES.items():
        dsn = saved[prefix + "_DATABASE_URL"]
        parsed = urlsplit(dsn)
        assert parsed.username == role and parsed.password == values[prefix + "_PASSWORD"]
        assert parsed.hostname == "database.internal.example" and parsed.port == 5432
        assert parse_qs(parsed.query)["sslmode"] == ["verify-full"]
        assert parse_qs(parsed.query)["sslrootcert"] == ["/etc/ssl/certs/ca-certificates.crt"]
        assert "hostaddr" not in parse_qs(parsed.query)
        assert "owner-secret" not in dsn and "/operator/" not in dsn
