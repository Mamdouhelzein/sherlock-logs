"""Bounded provider-log adapter. No browser reports or inferred failures are trusted."""

import json
import re
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
from pydantic import ValidationError

from sherlock_api.telemetry.collector import CollectionInterrupted, CollectionReport
from sherlock_api.telemetry.models import LoginEvent


class AuthLogsUnavailable(Exception):
    """Safe public error: never attach a request, token or provider response."""


def failure_event(row: dict, project: str) -> LoginEvent:
    if not (
        row.get("error_code") == "invalid_credentials"
        and row.get("grant_type") == "password"
        and row.get("method") == "POST"
        and row.get("endpoint") == "/token"
        and str(row.get("status")) == "400"
    ):
        raise ValueError("Not a verified invalid-password credential attempt")
    # Request IDs deduplicate repeated provider records, independently of log-row ID.
    request_id = str(UUID(row["request_id"]))
    at = datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
    return LoginEvent(
        event_id=uuid5(NAMESPACE_URL, f"supabase-auth-failure:{project}:{request_id}"),
        occurred_at=at,
        outcome="failure",
        source_ip=row.get("source_ip") or None,
        # Invalid credentials do not establish an account identity. Do not guess it.
        user_id=None,
        account_key=None,
        user_agent=None,
    )


def logs_query(after: tuple[datetime, UUID] | None, start: datetime, end: datetime) -> str:
    # All interpolated cursor components are validated timestamps/UUIDs, never raw SQL.
    def timestamp(at):
        return "parseDateTime64BestEffort('" + at.astimezone(UTC).isoformat() + "',6)"

    cursor = ""
    if after:
        cursor = (
            f"and (toDateTime64(timestamp,6),id) > ({timestamp(after[0])},'{UUID(str(after[1]))}')"
        )
    return f"""select id,toString(toDateTime64(timestamp,6)) as observed_at,
      JSONExtractString(event_message,'error_code') as error_code,
      JSONExtractString(event_message,'grant_type') as grant_type,
      JSONExtractString(event_message,'method') as method,
      JSONExtractString(event_message,'path') as endpoint,
      toString(JSONExtractInt(event_message,'status')) as status,
      JSONExtractString(event_message,'request_id') as request_id,
      JSONExtractString(event_message,'remote_addr') as source_ip
    from logs where source='auth_logs'
      and timestamp >= {timestamp(start)} and timestamp <= {timestamp(end)}
      and JSONExtractString(event_message,'error_code')='invalid_credentials'
      and JSONExtractString(event_message,'grant_type')='password'
      and JSONExtractString(event_message,'method')='POST'
      and JSONExtractString(event_message,'path')='/token'
      and JSONExtractInt(event_message,'status')=400
      {cursor} order by toDateTime64(timestamp,6),id limit 100"""


def collect_failures(token: str, project: str, store, *, progress, max_pages=10, client=None):
    """Rescan the last hour, bounded to 100 rows/page and a finite page budget."""
    if not re.fullmatch(r"[a-z]{20}", project) or not 1 <= max_pages <= 100:
        raise ValueError("Invalid bounded log collection configuration")
    end = datetime.now(UTC)
    start = end - timedelta(hours=1)
    report = CollectionReport(failed_login_coverage="provider_logs_recent_window")
    owned = client is None
    client = client or httpx.Client(timeout=10, follow_redirects=False, trust_env=False)
    after = None
    try:
        for _ in range(max_pages):
            if not progress():
                raise CollectionInterrupted()
            try:
                with client.stream(
                    "GET",
                    f"https://api.supabase.com/v1/projects/{project}/analytics/endpoints/logs",
                    headers={"Authorization": f"Bearer {token}"},
                    params={
                        "sql": logs_query(after, start, end),
                        "iso_timestamp_start": start.isoformat(),
                        "iso_timestamp_end": end.isoformat(),
                    },
                ) as response:
                    if response.status_code != 200:
                        raise AuthLogsUnavailable() from None
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        if len(body) + len(chunk) > 256 * 1024:
                            raise AuthLogsUnavailable() from None
                        body.extend(chunk)
                payload = json.loads(body)
                rows = payload.get("result")
                if payload.get("error") or not isinstance(rows, list) or len(rows) > 100:
                    raise AuthLogsUnavailable() from None
            except (httpx.HTTPError, ValueError, TypeError, AttributeError):
                raise AuthLogsUnavailable() from None
            valid = []
            previous = after
            for row in rows:
                # A malformed cursor could loop, skip records, or poison a whole window.
                try:
                    at = datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
                    if at.tzinfo is None:
                        at = at.replace(tzinfo=UTC)  # ClickHouse DateTime64 is documented UTC.
                    position = (at.astimezone(UTC), UUID(row["id"]))
                    if not start <= position[0] <= end or (previous and position <= previous):
                        raise ValueError()
                except (KeyError, TypeError, ValueError):
                    raise AuthLogsUnavailable() from None
                previous = position
                report.scanned += 1
                try:
                    event = failure_event({**row, "observed_at": position[0].isoformat()}, project)
                    event.validate_time(end, store.retention_days)
                    valid.append(event)
                except (KeyError, ValidationError, ValueError, TypeError):
                    report.rejected += 1
            if not progress():
                raise CollectionInterrupted()
            if valid:
                result = store.insert(valid, "trusted_auth_adapter")
                report.inserted += result.inserted
                report.duplicates += result.duplicates
            if len(rows) < 100:
                report.complete = True
                return report, start, end
            after = previous
        return report, start, end
    finally:
        if owned:
            client.close()
