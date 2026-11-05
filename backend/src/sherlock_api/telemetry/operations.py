"""Private aggregate operational state; no provider payloads or credentials in results."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from psycopg.types.json import Jsonb

from sherlock_api.telemetry.store import connect


class CollectionOperations:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def begin(self, run: UUID, days: int, interval: int) -> dict | None:
        with connect(self.dsn) as connection:
            return connection.execute(
                "select private.begin_collection_run(%s,%s,%s) as run", (run, days, interval)
            ).fetchone()["run"]

    def progress(self, run: UUID) -> bool:
        with connect(self.dsn) as connection:
            return connection.execute(
                "select private.collection_progress(%s) as accepted", (run,)
            ).fetchone()["accepted"]

    def finish(self, run: UUID, status: str, counts: dict, error: str | None, delay: int) -> bool:
        with connect(self.dsn) as connection:
            return connection.execute(
                "select private.finish_collection_run(%s,%s,%s,%s,%s) as accepted",
                (run, status, Jsonb(counts), error, delay),
            ).fetchone()["accepted"]

    def stop(self, run: UUID) -> None:
        with connect(self.dsn) as connection:
            connection.execute("select private.stop_collection_run(%s)", (run,))

    def status(self) -> dict:
        # Never serialize lease identifiers in administrator responses.
        with connect(self.dsn) as connection:
            collection = connection.execute("""select status,heartbeat_at,started_at,finished_at,
              last_success_at,last_full_scan_at,last_full_retention_days,next_run_at,interval_seconds,retention_days,
              scan_full,counts,error_code,lease_until > clock_timestamp() as lease_fresh
              from private.collection_state where singleton""").fetchone()
            retention = connection.execute("""select enabled,keep_days,status,last_started_at,
              last_finished_at,last_success_at,deleted,backlog,error_code
              from private.retention_state where singleton""").fetchone()
        now = datetime.now(UTC)
        collection["full_scan_overdue"] = (
            collection["last_full_scan_at"] is None
            or collection["last_full_scan_at"] < now - timedelta(hours=7)
            or collection["last_full_retention_days"] != collection["retention_days"]
        )
        collection["healthy"] = (
            collection["status"] == "ready"
            and collection["last_success_at"] is not None
            and collection["last_success_at"]
            > now - timedelta(seconds=max(120, 3 * collection["interval_seconds"]))
            and not collection["full_scan_overdue"]
        )
        retention["healthy"] = (
            retention["enabled"]
            and retention["status"] == "ready"
            and retention["last_success_at"] is not None
            and retention["last_success_at"] > now - timedelta(hours=2)
        )
        return {
            "collection": collection,
            "retention": retention,
            "failed_login_coverage": "not_connected",
            "retention_schedule": "hourly",
        }
