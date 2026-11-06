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

    def record_failures(self, run, status, start, end, seen, *, source="provider_logs"):
        with connect(self.dsn) as connection:
            if source != "provider_logs":
                return connection.execute(
                    "select private.record_failure_collection(%s,%s,%s,%s,%s,%s) as accepted",
                    (run, status, start, end, seen, source),
                ).fetchone()["accepted"]
            return connection.execute(
                "select private.record_failure_collection(%s,%s,%s,%s,%s) as accepted",
                (run, status, start, end, seen),
            ).fetchone()["accepted"]

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
            failures = failure_source_status(connection)
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
            "failed_login_coverage": failures["coverage"],
            "failure_source": failures,
            "retention_schedule": "hourly",
        }


def failure_source_status(connection) -> dict:
    installed = connection.execute("""select exists(select 1 from pg_attribute
      where attrelid=to_regclass('private.collection_state')
      and attname='failure_status' and not attisdropped) as installed""").fetchone()["installed"]
    if not installed:
        return {"coverage": "not_connected", "status": "not_configured", "healthy": False}
    has_kind = connection.execute("""select exists(select 1 from pg_attribute
      where attrelid=to_regclass('private.collection_state')
      and attname='failure_source_kind' and not attisdropped) as installed""").fetchone()[
        "installed"
    ]
    kind = "failure_source_kind" if has_kind else "'provider_logs'::text"
    row = connection.execute(f"""select failure_status as status,{kind} as source_kind,
      failure_checked_at as checked_at,failure_last_success_at as last_success_at,
      failure_window_start as window_start,failure_window_end as window_end,
      failure_seen as scanned,interval_seconds,
      (status in ('ready','running','partial') and
        (status <> 'running' or lease_until > clock_timestamp())) as collector_active
      from private.collection_state where singleton""").fetchone()
    now = datetime.now(UTC)
    fresh_seconds = max(120, 3 * row.pop("interval_seconds"))
    active = row.pop("collector_active")
    healthy = (
        active
        and row["status"] == "ready"
        and row["last_success_at"] is not None
        and row["last_success_at"] > now - timedelta(seconds=fresh_seconds)
        and row["window_end"] is not None
        and row["window_end"] > now - timedelta(seconds=fresh_seconds)
    )
    source = row["source_kind"]
    coverage = (
        "not_connected"
        if row["status"] == "not_configured"
        else "self_hosted_guard"
        if healthy and source == "self_hosted_guard"
        else "self_hosted_guard_unhealthy"
        if source == "self_hosted_guard"
        else "provider_logs_recent_window"
        if healthy
        else "provider_logs_unhealthy"
    )
    return {**row, "healthy": healthy, "coverage": coverage}
