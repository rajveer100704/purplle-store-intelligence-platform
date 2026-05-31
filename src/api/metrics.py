"""
api/metrics.py – GET /stores/{store_id}/metrics endpoint.

Computes real-time metrics by querying the event store:
  • footfall / unique_visitors (excludes staff)
  • conversion_rate = purchases / unique_visitors × 100
  • avg_dwell_per_zone (from ZONE_DWELL events)
  • queue_depth (active BILLING_QUEUE_JOIN without matching ABANDON or EXIT)
  • abandonment_rate = BILLING_QUEUE_ABANDON / BILLING_QUEUE_JOIN × 100
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.models import EventORM
from .schemas import MetricsResponse

router = APIRouter()


@router.get(
    "/stores/{store_id}/metrics",
    response_model=MetricsResponse,
    summary="Get real-time store metrics",
)
async def get_metrics(
    store_id: str,
    db: AsyncSession = Depends(get_db),
) -> MetricsResponse:

    base = and_(
        EventORM.store_id == store_id,
        EventORM.is_staff == False,  # noqa: E712
    )

    # ── Footfall: distinct visitor_ids with ENTRY events ───────────────────
    entry_q = await db.execute(
        select(func.count(func.distinct(EventORM.visitor_id))).where(
            base,
            EventORM.event_type == "ENTRY",
        )
    )
    footfall = entry_q.scalar() or 0

    # ── Unique visitors (distinct visitor_id across any event) ─────────────
    unique_q = await db.execute(
        select(func.count(func.distinct(EventORM.visitor_id))).where(base)
    )
    unique_visitors = unique_q.scalar() or 0

    # ── Conversion: visitors who purchased (POS-matched if available, else queue fallback) ──
    from ..db.models import POSTransactionORM
    pos_count_q = await db.execute(
        select(func.count()).where(
            POSTransactionORM.store_id == store_id,
            POSTransactionORM.matched == True
        )
    )
    has_pos = (pos_count_q.scalar() or 0) > 0

    if has_pos:
        purchased_q = await db.execute(
            select(func.count(func.distinct(POSTransactionORM.visitor_id))).where(
                POSTransactionORM.store_id == store_id,
                POSTransactionORM.matched == True
            )
        )
        purchased = purchased_q.scalar() or 0
    else:
        join_subq = (
            select(EventORM.visitor_id)
            .where(base, EventORM.event_type == "BILLING_QUEUE_JOIN")
            .distinct()
            .subquery()
        )
        abandon_subq = (
            select(EventORM.visitor_id)
            .where(base, EventORM.event_type == "BILLING_QUEUE_ABANDON")
            .distinct()
            .subquery()
        )
        purchased_q = await db.execute(
            select(func.count(func.distinct(EventORM.visitor_id))).where(
                EventORM.visitor_id.in_(select(join_subq)),
                EventORM.visitor_id.not_in(select(abandon_subq)),
                EventORM.store_id == store_id,
                EventORM.is_staff == False,  # noqa: E712
            )
        )
        purchased = purchased_q.scalar() or 0

    conversion_rate = (purchased / unique_visitors * 100) if unique_visitors else 0.0

    # ── Avg dwell per zone ─────────────────────────────────────────────────
    dwell_q = await db.execute(
        select(EventORM.zone_id, func.avg(EventORM.dwell_ms)).where(
            base,
            EventORM.event_type == "ZONE_DWELL",
            EventORM.zone_id.isnot(None),
            EventORM.dwell_ms.isnot(None),
        ).group_by(EventORM.zone_id)
    )
    avg_dwell_per_zone = {
        zone: round((ms or 0) / 1000, 1)
        for zone, ms in dwell_q.fetchall()
    }

    # ── Queue depth: JOIN count − ABANDON count (active visitors in queue) ─
    join_count_q = await db.execute(
        select(func.count()).where(
            base, EventORM.event_type == "BILLING_QUEUE_JOIN"
        )
    )
    join_count = join_count_q.scalar() or 0

    abandon_count_q = await db.execute(
        select(func.count()).where(
            base, EventORM.event_type == "BILLING_QUEUE_ABANDON"
        )
    )
    abandon_count = abandon_count_q.scalar() or 0

    queue_depth = max(0, join_count - abandon_count)
    abandonment_rate = (
        (abandon_count / join_count * 100) if join_count else 0.0
    )

    # ── Brand-level conversion and matched revenue computation ─────────────
    from ..layout.parser import load_store_config
    from ..config import STORE_CONFIG_PATH, POS_CSV_PATH
    from ..pos.parser import parse_pos_csv

    # 1. Total matched revenue
    rev_q = await db.execute(
        select(func.sum(POSTransactionORM.amount)).where(
            POSTransactionORM.store_id == store_id,
            POSTransactionORM.matched == True
        )
    )
    total_revenue = rev_q.scalar()
    if total_revenue is not None:
        total_revenue = round(float(total_revenue), 2)

    # 2. Brand conversion stats (visited_brand ∩ purchased_brand)
    # Load all distinct visitor-zone visits
    visits_q = await db.execute(
        select(EventORM.visitor_id, EventORM.zone_id).where(
            base,
            EventORM.event_type == "ZONE_ENTER",
            EventORM.zone_id.isnot(None)
        ).distinct()
    )
    visitor_zones: dict[str, set[str]] = {}
    brand_visitors: dict[str, int] = {}
    for row in visits_q.fetchall():
        visitor_zones.setdefault(row.visitor_id, set()).add(row.zone_id)
        brand_visitors[row.zone_id] = brand_visitors.get(row.zone_id, 0) + 1

    # Load matched transactions and their brands
    matched_txns_q = await db.execute(
        select(POSTransactionORM.txn_id, POSTransactionORM.visitor_id).where(
            POSTransactionORM.store_id == store_id,
            POSTransactionORM.matched == True
        )
    )
    matched_visitor_map = {row.txn_id: row.visitor_id for row in matched_txns_q.fetchall()}
    
    # Load all POS transactions for this store from CSV
    txns = parse_pos_csv(POS_CSV_PATH, store_id)
    txn_map = {t.invoice_number: t for t in txns}

    # Load store configuration for brand mapping
    config = load_store_config(STORE_CONFIG_PATH, store_id)
    brand_map = config.zone_brand_map() if config else {}

    brand_buyers: dict[str, int] = {}
    for txn_id, visitor_id in matched_visitor_map.items():
        txn = txn_map.get(txn_id)
        if not txn:
            continue
        purchased_brands = {b.upper() for b in txn.brands}
        visited_zones = visitor_zones.get(visitor_id, set())
        for zone_id in visited_zones:
            brand_name = brand_map.get(zone_id)
            if brand_name and brand_name.upper() in purchased_brands:
                brand_buyers[zone_id] = brand_buyers.get(zone_id, 0) + 1

    brand_conversion = {}
    for zone_id in sorted(brand_visitors.keys()):
        if zone_id in brand_map:
            visitors = brand_visitors[zone_id]
            buyers = brand_buyers.get(zone_id, 0)
            brand_conversion[zone_id] = round((buyers / visitors * 100) if visitors > 0 else 0.0, 1)

    return MetricsResponse(
        store_id=store_id,
        footfall=footfall,
        unique_visitors=unique_visitors,
        conversion_rate=round(conversion_rate, 2),
        avg_dwell_per_zone=avg_dwell_per_zone,
        queue_depth=queue_depth,
        abandonment_rate=round(abandonment_rate, 2),
        brand_conversion=brand_conversion,
        total_revenue=total_revenue,
        computed_at=datetime.now(timezone.utc),
    )
