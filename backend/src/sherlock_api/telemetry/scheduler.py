"""Separate collection daemon with fenced leases and aggregate-only reporting."""

import argparse
import json
import signal
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import uuid4

import psycopg
from pydantic import Field, SecretStr, ValidationError, model_validator

from sherlock_api.config import Settings
from sherlock_api.telemetry.auth_logs import AuthLogsUnavailable, collect_failures
from sherlock_api.telemetry.collector import CollectionInterrupted, collect_once
from sherlock_api.telemetry.operations import CollectionOperations
from sherlock_api.telemetry.store import EventConflict, EventStore


class CollectorSettings(Settings):
    collection_interval_seconds: int = Field(default=30, ge=10, le=900)
    collection_max_pages: int = Field(default=1000, ge=1, le=100000)
    auth_logs_token: SecretStr = SecretStr("")
    auth_logs_project_ref: str = Field(default="", pattern=r"^$|^[a-z]{20}$")
    auth_logs_max_pages: int = Field(default=10, ge=1, le=100)

    @model_validator(mode="after")
    def validate_log_access(self):
        token = self.auth_logs_token.get_secret_value()
        if bool(token) != bool(self.auth_logs_project_ref):
            raise ValueError("Set both Auth log settings, or neither")
        if token and (
            not token.startswith("sbp_fc")
            or not 20 <= len(token) <= 512
            or any(char.isspace() for char in token)
        ):
            raise ValueError("Use a scoped read-only Supabase token")
        if token and self.supabase_url != f"https://{self.auth_logs_project_ref}.supabase.co":
            raise ValueError("Auth log project must match the configured Auth project")
        return self


class Collector:
    def __init__(self, settings, *, operations=None, store=None, collect=collect_once):
        self.settings = settings
        self.operations = operations or CollectionOperations(
            settings.database_url.get_secret_value()
        )
        self.store = store or EventStore(
            settings.database_url.get_secret_value(), settings.event_retention_days
        )
        self.collect = collect
        self.run_id = None
        self.failures = 0

    def cycle(self, stopping: Event) -> dict:
        interval = self.settings.collection_interval_seconds
        result = {
            "status": "ready",
            "delay_seconds": interval,
            "scanned": 0,
            "inserted": 0,
            "duplicates": 0,
            "rejected": 0,
            "failed_login_coverage": "not_connected",
        }
        counts = {name: 0 for name in ("scanned", "inserted", "duplicates", "rejected")}
        run = uuid4()
        try:
            lease = self.operations.begin(run, self.settings.event_retention_days, interval)
            if lease is None:
                return {**result, "status": "waiting"}
            self.run_id = run

            def progress():
                return not stopping.is_set() and self.operations.progress(run)

            status, error = "ready", None
            try:
                report = self.collect(
                    self.settings.collector_database_url.get_secret_value(),
                    self.store,
                    max_pages=self.settings.collection_max_pages,
                    window_start=None
                    if lease["full_scan"]
                    else datetime.now(UTC) - timedelta(hours=1),
                    progress=progress,
                )
                counts = report.model_dump(include=set(counts))
                if self.settings.auth_logs_token.get_secret_value():
                    try:
                        failures, start, end = collect_failures(
                            self.settings.auth_logs_token.get_secret_value(),
                            self.settings.auth_logs_project_ref,
                            self.store,
                            progress=progress,
                            max_pages=self.settings.auth_logs_max_pages,
                        )
                        complete = failures.complete and not failures.rejected
                        accepted = self.operations.record_failures(
                            run, "ready" if complete else "partial", start, end, failures.scanned
                        )
                        for name in counts:
                            counts[name] += getattr(failures, name)
                        if not complete:
                            status, error = "partial", "incomplete_scan"
                        result["failed_login_coverage"] = (
                            "provider_logs_recent_window" if complete else "provider_logs_unhealthy"
                        )
                    except AuthLogsUnavailable:
                        accepted = self.operations.record_failures(run, "error", None, None, 0)
                        status, error = "partial", "incomplete_scan"
                        result["failed_login_coverage"] = "provider_logs_unhealthy"
                    if not accepted:
                        raise CollectionInterrupted()
                if not report.complete or report.rejected:
                    status, error = "partial", "incomplete_scan"
            except CollectionInterrupted:
                status = "stopped" if stopping.is_set() else "lease_lost"
            except EventConflict:
                status, error = "error", "event_conflict"
            except (ValidationError, ValueError):
                status, error = "error", "invalid_source"
            except psycopg.Error:
                status, error = "error", "source_or_storage_unavailable"
            self.failures = 0 if status == "ready" else min(self.failures + 1, 5)
            delay = min(900, interval * 2**self.failures)
            if status != "lease_lost" and not self.operations.finish(
                run, status, counts, error, delay
            ):
                status = "lease_lost"
            return {
                **result,
                **counts,
                "status": status,
                "delay_seconds": delay,
                "full_scan": lease["full_scan"],
            }
        except psycopg.Error:
            return {
                **result,
                "status": "storage_unavailable",
                "delay_seconds": min(900, interval * 2),
            }

    def stop(self):
        if self.run_id is not None:
            try:
                self.operations.stop(self.run_id)
            except psycopg.Error:
                pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "collect-once"])
    args = parser.parse_args(argv)
    try:
        settings = CollectorSettings()
        if not settings.events_configured or not settings.collector_database_url.get_secret_value():
            raise ValueError("Collector configuration is missing")
    except (ValidationError, ValueError):
        print(json.dumps({"status": "configuration_required"}))
        return 2
    stopping = Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stopping.set())
    collector = Collector(settings)
    try:
        while not stopping.is_set():
            result = collector.cycle(stopping)
            print(json.dumps(result), flush=True)
            if args.command == "collect-once":
                return 0 if result["status"] == "ready" else 2
            stopping.wait(result["delay_seconds"])
    finally:
        collector.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
