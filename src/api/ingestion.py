"""
api/ingestion.py – POST /events/ingest endpoint.

Accepts up to 500 events per call.
  • Validates each event against the Pydantic schema
  • Deduplicates by event_id using SQLAlchemy merge (idempotent)
  • Returns per-event error details for rejected events
  • Emits X-Event-Count response header for structured logging
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.models import EventORM
from .schemas import EventIn, IngestResponse, RejectedEvent

router = APIRouter()

MAX_BATCH_SIZE = 500


@router.post(
    "/events/ingest",
    response_model=IngestResponse,
    summary="Ingest a batch of events",
    description=(
        "Accept up to 500 events per call.  Events are validated against the "
        "challenge schema and deduplicated by event_id (idempotent).  "
        "Returns a count of accepted events and details on any rejected ones."
    ),
)
async def ingest_events(
    payload: list[dict[str, Any]],
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:

    if len(payload) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=422,
            detail=f"Batch size {len(payload)} exceeds maximum {MAX_BATCH_SIZE}",
        )

    accepted = 0
    rejected: list[RejectedEvent] = []
    valid_rows: list[EventORM] = []

    for raw in payload:
        event_id = raw.get("event_id", "<missing>")
        try:
            evt = EventIn.model_validate(raw)
        except Exception as exc:
            errors = [str(e) for e in getattr(exc, "errors", lambda: [str(exc)])()]
            rejected.append(RejectedEvent(event_id=str(event_id), errors=errors))
            continue

        # Build ORM row
        ts = evt.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        row = EventORM(
            event_id=evt.event_id,
            store_id=evt.store_id,
            camera_id=evt.camera_id,
            visitor_id=evt.visitor_id,
            event_type=evt.event_type,
            timestamp=ts,
            zone_id=evt.zone_id,
            dwell_ms=evt.dwell_ms,
            confidence=evt.confidence,
            is_staff=evt.is_staff,
            session_seq=evt.session_seq,
            uncertain_reid=evt.uncertain_reid,
            metadata_=evt.metadata,
            ingested_at=datetime.now(timezone.utc),
        )
        valid_rows.append(row)

    # Bulk insert with deduplication (INSERT OR IGNORE via merge)
    if valid_rows:
        for row in valid_rows:
            await db.merge(row)   # merge = upsert-like; existing rows by PK are skipped
        accepted = len(valid_rows)

    # Emit event count for structured logging middleware
    response.headers["X-Event-Count"] = str(accepted)

    return IngestResponse(
        accepted=accepted,
        rejected=rejected,
        total=len(payload),
    )

