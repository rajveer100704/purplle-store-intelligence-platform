"""
api/funnel.py – GET /stores/{store_id}/funnel endpoint.

Computes the customer journey funnel:
  entry → zone_visit → billing → purchase

Dropoff at each stage is also returned.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.models import EventORM
from .schemas import FunnelDropoff, FunnelResponse

router = APIRouter()


@router.get(
    "/stores/{store_id}/funnel",
    response_model=FunnelResponse,
    summary="Get customer journey funnel",
)
async def get_funnel(
    store_id: str,
    db: AsyncSession = Depends(get_db),
) -> FunnelResponse:

    base = and_(
        EventORM.store_id == store_id,
        EventORM.is_staff == False,  # noqa: E712
    )

    async def count_distinct_visitors(event_type: str) -> int:
        q = await db.execute(
            select(func.count(func.distinct(EventORM.visitor_id))).where(
                base, EventORM.event_type == event_type
            )
        )
        return q.scalar() or 0

    # ── Funnel stages ──────────────────────────────────────────────────────
    entry = await count_distinct_visitors("ENTRY")

    # Zone visit: any visitor with at least one ZONE_ENTER event
    zone_q = await db.execute(
        select(func.count(func.distinct(EventORM.visitor_id))).where(
            base, EventORM.event_type == "ZONE_ENTER"
        )
    )
    zone_visit = zone_q.scalar() or 0

    # Billing: any visitor with BILLING_QUEUE_JOIN
    billing = await count_distinct_visitors("BILLING_QUEUE_JOIN")

    # Purchase: matched POS transactions if any exist in DB, else fallback to BILLING_QUEUE_JOIN without BILLING_QUEUE_ABANDON
    from ..db.models import POSTransactionORM
    pos_count_q = await db.execute(
        select(func.count()).where(
            POSTransactionORM.store_id == store_id,
            POSTransactionORM.matched == True
        )
    )
    has_pos = (pos_count_q.scalar() or 0) > 0

    if has_pos:
        purchase_q = await db.execute(
            select(func.count(func.distinct(POSTransactionORM.visitor_id))).where(
                POSTransactionORM.store_id == store_id,
                POSTransactionORM.matched == True
            )
        )
        purchase = purchase_q.scalar() or 0
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
        purchase_q = await db.execute(
            select(func.count(func.distinct(EventORM.visitor_id))).where(
                EventORM.visitor_id.in_(select(join_subq)),
                EventORM.visitor_id.not_in(select(abandon_subq)),
                EventORM.store_id == store_id,
                EventORM.is_staff == False,  # noqa: E712
            )
        )
        purchase = purchase_q.scalar() or 0


    # ── Dropoff ────────────────────────────────────────────────────────────
    dropoff = FunnelDropoff(
        entry_to_zone=max(0, entry - zone_visit),
        zone_to_billing=max(0, zone_visit - billing),
        billing_to_purchase=max(0, billing - purchase),
    )

    return FunnelResponse(
        store_id=store_id,
        entry=entry,
        zone_visit=zone_visit,
        billing=billing,
        purchase=purchase,
        dropoff=dropoff,
        computed_at=datetime.now(timezone.utc),
    )
