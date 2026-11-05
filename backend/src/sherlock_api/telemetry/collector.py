"""Read-only Supabase audit adapter. Only 'login' audit entries map to successes.

Invalid-credential attempts are not represented by this adapter. Never infer
failure from a missing success, or an actual source IP from a proxy address.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from psycopg import sql
from pydantic import BaseModel, ValidationError

from sherlock_api.telemetry.models import LoginEvent
from sherlock_api.telemetry.store import EventStore, connect


class CollectionReport(BaseModel):
    scanned: int = 0
    inserted: int = 0
    duplicates: int = 0
    rejected: int = 0
    complete: bool = False
    failed_login_coverage: str = "unavailable_from_audit_adapter"


class CollectionInterrupted(Exception):
    """Lease loss or graceful shutdown: do not publish a successful scan."""


def audit_event(row: dict) -> LoginEvent:
    if row.get("action") != "login":
        raise ValueError("Unsupported audit action")
    # Only allowlisted fields leave the provider query; no raw email/traits/payload.
    return LoginEvent(
        event_id=row["id"],
        occurred_at=row["created_at"],
        outcome="success",
        user_id=row.get("actor_id") or None,
        source_ip=row.get("ip_address") or None,
        user_agent=row.get("user_agent") or None,
    )


def inspect_audit_schema(dsn: str) -> dict:
    with connect(dsn) as connection:
        rows = connection.execute(
            """select column_name from information_schema.columns
            where table_schema = 'private' and table_name = 'login_audit_source'"""
        ).fetchall()
        columns = {row["column_name"] for row in rows}
        required = {"id", "created_at", "action", "actor_id", "user_agent", "ip_address"}
        if not required <= columns:
            raise ValueError("Required audit columns are missing or inaccessible")
        # Schema visibility is not proof of SELECT privilege.
        connection.execute(
            "select id, created_at, action, actor_id, user_agent, ip_address "
            "from private.login_audit_source limit 0"
        )
    return {
        "schema_accessible": True,
        "source_projection": "private.login_audit_source",
        "ip_column_available": "ip_address" in columns,
        "supported_action": "login",
        "failed_login_coverage": "unavailable_from_audit_adapter",
        "live_event_coverage_verified": False,
    }


def collect_once(
    source_dsn: str,
    store: EventStore,
    *,
    batch_size: int = 100,
    max_pages: int = 1000,
    window_start: datetime | None = None,
    progress: Callable[[], bool] | None = None,
) -> CollectionReport:
    if not 1 <= batch_size <= 100 or not 1 <= max_pages <= 100000:
        raise ValueError("Use bounded collection pages")
    if window_start is not None and window_start.tzinfo is None:
        raise ValueError("Use timezone-aware collection windows")
    schema = inspect_audit_schema(source_dsn)
    report = CollectionReport()
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=store.retention_days)
    if window_start is not None:
        if window_start > now:
            raise ValueError("Collection window starts in the future")
        cutoff = max(cutoff, window_start)
    # Re-scan the retention window each run. A timestamp watermark alone can
    # permanently miss transactions which commit late with an earlier timestamp.
    after: tuple[datetime, UUID] | None = None
    ip_column = sql.SQL("ip_address") if schema["ip_column_available"] else sql.SQL("null::text")
    for _ in range(max_pages):
        if progress is not None and not progress():
            raise CollectionInterrupted()
        with connect(source_dsn) as connection:
            where_cursor = sql.SQL("and (created_at,id) > (%s,%s)") if after else sql.SQL("")
            query = sql.SQL("""select id, created_at, action, actor_id, user_agent,
                {} as ip_address from private.login_audit_source
                where action = 'login' and created_at >= %s and created_at <= %s
                {} order by created_at,id limit %s""").format(ip_column, where_cursor)
            parameters = (cutoff, now, *(after or ()), batch_size)
            rows = connection.execute(query, parameters).fetchall()
        valid = []
        for row in rows:
            report.scanned += 1
            try:
                event = audit_event(row)
                event.validate_time(now, store.retention_days)
                valid.append(event)
            except (ValidationError, ValueError):
                report.rejected += 1
        if valid:
            result = store.insert(valid, "supabase_audit")
            report.inserted += result.inserted
            report.duplicates += result.duplicates
        if progress is not None and not progress():
            raise CollectionInterrupted()
        if len(rows) < batch_size:
            report.complete = True
            return report
        last = rows[-1]
        after = (last["created_at"], last["id"])
    return report
