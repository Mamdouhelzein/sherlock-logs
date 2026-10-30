"""Service-signed ingestion and administrator-only reads; no client event authority."""

import hashlib
import hmac
import re
import time
from datetime import UTC, datetime
from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from sherlock_api.auth import Identity, require_admin
from sherlock_api.telemetry.models import EventBatch, EventPage, IngestionResult
from sherlock_api.telemetry.store import EventConflict, EventStore, decode_cursor

router = APIRouter(prefix="/api/v1", tags=["Telemetry"])
MAX_BODY_BYTES = 128 * 1024


def get_event_store(request: Request) -> EventStore:
    config = request.app.state.settings
    if not config.events_configured:
        raise HTTPException(503, "Event storage is not configured.")
    return EventStore(config.database_url.get_secret_value(), config.event_retention_days)


@router.post("/internal/events", response_model=IngestionResult)
async def ingest(request: Request) -> IngestionResult:
    """HMAC-authenticated service input. A user/admin bearer token cannot authorize writes."""
    timestamp = request.headers.get("X-Sherlock-Timestamp", "")
    signature = request.headers.get("X-Sherlock-Signature", "")
    if not re.fullmatch(r"[0-9]{1,12}", timestamp) or not re.fullmatch(
        r"v1=[a-f0-9]{64}", signature
    ):
        raise HTTPException(401, "A valid service signature is required.")
    if abs(time.time() - int(timestamp)) > 300:
        raise HTTPException(401, "Service signature has expired.")
    config = request.app.state.settings
    key = config.ingestion_signing_key.get_secret_value()
    if not key or not config.events_configured:
        raise HTTPException(503, "Event ingestion is not configured.")
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Send application/json.")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            raise HTTPException(413, "Event batch is too large.")
        body.extend(chunk)
    expected = (
        "v1=" + hmac.new(key.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    )
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "A valid service signature is required.")
    try:
        batch = EventBatch.model_validate_json(body)
        now = datetime.now(UTC)
        for event in batch.events:
            event.validate_time(now, config.event_retention_days)
    except (ValidationError, ValueError):
        # Never reflect rejected input: it could contain passwords or tokens.
        raise HTTPException(
            422, "Invalid event batch. Check the documented schema and time window."
        ) from None
    store = get_event_store(request)
    try:
        return await run_in_threadpool(store.insert, batch.events, "trusted_auth_adapter")
    except EventConflict:
        raise HTTPException(
            409, "An event ID was reused with different facts; no events were saved."
        ) from None
    except ValueError:
        raise HTTPException(422, "Event timestamp is outside the collection window.") from None
    except psycopg.Error:
        raise HTTPException(
            503, "Event storage is unavailable. Retry the same event IDs."
        ) from None


@router.get("/admin/events", response_model=EventPage)
def events(
    _identity: Annotated[Identity, Depends(require_admin)],
    store: Annotated[EventStore, Depends(get_event_store)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> EventPage:
    if cursor:
        try:
            decode_cursor(cursor)
        except ValueError:
            raise HTTPException(422, "Invalid event cursor.") from None
    try:
        return store.list(limit, cursor)
    except psycopg.Error:
        raise HTTPException(503, "Event storage is unavailable. Try again shortly.") from None
