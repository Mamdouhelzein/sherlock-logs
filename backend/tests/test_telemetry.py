import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from sherlock_api.auth import Identity, require_identity
from sherlock_api.config import Settings
from sherlock_api.main import create_app
from sherlock_api.telemetry import api
from sherlock_api.telemetry.collector import audit_event
from sherlock_api.telemetry.models import EventPage, IngestionResult, LoginEvent
from sherlock_api.telemetry.store import EventConflict, decode_cursor

KEY = "test-ingestion-signing-key-at-least-32-bytes"
USER = uuid4()


def event_data(**changes):
    return {
        "event_id": str(uuid4()),
        "occurred_at": datetime.now(UTC).isoformat(),
        "outcome": "failure",
        "account_key": "a" * 64,
        "source_ip": "192.0.2.1",
    } | changes


class RecordingStore:
    def __init__(self):
        self.calls = []
        self.failure = None

    def insert(self, events, source):
        if self.failure:
            raise self.failure
        self.calls.append((events, source))
        return IngestionResult(inserted=len(events), duplicates=0)

    def list(self, limit, cursor):
        self.calls.append((limit, cursor))
        return EventPage(events=[], next_cursor=None)


@pytest.fixture
def telemetry(monkeypatch):
    settings = Settings(
        _env_file=None,
        environment="test",
        ingestion_signing_key=KEY,
        database_url="postgresql://test@localhost/test",
    )
    store = RecordingStore()
    monkeypatch.setattr(api, "EventStore", lambda dsn, retention_days: store)
    app = create_app(settings)
    with TestClient(app) as client:
        yield client, app, store


def signed(client, payload=None, *, body=None, timestamp=None, key=KEY):
    raw = body if body is not None else json.dumps(payload).encode()
    timestamp = str(timestamp if timestamp is not None else int(time.time()))
    signature = hmac.new(key.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return client.post(
        "/api/v1/internal/events",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Sherlock-Timestamp": timestamp,
            "X-Sherlock-Signature": f"v1={signature}",
        },
    )


def test_signed_service_events_preserve_facts_and_bind_the_source(telemetry):
    client, _, store = telemetry
    response = signed(client, {"events": [event_data()]})
    assert response.status_code == 200
    assert response.json() == {"inserted": 1, "duplicates": 0}
    assert store.calls[0][1] == "trusted_auth_adapter"
    assert store.calls[0][0][0].outcome == "failure"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer user-token"},
        {
            "Authorization": "Bearer admin-token",
            "X-Sherlock-Timestamp": "1",
            "X-Sherlock-Signature": "v1=" + "0" * 64,
        },
    ],
)
def test_browser_and_admin_tokens_cannot_author_events(telemetry, headers):
    client, _, store = telemetry
    assert (
        client.post(
            "/api/v1/internal/events", json={"events": [event_data()]}, headers=headers
        ).status_code
        == 401
    )
    assert not store.calls


@pytest.mark.parametrize("offset", [-301, 301])
def test_replay_window_rejects_stale_or_future_signatures(telemetry, offset):
    client, _, store = telemetry
    assert (
        signed(client, {"events": [event_data()]}, timestamp=int(time.time()) + offset).status_code
        == 401
    )
    assert not store.calls


def test_tampered_signature_is_rejected(telemetry):
    client, _, store = telemetry
    assert signed(client, {"events": [event_data()]}, key="wrong-key").status_code == 401
    assert not store.calls


@pytest.mark.parametrize(
    "change",
    [
        {"password": "do-not-reflect-this-secret"},
        {"access_token": "do-not-reflect-this-secret"},
        {"source": "supabase_audit"},
        {"processing_status": "processed"},
        {"occurred_at": "2026-10-01T00:00:00"},
        {"event_id": "not-a-uuid"},
        {"source_ip": "not-an-address"},
        {"source_ip": "fe80::1%eth0"},
        {"occurred_at": 1793354400},
        {"account_key": "raw-email@example.test"},
        {"user_agent": "x" * 513},
        {"user_agent": "bad\r\nheader"},
        {"outcome": "maybe"},
        {"occurred_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
        {"occurred_at": (datetime.now(UTC) - timedelta(days=31)).isoformat()},
    ],
)
def test_rejects_unsafe_events_without_echoing_or_saving_inputs(telemetry, change):
    client, _, store = telemetry
    response = signed(client, {"events": [event_data(**change)]})
    assert response.status_code == 422
    assert "do-not-reflect" not in response.text
    assert "raw-email" not in response.text
    assert not store.calls


@pytest.mark.parametrize(
    "payload",
    [
        {"events": []},
        {"events": [event_data()] * 101},
        {"events": [event_data()], "token": "secret"},
    ],
)
def test_rejects_empty_or_overlarge_batches_and_unknown_fields(telemetry, payload):
    client, _, store = telemetry
    assert signed(client, payload).status_code == 422
    assert not store.calls


def test_caps_body_size_and_sanitizes_storage_failures(telemetry):
    client, _, store = telemetry
    assert signed(client, body=b"x" * (api.MAX_BODY_BYTES + 1)).status_code == 413
    store.failure = psycopg.OperationalError("postgresql://secret@private/db")
    response = signed(client, {"events": [event_data()]})
    assert response.status_code == 503
    assert "private" not in response.text
    store.failure = EventConflict()
    assert signed(client, {"events": [event_data()]}).status_code == 409


def test_event_reads_require_server_verified_admin_and_validate_pagination(telemetry):
    client, app, store = telemetry
    assert client.get("/api/v1/admin/events").status_code == 401
    app.dependency_overrides[require_identity] = lambda: Identity(
        id=USER, email="a@example.test", role="member"
    )
    assert client.get("/api/v1/admin/events").status_code == 403
    assert not store.calls
    app.dependency_overrides[require_identity] = lambda: Identity(
        id=USER, email="a@example.test", role="admin"
    )
    assert client.get("/api/v1/admin/events").json() == {"events": [], "next_cursor": None}
    assert client.get("/api/v1/admin/events?limit=101").status_code == 422
    assert client.get("/api/v1/admin/events?cursor=invalid").status_code == 422


def test_audit_normalization_discards_raw_payload_secrets_and_never_infers_failure():
    row = {
        "id": uuid4(),
        "created_at": datetime.now(UTC),
        "action": "login",
        "actor_id": str(USER),
        "ip_address": "",
        "email": "private@example.test",
        "password": "secret",
        "traits": {"token": "secret"},
    }
    event = audit_event(row)
    assert event.outcome == "success"
    assert event.source_ip is None and event.user_agent is None
    assert "private@example" not in event.model_dump_json()
    assert "secret" not in event.model_dump_json()
    with pytest.raises(ValueError):
        audit_event(row | {"action": "token_refreshed"})


def test_utc_canonicalization_makes_retries_equivalent():
    data = event_data(occurred_at="2026-10-30T12:00:00+02:00")
    first = LoginEvent.model_validate(data)
    second = LoginEvent.model_validate(data | {"occurred_at": "2026-10-30T10:00:00Z"})
    assert first.digest() == second.digest()


@pytest.mark.parametrize("cursor", ["[]", "*" * 100, "a" * 300, "bnVsbA==", "WzEsMl0="])
def test_invalid_cursors_are_rejected(cursor):
    with pytest.raises(ValueError):
        decode_cursor(cursor)


def test_rejects_short_keys_and_hides_database_secrets_in_config_errors():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ingestion_signing_key="short")
    with pytest.raises(ValidationError) as result:
        Settings(_env_file=None, database_url="https://secret:password@example.test/db")
    assert "secret:password" not in str(result.value)
