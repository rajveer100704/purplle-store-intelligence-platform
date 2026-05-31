"""
api/anomalies.py – GET /stores/{store_id}/anomalies endpoint.

Runs all three anomaly detectors against live event data and returns
current anomalies with severity and remediation actions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.models import EventORM
from ..anomaly_engine import AnomalyEngine
from .schemas import AnomaliesResponse, AnomalyItem

router = APIRouter()


@router.get(
    "/stores/{store_id}/anomalies",
    response_model=AnomaliesResponse,
    summary="Get active anomalies for a store",
)
async def get_anomalies(
    store_id: str,
    db: AsyncSession = Depends(get_db),
) -> AnomaliesResponse:

    now = datetime.now(timezone.utc)
    base = and_(
        EventORM.store_id == store_id,
        EventORM.is_staff == False,  # noqa: E712
    )

    # ── Discover zone IDs for this store ───────────────────────────────────
    zones_q = await db.execute(
        select(EventORM.zone_id)
        .where(base, EventORM.zone_id.isnot(None))
        .distinct()
    )
    zone_ids = [row[0] for row in zones_q.fetchall()]

    engine = AnomalyEngine(store_id=store_id, zone_ids=zone_ids)

    # ── Feed queue depth history (last 30 min) ─────────────────────────────
    cutoff_30min = now - timedelta(minutes=30)
    queue_hist_q = await db.execute(
        select(EventORM.timestamp, EventORM.event_type).where(
            base,
            EventORM.event_type.in_(["BILLING_QUEUE_JOIN", "BILLING_QUEUE_ABANDON"]),
            EventORM.timestamp >= cutoff_30min,
        ).order_by(EventORM.timestamp)
    )
    depth = 0
    for ts, etype in queue_hist_q.fetchall():
        if etype == "BILLING_QUEUE_JOIN":
            depth += 1
        else:
            depth = max(0, depth - 1)
        engine.update_queue_depth(depth, ts.timestamp())

    # ── Feed conversion history (last 7 days) ─────────────────────────────
    cutoff_7d = now - timedelta(days=7)
    daily_q = await db.execute(
        select(
            func.date(EventORM.timestamp).label("day"),
            func.count(func.distinct(EventORM.visitor_id)).label("entries"),
        ).where(
            base,
            EventORM.event_type == "ENTRY",
            EventORM.timestamp >= cutoff_7d,
        ).group_by(func.date(EventORM.timestamp))
    )
    # We need daily purchase proxy too
    daily_purchase_q = await db.execute(
        select(
            func.date(EventORM.timestamp).label("day"),
            func.count(func.distinct(EventORM.visitor_id)).label("purchased"),
        ).where(
            EventORM.store_id == store_id,
            EventORM.is_staff == False,  # noqa
            EventORM.event_type == "BILLING_QUEUE_JOIN",
            EventORM.timestamp >= cutoff_7d,
        ).group_by(func.date(EventORM.timestamp))
    )
    entries_by_day = {row.day: row.entries for row in daily_q.fetchall()}
    purchased_by_day = {row.day: row.purchased for row in daily_purchase_q.fetchall()}

    for day, entries in entries_by_day.items():
        if entries > 0:
            rate = (purchased_by_day.get(day, 0) / entries) * 100
            engine.update_conversion_rate(rate, str(day))

    # ── Feed zone activity timestamps ─────────────────────────────────────
    for zone_id in zone_ids:
        last_q = await db.execute(
            select(func.max(EventORM.timestamp)).where(
                base,
                EventORM.zone_id == zone_id,
            )
        )
        last_ts = last_q.scalar()
        if last_ts:
            engine.update_zone_activity(zone_id, last_ts.timestamp())

    # ── Run detection ─────────────────────────────────────────────────────
    raw_anomalies = engine.detect()

    anomaly_items = [
        AnomalyItem(
            type=a["type"],
            severity=a["severity"],
            store_id=store_id,
            action=a.get("action", ""),
            details={k: v for k, v in a.items()
                     if k not in {"type", "severity", "store_id", "action"}},
        )
        for a in raw_anomalies
    ]

    return AnomaliesResponse(
        store_id=store_id,
        anomalies=anomaly_items,
        computed_at=now,
    )
