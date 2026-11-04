"""Bounded retry-safe cycles. Reports contain counts/status only, never event facts."""

from dataclasses import asdict, dataclass
from pathlib import Path
from time import monotonic
from uuid import uuid4

import psycopg

from sherlock_api.detection.runtime import ModelRuntime
from sherlock_api.detection.store import WorkerStore


@dataclass
class WorkerReport:
    status: str = "ready"
    mode: str = "shadow"
    claimed: int = 0
    processed: int = 0
    flagged: int = 0
    retried: int = 0
    lost_leases: int = 0

    def record(self):
        return asdict(self)


class Worker:
    def __init__(self, settings, *, store=None, runtime=None):
        self.settings = settings
        self.id = uuid4()
        self.store = store or WorkerStore(
            settings.worker_database_url.get_secret_value(),
            settings.event_retention_days,
            settings.worker_lease_seconds,
            settings.worker_history_limit,
        )
        self.runtime = runtime

    def cycle(self, max_jobs: int = 100, stopping=None) -> WorkerReport:
        report = WorkerReport()
        if not 1 <= max_jobs <= 1000:
            raise ValueError("Use 1–1000 jobs per cycle")
        try:
            if self.runtime is None:
                try:
                    self.runtime = ModelRuntime(
                        Path(self.settings.model_artifact_dir),
                        self.settings.worker_model_version,
                        trusted=self.settings.worker_trust_local_artifact,
                    )
                except Exception:
                    self.store.heartbeat(self.id, None, "model_unavailable")
                    report.status = "model_unavailable"
                    return report
            self.store.register(self.runtime)
            self.store.heartbeat(self.id, self.runtime.version, "ready")
            last_heartbeat = monotonic()
            for _ in range(max_jobs):
                if stopping is not None and stopping.is_set():
                    break
                if monotonic() - last_heartbeat >= 30:
                    self.store.heartbeat(self.id, self.runtime.version, "ready")
                    last_heartbeat = monotonic()
                claim = self.store.claim(self.runtime.version)
                if claim is None:
                    break
                report.claimed += 1
                if claim.history_overflow:
                    accepted = self.store.fail(claim, "history_limit")
                    report.retried += int(accepted)
                    report.lost_leases += int(not accepted)
                    continue
                try:
                    result = self.runtime.score(claim)
                    accepted = self.store.complete(claim, result)
                    report.processed += int(accepted)
                    report.flagged += int(accepted and result.flagged)
                    report.lost_leases += int(not accepted)
                except Exception:
                    # An uncertain commit may already be processed. Fail is token-guarded.
                    accepted = self.store.fail(claim, "scoring_failed")
                    report.retried += int(accepted)
                    report.lost_leases += int(not accepted)
            self.store.heartbeat(self.id, self.runtime.version, "ready")
        except psycopg.Error:
            report.status = "database_unavailable"
        return report

    def stop(self):
        try:
            self.store.heartbeat(self.id, self.runtime.version if self.runtime else None, "stopped")
        except psycopg.Error:
            pass
