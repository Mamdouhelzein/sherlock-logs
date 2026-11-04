"""Operate the separate scoring worker. No raw events, credentials, or errors are logged."""

import argparse
import json
import signal
from threading import Event

from pydantic import ValidationError

from sherlock_api.detection.config import WorkerSettings
from sherlock_api.detection.worker import Worker


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["process-once", "run"])
    parser.add_argument("--max-jobs", type=int, default=100)
    args = parser.parse_args(argv)
    try:
        settings = WorkerSettings()
        if not settings.worker_database_url.get_secret_value() or not 1 <= args.max_jobs <= 1000:
            raise ValueError("Worker configuration is missing")
    except (ValidationError, ValueError):
        print(json.dumps({"status": "configuration_required"}))
        return 2
    worker = Worker(settings)
    stopping = Event()
    if args.command == "run":
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, lambda *_: stopping.set())
    try:
        while not stopping.is_set():
            report = worker.cycle(args.max_jobs, stopping)
            print(json.dumps(report.record()), flush=True)
            if args.command == "process-once":
                return 0 if report.status == "ready" else 2
            stopping.wait(settings.worker_poll_seconds)
    finally:
        worker.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
