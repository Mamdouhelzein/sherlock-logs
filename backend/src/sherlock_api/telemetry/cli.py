"""Operator commands. Output contains aggregate counts only, never raw log entries."""

import argparse
import json

import psycopg
from pydantic import ValidationError

from sherlock_api.config import Settings
from sherlock_api.telemetry.collector import collect_once, inspect_audit_schema
from sherlock_api.telemetry.store import EventConflict, EventStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inspect-source", "collect-once", "purge-expired"])
    parser.add_argument("--max-pages", type=int, default=1000)
    args = parser.parse_args()
    try:
        if not 1 <= args.max_pages <= 100000:
            raise ValueError("Invalid page limit")
        settings = Settings()
        if args.command == "inspect-source":
            dsn = settings.collector_database_url.get_secret_value()
            if not dsn:
                raise ValueError("Collector connection is missing")
            print(json.dumps(inspect_audit_schema(dsn)))
            return 0
        if not settings.events_configured:
            raise ValueError("Event connection is missing")
        store = EventStore(settings.database_url.get_secret_value(), settings.event_retention_days)
        if args.command == "purge-expired":
            print(json.dumps({"deleted": store.purge()}))
            return 0
        source_dsn = settings.collector_database_url.get_secret_value()
        if not source_dsn:
            raise ValueError("Collector connection is missing")
        report = collect_once(source_dsn, store, max_pages=args.max_pages)
        print(report.model_dump_json())
        return 0 if report.complete and report.rejected == 0 else 2
    except (psycopg.Error, ValidationError, ValueError, EventConflict):
        print(
            json.dumps(
                {
                    "error": (
                        "Telemetry command failed. Check configuration, permissions, migrations, "
                        "and source schema. No raw provider data is printed."
                    )
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
