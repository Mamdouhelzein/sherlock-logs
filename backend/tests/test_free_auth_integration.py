"""Opt-in real Auth HTTP checks, restricted to our separate local test realm."""

import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from dotenv import dotenv_values
from psycopg import connect
from psycopg.rows import dict_row

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_FREE_AUTH") != "1", reason="Needs the isolated free Auth stack"
)
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def realm():
    values = dotenv_values(ROOT / ".env.free-auth.local")
    assert values["SUPABASE_URL"] == "http://127.0.0.1:54421"
    identities = []
    with (
        httpx.Client(
            base_url=values["SUPABASE_URL"],
            headers={"apikey": values["LOCAL_PUBLIC_KEY"]},
            trust_env=False,
            timeout=10,
            follow_redirects=False,
        ) as client,
        connect(
            host="127.0.0.1",
            port=54322,
            dbname="sherlock",
            user="postgres",
            password=values["LOCAL_DB_PASSWORD"],
            row_factory=dict_row,
            autocommit=True,
        ) as db,
    ):

        def create_account():
            email = f"guard-{uuid4().hex}@example.test"
            password = "local-fixture-" + uuid4().hex
            response = client.post("/auth/v1/signup", json={"email": email, "password": password})
            assert response.status_code == 200
            assert not response.json().get("access_token")  # Confirmation remains required.
            identity = response.json()["id"]
            identities.append(identity)
            # Only this disposable fixture is confirmed directly; browser tests exercise email/PKCE.
            db.execute(
                "update auth.users set email_confirmed_at=clock_timestamp() where id=%s",
                (identity,),
            )
            return identity, email, password

        yield client, db, create_account
        # Only UUIDs created by this fixture are removed. Never touch hosted/current app accounts.
        for identity in identities:
            db.execute("delete from auth.users where id=%s", (identity,))


def login(client, email, password, **kwargs):
    return client.post(
        "/auth/v1/token",
        params={"grant_type": "password"},
        json={"email": email, "password": password},
        **kwargs,
    )


def test_direct_auth_calls_enforce_account_guard_and_preserve_sessions(realm):
    client, db, create = realm
    identity, email, password = create()
    _, other_email, other_password = create()
    initial = login(client, email, password)
    assert initial.status_code == 200
    session = initial.json()
    unknown = login(client, f"absent-{uuid4().hex}@example.test", "wrong-fixture-password")
    assert unknown.status_code == 400
    for number in range(5):
        response = login(
            client,
            email,
            "wrong-fixture-password",
            headers={
                "X-Real-IP": f"192.0.2.{number + 1}",
                "X-Forwarded-For": f"198.51.100.{number + 1}",
            },
        )
        assert response.status_code == 400
    blocked = db.execute(
        "select * from auth_guard.password_attempts where user_id=%s", (identity,)
    ).fetchone()
    assert blocked["failures"] == 5 and blocked["blocked_until"] is not None
    assert login(client, email, password).json() == unknown.json()
    assert (
        db.execute(
            "select * from auth_guard.password_attempts where user_id=%s", (identity,)
        ).fetchone()
        == blocked
    )
    assert login(client, other_email, other_password).status_code == 200
    assert (
        client.get(
            "/auth/v1/user", headers={"Authorization": f"Bearer {session['access_token']}"}
        ).status_code
        == 200
    )
    refresh = client.post(
        "/auth/v1/token",
        params={"grant_type": "refresh_token"},
        json={"refresh_token": session["refresh_token"]},
    )
    assert refresh.status_code == 200
    assert (
        db.execute(
            "select blocked_until from auth_guard.password_attempts where user_id=%s", (identity,)
        ).fetchone()["blocked_until"]
        == blocked["blocked_until"]
    )
    db.execute(
        "update auth_guard.password_attempts set blocked_until=clock_timestamp() where user_id=%s",
        (identity,),
    )
    assert login(client, email, password).status_code == 200
    assert (
        db.execute(
            "select failures from auth_guard.password_attempts where user_id=%s", (identity,)
        ).fetchone()["failures"]
        == 0
    )


