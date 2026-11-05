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
