import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from sherlock_api.config import Settings
from sherlock_api.main import create_app


@pytest.fixture
def client():
    settings = Settings(_env_file=None, environment="test")
    with TestClient(create_app(settings)) as instance:
        yield instance


def test_liveness_does_not_claim_future_services_are_ready(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["cache-control"] == "no-store"
    snapshot = client.get("/api/v1/system").json()
    assert snapshot["stage"] == "telemetry"
    assert snapshot["uptime_seconds"] >= 0
    assert snapshot["checked_at"].endswith("Z")
    assert {item["status"] for item in snapshot["integrations"]} == {
        "not_configured",
        "not_trained",
    }


def test_cors_allows_configured_frontend_and_rejects_other_origins(client):
    for origin in ["http://localhost:5173", "http://127.0.0.1:5173"]:
        response = client.get("/api/v1/system", headers={"Origin": origin})
        assert response.headers["access-control-allow-origin"] == origin
    response = client.get("/api/v1/system", headers={"Origin": "https://untrusted.example"})
    assert "access-control-allow-origin" not in response.headers
    response = client.options(
        "/api/v1/system",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "origins", ["*", "", "http://localhost:5173/path", "https://a,,", "https://*.example.com"]
)
def test_rejects_invalid_origin_configuration(origins):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, allowed_origins=origins)


def test_production_requires_https_and_hides_developer_docs():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production", allowed_origins="http://example.com")
    settings = Settings(
        _env_file=None, environment="production", allowed_origins="https://example.com"
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/healthz").status_code == 200


def test_no_event_ingestion_or_login_routes_are_exposed_yet(client):
    assert client.post("/api/v1/events", json={"success": True}).status_code == 404
    assert client.post("/login").status_code == 404
