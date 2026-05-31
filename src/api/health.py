"""
api/health.py – GET /health endpoint.

Returns:
  • status: "OK" or "DEGRADED"
  • last_event_per_store: {store_id → ISO timestamp of most recent event}
  • stale_feeds: list of store IDs with no events in last 10 minutes
  • db_event_count: total rows in events table
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.models import EventORM
from .schemas import HealthResponse

router = APIRouter()

STALE_FEED_MINUTES = int(os.environ.get("STALE_FEED_MINUTES", "10"))


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System health check",
)
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(minutes=STALE_FEED_MINUTES)

    # ── Last event per store ───────────────────────────────────────────────
    q = await db.execute(
        select(
            EventORM.store_id,
            func.max(EventORM.timestamp).label("last_ts"),
        ).group_by(EventORM.store_id)
    )
    rows = q.fetchall()

    last_event_per_store: dict[str, str] = {}
    stale_feeds: list[str] = []

    for store_id, last_ts in rows:
        if last_ts is None:
            stale_feeds.append(store_id)
            continue
        # Ensure tz-aware
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        last_event_per_store[store_id] = last_ts.isoformat()
        if last_ts < stale_cutoff:
            stale_feeds.append(store_id)

    # ── Total event count ──────────────────────────────────────────────────
    count_q = await db.execute(select(func.count()).select_from(EventORM))
    db_event_count = count_q.scalar() or 0

    status = "DEGRADED" if stale_feeds else "OK"

    return HealthResponse(
        status=status,
        last_event_per_store=last_event_per_store,
        stale_feeds=stale_feeds,
        db_event_count=db_event_count,
        checked_at=now,
    )
