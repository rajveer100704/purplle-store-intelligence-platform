"""
api/heatmap.py – GET /stores/{store_id}/heatmap endpoint.

Returns zone engagement metrics: visit counts, average dwell, and a
computed engagement score (0–100) normalized across all zones.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.models import EventORM
from .schemas import HeatmapResponse, ZoneHeatmap

router = APIRouter()


@router.get(
    "/stores/{store_id}/heatmap",
    response_model=HeatmapResponse,
    summary="Get zone engagement heatmap",
)
async def get_heatmap(
    store_id: str,
    db: AsyncSession = Depends(get_db),
) -> HeatmapResponse:

    base = and_(
        EventORM.store_id == store_id,
        EventORM.is_staff == False,  # noqa: E712
        EventORM.zone_id.isnot(None),
    )

    # ── Visit counts per zone (distinct visitor_id with ZONE_ENTER) ────────
    visit_q = await db.execute(
        select(
            EventORM.zone_id,
            func.count(func.distinct(EventORM.visitor_id)).label("visits"),
        ).where(
            base, EventORM.event_type == "ZONE_ENTER"
        ).group_by(EventORM.zone_id)
    )
    visits_by_zone: dict[str, int] = {
        row.zone_id: row.visits for row in visit_q.fetchall()
    }

    # ── Avg dwell per zone (from ZONE_DWELL events, in seconds) ───────────
    dwell_q = await db.execute(
        select(
            EventORM.zone_id,
            func.avg(EventORM.dwell_ms).label("avg_dwell_ms"),
        ).where(
            base,
            EventORM.event_type == "ZONE_DWELL",
            EventORM.dwell_ms.isnot(None),
        ).group_by(EventORM.zone_id)
    )
    dwell_by_zone: dict[str, float] = {
        row.zone_id: (row.avg_dwell_ms or 0.0) / 1000
        for row in dwell_q.fetchall()
    }

    # ── Combine and compute engagement score ──────────────────────────────
    all_zones = set(visits_by_zone) | set(dwell_by_zone)

    if not all_zones:
        return HeatmapResponse(
            store_id=store_id,
            zones={},
            computed_at=datetime.now(timezone.utc),
        )

    from ..layout.parser import load_store_config
    from ..config import STORE_CONFIG_PATH
    config = load_store_config(STORE_CONFIG_PATH, store_id)
    brand_map = config.zone_brand_map() if config else {}

    max_visits = max(visits_by_zone.values(), default=1)
    max_dwell = max(dwell_by_zone.values(), default=1.0)

    zones: dict[str, ZoneHeatmap] = {}
    for zone_id in sorted(all_zones):
        visits = visits_by_zone.get(zone_id, 0)
        avg_dwell_s = round(dwell_by_zone.get(zone_id, 0.0), 1)

        # Engagement score: weighted blend of normalised visits (40%) + dwell (60%)
        visit_norm = (visits / max_visits) if max_visits else 0
        dwell_norm = (avg_dwell_s / (max_dwell + 1e-6)) if max_dwell else 0
        score = int((0.4 * visit_norm + 0.6 * dwell_norm) * 100)

        zones[zone_id] = ZoneHeatmap(
            visits=visits,
            avg_dwell_s=avg_dwell_s,
            score=score,
            brand=brand_map.get(zone_id),
        )

    return HeatmapResponse(
        store_id=store_id,
        zones=zones,
        computed_at=datetime.now(timezone.utc),
    )