def test_real_profile_rls_roles_and_guard_are_not_browser_mutable(realm):
    client, db, create = realm
    identity, email, password = create()
    other, other_email, other_password = create()
    token = login(client, email, password).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert (
        client.post("/rest/v1/rpc/current_user_role", headers=headers, json={}).json() == "member"
    )
    db.execute("insert into private.user_roles(user_id,role) values(%s,'admin')", (identity,))
    assert client.post("/rest/v1/rpc/current_user_role", headers=headers, json={}).json() == "admin"
    response = client.patch(
        "/rest/v1/profiles",
        params={"id": f"eq.{identity}"},
        headers={**headers, "Prefer": "return=representation"},
        json={"display_name": "Local Detective"},
    )
    assert response.status_code == 200
    assert response.json()[0]["display_name"] == "Local Detective"
    second_token = login(client, other_email, other_password).json()["access_token"]
    read = client.get(
        "/rest/v1/profiles",
        params={"id": f"eq.{identity}"},
        headers={"Authorization": f"Bearer {second_token}"},
    )
    assert read.status_code == 200 and read.json() == []
    assert client.get("/rest/v1/password_attempts", headers=headers).status_code == 404
    assert (
        client.post(
            "/rest/v1/rpc/check_password_attempt",
            headers=headers,
            json={"event": {"user_id": other, "valid": True}},
        ).status_code
        == 404
    )
    db.execute("delete from private.user_roles where user_id=%s", (identity,))
    assert (
        client.post("/rest/v1/rpc/current_user_role", headers=headers, json={}).json() == "member"
    )


def test_missing_hook_permission_fails_closed(realm):
    client, db, create = realm
    _, email, password = create()
    db.execute(
        "revoke execute on function auth_guard.check_password_attempt(jsonb) "
        "from supabase_auth_admin"
    )
    try:
        response = login(client, email, password)
        assert response.status_code >= 500
        assert "access_token" not in response.json()
    finally:
        db.execute(
            "grant execute on function auth_guard.check_password_attempt(jsonb) "
            "to supabase_auth_admin"
        )


def test_gateway_checks_key_origin_and_private_routes(realm):
    client, _, _ = realm
    assert client.get("/auth/v1/admin/users").status_code == 404
    assert client.get("/auth/v1/settings", headers={"apikey": "invalid"}).status_code == 401
    assert (
        client.get("/auth/v1/settings", headers={"Origin": "http://127.0.0.1:5180"}).headers[
            "access-control-allow-origin"
        ]
        == "http://127.0.0.1:5180"
    )
    assert (
        "access-control-allow-origin"
        not in client.get(
            "/auth/v1/settings", headers={"Origin": "https://untrusted.example"}
        ).headers
    )


