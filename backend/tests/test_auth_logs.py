from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from sherlock_api.telemetry.auth_logs import AuthLogsUnavailable, collect_failures, failure_event
from sherlock_api.telemetry.collector import CollectionInterrupted
from sherlock_api.telemetry.scheduler import CollectorSettings

PROJECT = "a" * 20


def row(**changes):
    at = changes.pop("timestamp", (datetime.now(UTC) - timedelta(seconds=10)).isoformat())
    return {
        "id": str(uuid4()),
        "observed_at": at,
        "error_code": "invalid_credentials",
        "grant_type": "password",
        "method": "POST",
        "endpoint": "/token",
        "status": "400",
        "request_id": str(uuid4()),
        "source_ip": "192.0.2.40",
        **changes,
    }


class Store:
    retention_days = 30

    def __init__(self):
        self.events = {}

    def insert(self, events, source):
        assert source == "trusted_auth_adapter"
        inserted = 0
        for event in events:
            if event.event_id not in self.events:
                self.events[event.event_id] = event
                inserted += 1
        return SimpleNamespace(inserted=inserted, duplicates=len(events) - inserted)


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_only_explicit_provider_failures_map_and_private_fields_are_dropped():
    event = row(email="private@example.invalid", password="private-password", token="private-token")
    saved = failure_event(event, PROJECT)
    assert saved.user_id is saved.account_key is saved.user_agent is None
    assert saved.outcome == "failure"
    assert "private" not in saved.model_dump_json()
    assert saved.event_id == failure_event({**event, "id": str(uuid4())}, PROJECT).event_id
    assert saved.event_id != failure_event(event, "b" * 20).event_id
    for field, value in [
        ("error_code", "email_not_confirmed"),
        ("status", "429"),
        ("grant_type", "refresh_token"),
        ("method", "GET"),
        ("endpoint", "/"),
    ]:
        with pytest.raises(ValueError):
            failure_event({**event, field: value}, PROJECT)
    with pytest.raises(ValueError):
        failure_event({**event, "request_id": "untrusted-request-id"}, PROJECT)


def test_collection_uses_fixed_destination_narrow_projection_and_retry_deduplication():
    event = row()
    store = Store()
    requests = []

    def provider(request):
        requests.append(request)
        assert request.url.host == "api.supabase.com"
        assert request.headers["authorization"] == "Bearer private-token"
        query = request.url.params["sql"]
        assert "select *" not in query.lower()
        assert "source='auth_logs'" in query
        assert "limit 100" in query
        return httpx.Response(200, json={"result": [event], "error": None})

    with client(provider) as http:
        first, start, end = collect_failures(
            "private-token", PROJECT, store, progress=lambda: True, client=http
        )
        second, _, _ = collect_failures(
            "private-token", PROJECT, store, progress=lambda: True, client=http
        )
    assert first.complete and first.inserted == 1 and first.rejected == 0
    assert second.complete and second.duplicates == 1 and second.inserted == 0
    assert end - start == timedelta(hours=1)
    assert len(store.events) == 1 and len(requests) == 2


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"error": "private-token"}),
        httpx.Response(429, json={"error": "private-token"}),
        httpx.Response(200, json={"result": [], "error": "private-provider-error"}),
        httpx.Response(200, json={"result": None}),
        httpx.Response(200, content=b"x" * (256 * 1024 + 1)),
        httpx.Response(200, content=b"not-json"),
    ],
)
def test_provider_errors_and_response_bounds_fail_safely(response):
    with client(lambda request: response) as http:
        with pytest.raises(AuthLogsUnavailable) as error:
            collect_failures("private-token", PROJECT, Store(), progress=lambda: True, client=http)
    assert "private" not in str(error.value)


def test_incomplete_page_budget_invalid_rows_and_lease_loss_do_not_claim_complete():
    now = datetime.now(UTC) - timedelta(seconds=20)
    rows = [row(timestamp=(now + timedelta(microseconds=i)).isoformat()) for i in range(100)]
    store = Store()
    with client(lambda request, rows=rows: httpx.Response(200, json={"result": rows})) as http:
        report, _, _ = collect_failures(
            "token", PROJECT, store, progress=lambda: True, max_pages=1, client=http
        )
    assert report.inserted == 100 and not report.complete
    with client(lambda request: httpx.Response(200, json={"result": [row(status="500")]})) as http:
        report, _, _ = collect_failures(
            "token", PROJECT, Store(), progress=lambda: True, client=http
        )
    assert report.rejected == 1 and report.complete and report.inserted == 0
    checks = iter([True, False])
    store = Store()
    with client(lambda request: httpx.Response(200, json={"result": [row()]})) as http:
        with pytest.raises(CollectionInterrupted):
            collect_failures("token", PROJECT, store, progress=lambda: next(checks), client=http)
    assert not store.events


def test_nonmonotonic_cursor_and_outside_window_fail_closed():
    now = datetime.now(UTC)
    for rows in [
        [row(timestamp=(now - timedelta(hours=2)).isoformat())],
        [row(timestamp=now.isoformat()), row(timestamp=(now - timedelta(seconds=1)).isoformat())],
    ]:
        with client(lambda request, rows=rows: httpx.Response(200, json={"result": rows})) as http:
            with pytest.raises(AuthLogsUnavailable):
                collect_failures("token", PROJECT, Store(), progress=lambda: True, client=http)


def test_token_configuration_requires_scoped_token_and_matching_project():
    good = dict(
        _env_file=None,
        auth_logs_token="sbp_fc" + "x" * 32,
        auth_logs_project_ref=PROJECT,
        supabase_url=f"https://{PROJECT}.supabase.co",
        supabase_publishable_key="sb_publishable_public",
    )
    assert CollectorSettings(**good).auth_logs_max_pages == 10
    for changes in [
        {"auth_logs_token": "sbp_legacy_full_access"},
        {"auth_logs_project_ref": "b" * 20},
        {"auth_logs_token": ""},
    ]:
        with pytest.raises(ValidationError) as error:
            CollectorSettings(**{**good, **changes})
        assert "sbp_legacy_full_access" not in str(error.value)


def test_multiple_pages_advance_validated_cursor_and_do_not_skip_same_timestamp():
    at = datetime.now(UTC) - timedelta(seconds=20)
    ids = sorted(str(uuid4()) for _ in range(101))
    pages = [
        [row(id=ident, timestamp=at.isoformat()) for ident in ids[:100]],
        [row(id=ids[-1], timestamp=at.isoformat())],
    ]
    requests = []

    def provider(request):
        requests.append(request)
        return httpx.Response(200, json={"result": pages.pop(0)})

    store = Store()
    with client(provider) as http:
        report, _, _ = collect_failures("token", PROJECT, store, progress=lambda: True, client=http)
    assert report.complete and report.inserted == 101
    assert ids[99] in requests[1].url.params["sql"]
    assert "and (toDateTime64(timestamp,6),id) >" in requests[1].url.params["sql"]
