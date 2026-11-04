"""Read-only administrator investigation endpoints. No browser scoring/activation writes."""

import base64
import json
from datetime import datetime
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from sherlock_api.auth import Identity, require_admin
from sherlock_api.detection.store import DetectionReader
from sherlock_api.telemetry.store import decode_cursor

router = APIRouter(prefix="/api/v1/admin", tags=["Detection"])


def reader(request: Request) -> DetectionReader:
    config = request.app.state.settings
    if not config.events_configured:
        raise HTTPException(503, "Detection storage is not configured.")
    return DetectionReader(config.database_url.get_secret_value(), config.event_retention_days)


def page(store_call, limit, cursor):
    try:
        before = decode_cursor(cursor) if cursor else None
    except ValueError:
        raise HTTPException(422, "Invalid investigation cursor.") from None
    try:
        result = store_call(limit, before)
    except psycopg.Error:
        raise HTTPException(
            503, "Detection storage is unavailable. Check the worker setup."
        ) from None
    rows = result["rows"]
    last = rows[-1] if result["has_more"] else None
    next_cursor = None
    if last:
        at: datetime = last.get("last_seen", last.get("occurred_at"))
        next_cursor = base64.urlsafe_b64encode(
            json.dumps([at.isoformat(), str(last["id"])]).encode()
        ).decode()
    return {"items": rows, "next_cursor": next_cursor, "mode": "shadow"}


@router.get("/detection/status")
def status(
    _identity: Annotated[Identity, Depends(require_admin)],
    store: Annotated[DetectionReader, Depends(reader)],
):
    try:
        return store.status()
    except psycopg.Error:
        raise HTTPException(
            503, "Detection storage is unavailable. Check the worker setup."
        ) from None


@router.get("/incidents")
def incidents(
    _identity: Annotated[Identity, Depends(require_admin)],
    store: Annotated[DetectionReader, Depends(reader)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
):
    return page(store.incidents, limit, cursor)


@router.get("/events/{event_id}/detection")
def event_detection(
    event_id: UUID,
    _identity: Annotated[Identity, Depends(require_admin)],
    store: Annotated[DetectionReader, Depends(reader)],
):
    try:
        result = store.event(event_id)
    except psycopg.Error:
        raise HTTPException(
            503, "Detection storage is unavailable. Check the worker setup."
        ) from None
    if result is None:
        raise HTTPException(404, "Event is unavailable or outside retention.")
    return result


@router.get("/incidents/{incident_id}")
def incident(
    incident_id: UUID,
    _identity: Annotated[Identity, Depends(require_admin)],
    store: Annotated[DetectionReader, Depends(reader)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
):
    return page(lambda size, before: store.incident(incident_id, size, before), limit, cursor)