def test_rejections_flow_through_collection_scoring_and_admin_api(realm, tmp_path):
    from threading import Event

    from fastapi.testclient import TestClient
    from sherlock_ml.artifacts import save_experiment
    from sherlock_ml.features import build_features
    from sherlock_ml.synthetic import Config, generate
    from sherlock_ml.training import TrainingOptions, fit_from_partitions

    from sherlock_api.config import Settings
    from sherlock_api.detection.config import WorkerSettings
    from sherlock_api.detection.runtime import artifact_version
    from sherlock_api.detection.worker import Worker
    from sherlock_api.main import create_app
    from sherlock_api.telemetry.guard import collect_guard_rejections
    from sherlock_api.telemetry.scheduler import Collector, CollectorSettings
    from sherlock_api.telemetry.store import EventStore

    client, db, create = realm
    identity, email, password = create()
    token = login(client, email, password).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(5):
        assert login(client, email, "incorrect-fixture-password").status_code == 400
    assert login(client, email, password).status_code == 400
    journal = db.execute(
        "select id,reason from auth_guard.password_rejections "
        "where user_id=%s order by created_at,id",
        (identity,),
    ).fetchall()
    assert [row["reason"] for row in journal] == ["invalid_password"] * 5 + ["cooldown_rejected"]
    values = dotenv_values(ROOT / ".env.free-auth.local")
    config = {
        "supabase_url": values["SUPABASE_URL"],
        "supabase_publishable_key": values["LOCAL_PUBLIC_KEY"],
        "database_url": values["DATABASE_URL"],
        "collector_database_url": values["COLLECTOR_DATABASE_URL"],
        "worker_database_url": values["WORKER_DATABASE_URL"],
    }
    settings = CollectorSettings(_env_file=None, **config, self_hosted_guard=True)
    collector = Collector(settings)
    report = collector.cycle(Event())
    assert report["status"] == "ready", report
    assert report["failed_login_coverage"] == "self_hosted_guard"
    store = EventStore(values["DATABASE_URL"], 30)
    repeated, _, _ = collect_guard_rejections(values["COLLECTOR_DATABASE_URL"], store)
    assert repeated.complete and repeated.inserted == 0 and repeated.duplicates >= 6
    rows = db.execute(
        "select id,outcome,rejection_reason from private.security_events "
        "where user_id=%s and source='self_hosted_guard' order by occurred_at,id",
        (identity,),
    ).fetchall()
    assert len(rows) == 6 and all(row["outcome"] == "failure" for row in rows)
    assert {row["rejection_reason"] for row in rows} == {"invalid_password", "cooldown_rejected"}
    assert (
        db.execute(
            "select count(*) as n from private.security_events "
            "where user_id=%s and outcome='success'",
            (identity,),
        ).fetchone()["n"]
        >= 1
    )

    # A small deterministic CI artifact exercises real inference; it is never the deployment pin.
    scenario = Config(users=20, days=12, train_days=6, validation_days=3, attack_episodes=18)
    events, labels = generate(scenario)
    experiment = fit_from_partitions(
        build_features(events),
        labels,
        scenario,
        TrainingOptions(seed=7, trees=16, sample_sizes=(16,), false_alert_budget=5),
    )
    artifact = tmp_path / "model"
    save_experiment(artifact, experiment, {"purpose": "disposable pipeline test"})
    worker = Worker(
        WorkerSettings(
            _env_file=None,
            **config,
            model_artifact_dir=str(artifact),
            worker_model_version=artifact_version(artifact),
            worker_trust_local_artifact=True,
        )
    )
    result = worker.cycle(1000)
    assert result.status == "ready" and result.processed >= 7
    with TestClient(create_app(Settings(_env_file=None, **config))) as api:
        assert api.get("/api/v1/admin/investigation/events").status_code == 401
        assert api.get("/api/v1/admin/investigation/events", headers=headers).status_code == 403
        db.execute("insert into private.user_roles(user_id,role) values(%s,'admin')", (identity,))
        response = api.get(
            "/api/v1/admin/investigation/events", headers=headers, params={"user_id": identity}
        )
        assert response.status_code == 200
        evidence = response.json()["items"]
        assert len(evidence) >= 7
        assert all(row["job_state"] == "processed" for row in evidence)
        blocked = next(row for row in evidence if row["rejection_reason"] == "cooldown_rejected")
        detail = api.get(f"/api/v1/admin/events/{blocked['id']}/detection", headers=headers).json()
        assert "cooldown_rejection" in detail["context_warnings"]
        health = api.get("/api/v1/admin/telemetry/status", headers=headers).json()
        assert health["failed_login_coverage"] == "self_hosted_guard"
        db.execute("delete from private.user_roles where user_id=%s", (identity,))
        assert api.get("/api/v1/admin/investigation/events", headers=headers).status_code == 403
    worker.stop()
    collector.stop()
