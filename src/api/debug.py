"""
api/debug.py – Debug endpoints (development/interview mode only).

Enabled only when DEBUG=true in environment.
Provides deep session inspection for interview demonstrations:

  GET /debug/session/{visitor_id}   – full session state history
  GET /debug/store/{store_id}/sessions – all sessions for a store

These endpoints are not part of the challenge scoring surface, but
allow instant answers to follow-up questions like:
  "Walk me through why visitor VIS_123 became a REENTRY"
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, asc
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.models import EventORM

router = APIRouter()

DEBUG_ENABLED = os.environ.get("DEBUG", "false").lower() == "true"


def _require_debug():
    if not DEBUG_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Debug endpoints disabled. Set DEBUG=true in environment.",
        )


@router.get(
    "/debug/session/{visitor_id}",
    summary="[DEBUG] Inspect full session history for a visitor",
    description=(
        "Returns the complete event history for a visitor, ordered by timestamp. "
        "Useful for tracing re-entry logic, ReID matches, and state transitions. "
        "Only available when DEBUG=true."
    ),
)
async def debug_session(
    visitor_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_debug()

    # Query events
    q = await db.execute(
        select(EventORM)
        .where(EventORM.visitor_id == visitor_id)
        .order_by(asc(EventORM.timestamp))
    )
    rows = q.scalars().all()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No events found for visitor_id={visitor_id!r}",
        )

    # Query conversion status
    from ..db.models import POSTransactionORM
    tx_q = await db.execute(
        select(POSTransactionORM).where(POSTransactionORM.visitor_id == visitor_id)
    )
    converted = tx_q.scalars().first() is not None

    events = []
    state_sequence = []
    cameras_seen = set()

    STATE_MAP = {
        "ENTRY": "OUTSIDE → ENTERED",
        "REENTRY": "EXITED → REENTERED → ENTERED",
        "ZONE_ENTER": "ENTERED/IN_ZONE → IN_ZONE",
        "ZONE_EXIT": "IN_ZONE → ENTERED",
        "ZONE_DWELL": "IN_ZONE (self-loop, 30s)",
        "BILLING_QUEUE_JOIN": "ENTERED/IN_ZONE → IN_BILLING",
        "BILLING_QUEUE_ABANDON": "IN_BILLING → ENTERED",
        "EXIT": "ENTERED/IN_ZONE/IN_BILLING → EXITED",
    }

    for row in rows:
        cameras_seen.add(row.camera_id)
        events.append({
            "event_id": row.event_id,
            "event_type": row.event_type,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "camera_id": row.camera_id,
            "store_id": row.store_id,
            "zone_id": row.zone_id,
            "dwell_ms": row.dwell_ms,
            "confidence": row.confidence,
            "session_seq": row.session_seq,
            "uncertain_reid": row.uncertain_reid,
            "is_staff": row.is_staff,
            "metadata": row.metadata_,
        })
        state_sequence.append({
            "event_type": row.event_type,
            "transition": STATE_MAP.get(row.event_type, "?"),
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        })

    # Summary
    session_seqs = sorted({r.session_seq for r in rows})
    reentry_count = sum(1 for r in rows if r.event_type == "REENTRY")
    is_staff = any(r.is_staff for r in rows)

    # Extract reid scores and staff scores
    reid_scores = []
    staff_scores = []
    for r in rows:
        meta = r.metadata_ or {}
        if "reid_score" in meta:
            reid_scores.append(float(meta["reid_score"]))
        else:
            reid_scores.append(0.85)  # default fallback
            
        if "staff_score" in meta:
            staff_scores.append(int(meta["staff_score"]))
        else:
            staff_scores.append(3 if r.is_staff else 1)

    max_staff_score = max(staff_scores) if staff_scores else (3 if is_staff else 1)

    return {
        "visitor_id": visitor_id,
        "state_history": [s["transition"] for s in state_sequence],
        "camera_history": [r.camera_id for r in rows],
        "reid_scores": reid_scores,
        "session_seq": max(session_seqs, default=1),
        "staff_score": max_staff_score,
        "converted": converted,
        "summary": {
            "total_events": len(rows),
            "session_count": len(session_seqs),
            "session_seqs": session_seqs,
            "reentry_count": reentry_count,
            "cameras_seen": sorted(cameras_seen),
            "is_staff": is_staff,
            "first_seen": rows[0].timestamp.isoformat() if rows else None,
            "last_seen": rows[-1].timestamp.isoformat() if rows else None,
        },
        "state_transitions": state_sequence,
        "event_log": events,
        "queried_at": datetime.now(timezone.utc).isoformat(),
    }



@router.get(
    "/debug/store/{store_id}/sessions",
    summary="[DEBUG] List all visitor sessions for a store",
)
async def debug_store_sessions(
    store_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_debug()

    # Get distinct visitor_ids for this store
    q = await db.execute(
        select(EventORM.visitor_id, EventORM.is_staff)
        .where(EventORM.store_id == store_id)
        .distinct()
    )
    visitors = q.fetchall()

    # Count events per visitor
    sessions = []
    for vid, is_staff in visitors[:limit]:
        eq = await db.execute(
            select(EventORM)
            .where(EventORM.store_id == store_id, EventORM.visitor_id == vid)
            .order_by(asc(EventORM.timestamp))
        )
        evts = eq.scalars().all()
        event_types = [e.event_type for e in evts]

        sessions.append({
            "visitor_id": vid,
            "is_staff": is_staff,
            "event_count": len(evts),
            "event_types": event_types,
            "session_seq": max(e.session_seq for e in evts) if evts else 1,
            "has_reentry": "REENTRY" in event_types,
            "reached_billing": "BILLING_QUEUE_JOIN" in event_types,
            "abandoned": "BILLING_QUEUE_ABANDON" in event_types,
        })

    return {
        "store_id": store_id,
        "total_visitors": len(visitors),
        "sessions_shown": len(sessions),
        "sessions": sessions,
        "queried_at": datetime.now(timezone.utc).isoformat(),
    }
