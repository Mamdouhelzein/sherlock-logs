from threading import Event
from types import SimpleNamespace

import psycopg
import pytest

from sherlock_api.telemetry.collector import CollectionInterrupted, CollectionReport
from sherlock_api.telemetry.scheduler import Collector, CollectorSettings, main
from sherlock_api.telemetry.store import EventConflict


class Operations:
    def __init__(self, full=True):
        self.lease = {"full_scan": full}
        self.finished = []
        self.progress_ok = True
        self.accept = True

    def begin(self, *args):
        return self.lease

    def progress(self, run):
        return self.progress_ok

    def finish(self, *args):
        self.finished.append(args)
        return self.accept

    def stop(self, run):
        pass


def settings():
    return CollectorSettings(_env_file=None)


def test_full_then_recent_collection_and_busy_run_are_bounded():
    operations = Operations()
    windows = []

    def collect(source, store, **kwargs):
        assert kwargs["progress"]()
        windows.append(kwargs["window_start"])
        return CollectionReport(scanned=1, inserted=1, complete=True)

    collector = Collector(
        settings(), operations=operations, store=SimpleNamespace(), collect=collect
    )
    assert collector.cycle(Event())["inserted"] == 1
    assert windows == [None]
    operations.lease = {"full_scan": False}
    assert collector.cycle(Event())["status"] == "ready"
    assert windows[-1].tzinfo is not None
    operations.lease = None
    assert collector.cycle(Event())["status"] == "waiting"
    assert len(windows) == 2


@pytest.mark.parametrize(
    "exception,code",
    [
        (psycopg.OperationalError("private-database-credential"), "source_or_storage_unavailable"),
        (ValueError("private-source-payload"), "invalid_source"),
        (EventConflict(), "event_conflict"),
    ],
)
def test_failures_back_off_and_publish_only_safe_error_codes(exception, code):
    operations = Operations()

    def failed(*args, **kwargs):
        raise exception

    collector = Collector(
        settings(), operations=operations, store=SimpleNamespace(), collect=failed
    )
    assert collector.cycle(Event())["delay_seconds"] == 60
    assert collector.cycle(Event())["delay_seconds"] == 120
    assert operations.finished[-1][3] == code
    assert "private" not in str(operations.finished)
    for _ in range(8):
        assert collector.cycle(Event())["delay_seconds"] <= 900


def test_partial_scans_stopping_and_lease_loss_cannot_claim_success():
    operations = Operations()
    collector = Collector(
        settings(),
        operations=operations,
        store=SimpleNamespace(),
        collect=lambda *args, **kwargs: CollectionReport(
            scanned=2, inserted=1, rejected=1, complete=True
        ),
    )
    assert collector.cycle(Event())["status"] == "partial"
    assert operations.finished[-1][1] == "partial"

    def interrupted(*args, **kwargs):
        assert not kwargs["progress"]()
        raise CollectionInterrupted()

    collector.collect = interrupted
    operations.progress_ok = False
    count = len(operations.finished)
    assert collector.cycle(Event())["status"] == "lease_lost"
    assert len(operations.finished) == count
    stopping = Event()
    stopping.set()
    assert collector.cycle(stopping)["status"] == "stopped"
    operations.progress_ok = True
    operations.accept = False
    collector.collect = lambda *args, **kwargs: CollectionReport(complete=True)
    assert collector.cycle(Event())["status"] == "lease_lost"


def test_unconfigured_startup_does_not_connect_or_echo_settings(monkeypatch, capsys):
    monkeypatch.setattr("sherlock_api.telemetry.scheduler.CollectorSettings", settings)
    assert main(["collect-once"]) == 2
    assert capsys.readouterr().out.strip() == '{"status": "configuration_required"}'


def test_verified_failure_collection_and_provider_outage_keep_honest_status(monkeypatch):
    from datetime import UTC, datetime, timedelta

    from sherlock_api.telemetry.auth_logs import AuthLogsUnavailable

    operations = Operations()
    recorded = []
    operations.record_failures = lambda *args: recorded.append(args) or True
    config = CollectorSettings(
        _env_file=None,
        auth_logs_token="sbp_fc" + "x" * 32,
        auth_logs_project_ref="a" * 20,
        supabase_url="https://" + "a" * 20 + ".supabase.co",
        supabase_publishable_key="sb_publishable_public",
    )
    end = datetime.now(UTC)
    monkeypatch.setattr(
        "sherlock_api.telemetry.scheduler.collect_failures",
        lambda *args, **kwargs: (
            CollectionReport(scanned=2, inserted=2, complete=True),
            end - timedelta(hours=1),
            end,
        ),
    )
    collector = Collector(
        config,
        operations=operations,
        store=SimpleNamespace(),
        collect=lambda *args, **kwargs: CollectionReport(scanned=1, duplicates=1, complete=True),
    )
    result = collector.cycle(Event())
    assert result["status"] == "ready" and result["scanned"] == 3 and result["inserted"] == 2
    assert result["failed_login_coverage"] == "provider_logs_recent_window"
    assert recorded[-1][1] == "ready"

    def failed(*args, **kwargs):
        raise AuthLogsUnavailable()

    monkeypatch.setattr("sherlock_api.telemetry.scheduler.collect_failures", failed)
    result = collector.cycle(Event())
    assert result["status"] == "partial" and result["duplicates"] == 1
    assert result["failed_login_coverage"] == "provider_logs_unhealthy"
    assert recorded[-1][1] == "error" and recorded[-1][-1] == 0
    assert operations.finished[-1][1] == "partial"
