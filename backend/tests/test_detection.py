from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from sherlock_api.auth import get_auth_client
from sherlock_api.config import Settings
from sherlock_api.detection.api import reader
from sherlock_api.detection.config import WorkerSettings
from sherlock_api.detection.store import Claim
from sherlock_api.detection.worker import Worker
from sherlock_api.main import create_app


class Store:
    def __init__(self):
        self.claims = [Claim({"id": str(uuid4())}, uuid4(), [], datetime.now(UTC), False, False)]
        self.completed = []
        self.failed = []
        self.beats = []
        self.accept = True

    def register(self, runtime):
        pass

    def heartbeat(self, *args):
        self.beats.append(args[-1])

    def claim(self, version):
        return self.claims.pop(0) if self.claims else None

    def complete(self, claim, result):
        self.completed.append(result)
        return self.accept

    def fail(self, claim, code):
        self.failed.append(code)
        return self.accept


def settings():
    return WorkerSettings(_env_file=None)


def test_worker_finalizes_or_reports_a_lost_lease_without_double_counting():
    store = Store()
    runtime = SimpleNamespace(version="a" * 64, score=lambda claim: SimpleNamespace(flagged=True))
    report = Worker(settings(), store=store, runtime=runtime).cycle()
    assert report.processed == report.flagged == report.claimed == 1
    assert report.mode == "shadow"
    assert store.beats == ["ready", "ready"]
    store = Store()
    store.accept = False
    report = Worker(settings(), store=store, runtime=runtime).cycle()
    assert report.processed == report.flagged == 0
    assert report.lost_leases == 1


def test_model_outage_does_not_claim_or_consume_events(monkeypatch):
    store = Store()

    def unavailable(*args, **kwargs):
        raise ValueError("private-path-or-credential")

    monkeypatch.setattr("sherlock_api.detection.worker.ModelRuntime", unavailable)
    report = Worker(settings(), store=store).cycle()
    assert report.status == "model_unavailable"
    assert report.claimed == 0 and len(store.claims) == 1
    assert "private" not in str(report.record())
    assert store.beats == ["model_unavailable"]


def test_history_overflow_and_scoring_failure_release_a_bounded_retry():
    store = Store()
    store.claims[0].history_overflow = True
    runtime = SimpleNamespace(
        version="a" * 64, score=lambda claim: pytest.fail("Overflow was scored")
    )
    report = Worker(settings(), store=store, runtime=runtime).cycle()
    assert report.retried == 1 and store.failed == ["history_limit"]
    store = Store()

    def failed(claim):
        raise ValueError("do-not-log-this-event")

    runtime.score = failed
    report = Worker(settings(), store=store, runtime=runtime).cycle()
    assert report.retried == 1 and store.failed == ["scoring_failed"]
    assert "do-not-log" not in str(report.record())


def test_database_failure_reports_unavailable_and_does_not_expose_credentials():
    store = Store()

    def failed(*args):
        raise psycopg.OperationalError("postgres://sensitive-connection")

    store.register = failed
    report = Worker(settings(), store=store, runtime=SimpleNamespace(version="a" * 64)).cycle()
    assert report.status == "database_unavailable" and report.claimed == 0
    assert "postgres" not in str(report.record())


def test_api_guard_is_server_enforced_before_storage_and_rechecks_revocation():
    app = create_app(
        Settings(
            _env_file=None,
            supabase_url="https://project.supabase.co",
            supabase_publishable_key="sb_publishable_fixture",
        )
    )
    role = "member"

    def upstream(request):
        if request.url.path == "/auth/v1/user":
            return httpx.Response(
                200,
                json={
                    "id": str(uuid4()),
                    "email": "fixture@example.test",
                    "email_confirmed_at": "2026-01-01T00:00:00Z",
                },
            )
        return httpx.Response(200, json=role)

    async def client_override():
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            yield client

    class Reader:
        def status(self):
            return {"mode": "shadow", "queue": {"pending": 1}}

        def incidents(self, *args):
            return {"rows": [], "has_more": False}

        def incident(self, *args):
            return {"rows": [], "has_more": False}

        def events(self, *args, **kwargs):
            return {"rows": [], "has_more": False}

        def event(self, *args):
            return None

    app.dependency_overrides[get_auth_client] = client_override
    app.dependency_overrides[reader] = lambda: Reader()
    paths = [
        "/api/v1/admin/detection/status",
        "/api/v1/admin/incidents",
        f"/api/v1/admin/incidents/{uuid4()}",
        "/api/v1/admin/investigation/events",
        f"/api/v1/admin/events/{uuid4()}/detection",
    ]
    headers = {"Authorization": "Bearer opaque-fixture"}
    with TestClient(app) as client:
        for path in paths:
            assert client.get(path).status_code == 401
            assert client.get(path, headers=headers).status_code == 403
        role = "admin"
        assert client.get(paths[0], headers=headers).json()["mode"] == "shadow"
        assert client.get(paths[1], headers=headers).json()["items"] == []
        assert client.get(paths[1] + "?cursor=bad", headers=headers).status_code == 422
        assert client.get(paths[3], headers=headers).json()["items"] == []
        for filters in ["cursor=bad", "user_id=bad", "account_key=bad", "outcome=bad", "limit=101"]:
            assert client.get(paths[3] + "?" + filters, headers=headers).status_code == 422
        assert (
            client.get(
                paths[3] + f"?user_id={uuid4()}&account_key={'a' * 64}", headers=headers
            ).status_code
            == 422
        )
        assert client.get(paths[-1], headers=headers).status_code == 404
        role = "member"
        assert client.get(paths[0], headers=headers).status_code == 403
