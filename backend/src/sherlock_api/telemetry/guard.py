"""Read-only minimal rejection journal; never infer an incorrect password from a block."""

from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from sherlock_api.telemetry.collector import CollectionInterrupted, CollectionReport
from sherlock_api.telemetry.models import LoginEvent
from sherlock_api.telemetry.store import connect


def collect_guard_rejections(source_dsn, store, *, max_pages=1000, progress=None):
    if not 1 <= max_pages <= 100000:
        raise ValueError("Use bounded collection pages")
    end = datetime.now(UTC)
    start = end - timedelta(days=store.retention_days)
    report = CollectionReport(failed_login_coverage="self_hosted_guard")
    after = None
    # Full retained window each time: find late commits and catch up after sleep.
    for _ in range(max_pages):
        if progress is not None and not progress():
            raise CollectionInterrupted()
        with connect(source_dsn) as connection:
            cursor = "and (created_at,id) > (%s,%s)" if after else ""
            rows = connection.execute(
                f"""select id,created_at,user_id,reason from private.password_rejection_source
                where created_at >= %s and created_at <= %s {cursor}
                order by created_at,id limit 100""",
                (start, end, *(after or ())),
            ).fetchall()
        valid = []
        for row in rows:
            report.scanned += 1
            try:
                event = LoginEvent(
                    event_id=row["id"],
                    occurred_at=row["created_at"],
                    user_id=row["user_id"],
                    outcome="failure",
                    rejection_reason=row["reason"],
                )
                event.validate_time(end, store.retention_days)
                valid.append(event)
            except (ValueError, ValidationError):
                report.rejected += 1
        if valid:
            result = store.insert(valid, "self_hosted_guard")
            report.inserted += result.inserted
            report.duplicates += result.duplicates
        if progress is not None and not progress():
            raise CollectionInterrupted()
        if len(rows) < 100:
            report.complete = True
            break
        after = (rows[-1]["created_at"], rows[-1]["id"])
    return report, start, end
