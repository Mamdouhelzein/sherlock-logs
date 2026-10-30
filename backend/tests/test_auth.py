from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from sherlock_api.auth import get_auth_client
from sherlock_api.config import Settings
from sherlock_api.main import create_app

USER = "00000000-0000-4000-8000-000000000001"
USER_DATA = {
    "id": USER,
    "email": "detective@example.test",
    "email_confirmed_at": "2026-10-30T00:00:00Z",
    "user_metadata": {"role": "admin"},
    "app_metadata": {"role": "admin"},
}
HEADERS = {"Authorization": "Bearer opaque-test-token"}


@contextmanager
def auth_client(handler):
    settings = Settings(
        _env_file=None,
        environment="test",
        supabase_url="https://project.supabase.co",
        supabase_publishable_key="sb_publishable_test_only",
    )
    app = create_app(settings)

    async def override():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            yield client

    app.dependency_overrides[get_auth_client] = override
    with TestClient(app) as client:
        yield client


def test_anonymous_requests_never_contact_supabase():
    with auth_client(lambda request: pytest.fail("Anonymous request reached upstream")) as client:
        for path in ["/api/v1/me", "/api/v1/admin/status"]:
            response = client.get(path)
            assert response.status_code == 401
            assert response.headers["www-authenticate"] == "Bearer"
        assert (
            client.get("/api/v1/me", headers={"Authorization": "Basic invalid"}).status_code == 401
        )


def test_unconfigured_auth_fails_closed():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.get("/api/v1/me", headers=HEADERS).status_code == 503


@pytest.mark.parametrize("status", [401, 403])
def test_invalid_or_expired_token_is_rejected_before_role_lookup(status):
    def handler(request):
        assert request.url.path == "/auth/v1/user"
        return httpx.Response(status, json={"message": "Sensitive upstream error"})

    with auth_client(handler) as client:
        response = client.get("/api/v1/admin/status", headers=HEADERS)
        assert response.status_code == 401
        assert "Sensitive" not in response.text


def test_roles_are_read_from_database_and_revocation_applies_on_next_request():
    role = "member"
    calls = []

    def handler(request):
        calls.append(request.url.path)
        assert request.url.host == "project.supabase.co"
        assert request.headers["authorization"] == HEADERS["Authorization"]
        assert request.headers["apikey"] == "sb_publishable_test_only"
        if request.url.path == "/auth/v1/user":
            return httpx.Response(200, json=USER_DATA)
        assert request.url.path == "/rest/v1/rpc/current_user_role"
        assert request.content == b"{}"
        return httpx.Response(200, json=role)

    with auth_client(handler) as client:
        assert client.get("/api/v1/me", headers=HEADERS).json() == {
            "id": USER,
            "email": USER_DATA["email"],
            "role": "member",
        }
        # Even forged metadata saying 'admin' cannot promote a member.
        assert client.get("/api/v1/admin/status", headers=HEADERS).status_code == 403
        role = "admin"
        response = client.get("/api/v1/admin/status", headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["user_id"] == USER
        role = "member"
        assert client.get("/api/v1/admin/status", headers=HEADERS).status_code == 403
        assert calls.count("/auth/v1/user") == 4
        assert calls.count("/rest/v1/rpc/current_user_role") == 4


@pytest.mark.parametrize(
    "failure", ["timeout", "redirect", "malformed", "unknown-role", "missing-rpc"]
)
def test_unavailable_or_malformed_upstream_never_grants_access(failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("do not expose", request=request)
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "https://untrusted.example"})
        if failure == "malformed":
            return httpx.Response(200, json={"id": "invalid"})
        if request.url.path == "/auth/v1/user":
            return httpx.Response(200, json=USER_DATA)
        if failure == "missing-rpc":
            return httpx.Response(404, json={"message": "relation details"})
        return httpx.Response(200, json="super-admin")

    with auth_client(handler) as client:
        response = client.get("/api/v1/admin/status", headers=HEADERS)
        assert response.status_code == 503
        assert response.headers["cache-control"] == "no-store"
        assert "do not expose" not in response.text
        assert "relation" not in response.text


@pytest.mark.parametrize("change", [{"is_anonymous": True}, {"email_confirmed_at": None}])
def test_only_confirmed_email_accounts_can_enter(change):
    with auth_client(lambda request: httpx.Response(200, json=USER_DATA | change)) as client:
        assert client.get("/api/v1/me", headers=HEADERS).status_code == 401


@pytest.mark.parametrize(
    "values",
    [
        {"supabase_url": "https://project.supabase.co"},
        {"supabase_publishable_key": "sb_publishable_test"},
        {
            "supabase_url": "http://untrusted.example",
            "supabase_publishable_key": "sb_publishable_test",
        },
        {
            "supabase_url": "https://project.supabase.co/path",
            "supabase_publishable_key": "sb_publishable_test",
        },
        {
            "supabase_url": "https://project.supabase.co",
            "supabase_publishable_key": "sb_secret_test",
        },
    ],
)
def test_rejects_partial_unsafe_or_privileged_config(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_cors_allows_bearer_header_but_not_untrusted_origins():
    with auth_client(lambda request: httpx.Response(401)) as client:
        response = client.options(
            "/api/v1/me",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
        response = client.options(
            "/api/v1/me",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert response.status_code == 400


def test_configuration_status_does_not_claim_live_readiness():
    with auth_client(lambda request: pytest.fail("Status must not probe auth")) as client:
        integration = client.get("/api/v1/system").json()["integrations"][0]
        assert integration["status"] == "configured"
        assert "does not probe live sign-in" in integration["detail"]
