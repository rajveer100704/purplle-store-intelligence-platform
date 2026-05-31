"""
session_manager.py – Visitor session lifecycle engine.

Manages the full lifecycle of every visitor:
  • Session creation on ENTRY
  • Zone tracking
  • Billing state and queue management
  • Re-entry merging (same visitor_id, incremented session_seq)
  • Staff scoring and classification
  • POS correlation window

The SessionManager is the single authoritative source of truth for
what visitor is currently active, what state they're in, and whether
they've made a purchase.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
from .config import (
    STORE_OPEN_HOUR,
    STAFF_SCORE_THRESHOLD,
    STAFF_HUE_RANGE,
    STAFF_PRESENCE_RATIO_SINGLE,
    STAFF_PRESENCE_RATIO_MULTI,
)
POS_WINDOW_SECONDS = 300  # 5 minutes


# ──────────────────────────────────────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class VisitorSession:
    visitor_id: str
    store_id: str
    camera_id: str
    session_seq: int = 1

    # Timing
    entry_time: float = field(default_factory=time.time)  # unix epoch
    exit_time: float | None = None

    # Zone tracking
    current_zone: str | None = None
    zone_enter_time: float | None = None
    zones_visited: set[str] = field(default_factory=set)
    zone_dwell_timers: dict[str, float] = field(default_factory=dict)  # zone → last_dwell_emit
    visited_brands: list[str] = field(default_factory=list)           # ordered visited brand zone_ids
    brands_purchased: list[str] = field(default_factory=list)         # purchased brand names


    # Billing
    billing_entry_time: float | None = None
    billing_queue_depth_at_join: int = 0
    converted: bool = False
    purchase_amount: float | None = None
    camera_durations: dict[str, float] = field(default_factory=dict) # camera_id -> total seconds seen

    @property
    def purchased(self) -> bool:
        return self.converted

    @purchased.setter
    def purchased(self, val: bool) -> None:
        self.converted = val

    billing_abandoned: bool = False

    # Staff
    is_staff: bool = False
    staff_score: int = 0

    # Re-entry
    reentry_count: int = 0
    first_entry_time: float = field(default_factory=time.time)

    # Misc
    uncertain_reid: bool = False
    frame_count: int = 0            # number of frames this visitor was detected
    dominant_hue: float | None = None   # for uniform-color staff detection

    def total_dwell_ms(self) -> int:
        end = self.exit_time or time.time()
        return int((end - self.first_entry_time) * 1000)

    def is_active(self) -> bool:
        return self.exit_time is None


# ──────────────────────────────────────────────────────────────────────────────
# Session Manager
# ──────────────────────────────────────────────────────────────────────────────

class SessionManager:
    """
    Manages all active and completed visitor sessions for a single store.

    Usage
    -----
    mgr = SessionManager(store_id="S1")
    session = mgr.open_session(visitor_id, camera_id, frame_time)
    mgr.close_session(visitor_id, frame_time)
    """

    # Staff uniform HSV hue range (configurable)
    STAFF_HUE_RANGE = (100, 140)   # blue-ish uniform (example)
    STAFF_LONG_DWELL_HOURS = 4.0

    def __init__(self, store_id: str) -> None:
        self.store_id = store_id
        self._active: dict[str, VisitorSession] = {}       # visitor_id → session
        self._history: list[VisitorSession] = []           # closed sessions
        self._queue: list[str] = []                        # ordered billing queue (visitor_ids)
        self._pos_events: list[dict[str, Any]] = []        # ingested POS rows

    # ── Session lifecycle ────────────────────────────────────────────────────

    def open_session(
        self,
        visitor_id: str,
        camera_id: str,
        frame_time: float,
        uncertain_reid: bool = False,
    ) -> VisitorSession:
        """
        Open a new session or increment session_seq for a re-entry.
        """
        if visitor_id in self._active:
            # Already active – shouldn't happen; return existing
            return self._active[visitor_id]

        # Check if this visitor has a history (re-entry)
        prior = [s for s in self._history if s.visitor_id == visitor_id]
        seq = (max(s.session_seq for s in prior) + 1) if prior else 1
        reentry_count = len(prior)
        first_entry = prior[0].first_entry_time if prior else frame_time

        session = VisitorSession(
            visitor_id=visitor_id,
            store_id=self.store_id,
            camera_id=camera_id,
            session_seq=seq,
            entry_time=frame_time,
            first_entry_time=first_entry,
            reentry_count=reentry_count,
            uncertain_reid=uncertain_reid,
        )
        self._active[visitor_id] = session
        return session

    def close_session(
        self,
        visitor_id: str,
        frame_time: float,
        total_video_frames: int = 0,
        clip_duration: float = 0.0,
    ) -> VisitorSession | None:
        session = self._active.pop(visitor_id, None)
        if session is None:
            return None
        session.exit_time = frame_time
        self._score_staff(session, total_video_frames, clip_duration)
        self._history.append(session)
        return session


    def get_active(self, visitor_id: str) -> VisitorSession | None:
        return self._active.get(visitor_id)

    # ── Zone management ──────────────────────────────────────────────────────

    def enter_zone(self, visitor_id: str, zone_id: str, frame_time: float) -> None:
        session = self._active.get(visitor_id)
        if not session:
            return
        session.current_zone = zone_id
        session.zone_enter_time = frame_time
        session.zones_visited.add(zone_id)
        session.zone_dwell_timers[zone_id] = frame_time  # reset dwell timer

    def exit_zone(self, visitor_id: str, frame_time: float) -> None:
        session = self._active.get(visitor_id)
        if not session:
            return
        session.current_zone = None
        session.zone_enter_time = None

    def check_dwell(self, visitor_id: str, zone_id: str, frame_time: float) -> int | None:
        """
        Returns dwell_ms if a 30s ZONE_DWELL event should be emitted, else None.
        Also updates the dwell timer for next emission.
        """
        session = self._active.get(visitor_id)
        if not session:
            return None

        last = session.zone_dwell_timers.get(zone_id, frame_time)
        elapsed = frame_time - last
        if elapsed >= 30.0:
            dwell_ms = int(elapsed * 1000)
            session.zone_dwell_timers[zone_id] = frame_time
            return dwell_ms
        return None

    # ── Billing queue ────────────────────────────────────────────────────────

    def join_billing_queue(self, visitor_id: str, frame_time: float) -> int:
        """Returns current queue depth when the visitor joins."""
        session = self._active.get(visitor_id)
        if session:
            session.billing_entry_time = frame_time
            depth = len(self._queue)
            session.billing_queue_depth_at_join = depth
            self._queue.append(visitor_id)
        return len(self._queue) - 1   # depth BEFORE this person joined

    def leave_billing_queue(self, visitor_id: str, frame_time: float) -> bool:
        """
        Returns True if this is a BILLING_QUEUE_ABANDON (no POS match).
        Returns False if POS was already matched (purchased).
        """
        session = self._active.get(visitor_id)
        purchased = session.purchased if session else False

        if visitor_id in self._queue:
            self._queue.remove(visitor_id)

        if session and not purchased:
            session.billing_abandoned = True
            return True  # emit ABANDON
        return False

    def mark_purchased(self, visitor_id: str, amount: float | None = None) -> None:
        session = self._active.get(visitor_id) or next(
            (s for s in self._history if s.visitor_id == visitor_id), None
        )
        if session:
            session.converted = True
            if amount is not None:
                session.purchase_amount = amount

    def current_queue_depth(self) -> int:
        return len(self._queue)

    # ── POS correlation ──────────────────────────────────────────────────────

    def ingest_pos(self, pos_rows: list[dict[str, Any]]) -> None:
        self._pos_events.extend(pos_rows)

    def find_pos_match(self, visitor_id: str, exit_time: float) -> dict | None:
        """
        Find a POS transaction for this store within POS_WINDOW_SECONDS of exit_time.
        Marks the transaction as consumed to avoid double-matching.
        """
        window_start = exit_time - POS_WINDOW_SECONDS
        window_end = exit_time + POS_WINDOW_SECONDS

        for pos in self._pos_events:
            if pos.get("_matched"):
                continue
            ts = pos.get("_ts_epoch", 0.0)
            if window_start <= ts <= window_end:
                pos["_matched"] = True
                pos["_visitor_id"] = visitor_id
                return pos
        return None

    def _score_staff(
        self,
        session: VisitorSession,
        total_video_frames: int = 0,
        clip_duration: float = 0.0,
    ) -> None:
        score = 0

        # Rule 1: Uniform color match
        if session.dominant_hue is not None:
            lo, hi = STAFF_HUE_RANGE
            if lo <= session.dominant_hue <= hi:
                score += 1

        # Rule 2: Present before store opening
        entry_hour = datetime.fromtimestamp(
            session.first_entry_time, tz=timezone.utc
        ).hour
        if entry_hour < STORE_OPEN_HOUR:
            score += 2

        # Rule 3: Time spread across cameras (using ratios if duration is known)
        if clip_duration > 0.0:
            high_ratio_cams = sum(
                1 for dur in session.camera_durations.values()
                if (dur / clip_duration) > STAFF_PRESENCE_RATIO_MULTI
            )
            max_single_ratio = max(
                (dur / clip_duration) for dur in session.camera_durations.values()
            ) if session.camera_durations else 0.0

            if max_single_ratio > STAFF_PRESENCE_RATIO_SINGLE:
                score += 2
            if high_ratio_cams >= 2:
                score += 2
        else:
            # Fallback to absolute seconds if clip_duration is unknown
            high_dur_cams = sum(1 for dur in session.camera_durations.values() if dur > 120.0)
            max_single_dur = max(session.camera_durations.values()) if session.camera_durations else 0.0

            if max_single_dur > 300.0:
                score += 2
            if high_dur_cams >= 2:
                score += 2

        # Rule 4: High frame density (appears in >30% of total video frames)
        if total_video_frames > 0:
            presence_ratio = session.frame_count / total_video_frames
            if presence_ratio > 0.30:
                score += 2
        else:
            # Fallback if total_video_frames is not provided
            if session.frame_count > 5000:
                score += 2

        session.staff_score = score
        session.is_staff = score >= STAFF_SCORE_THRESHOLD


    # ── Aggregation helpers ──────────────────────────────────────────────────

    def all_sessions(self) -> list[VisitorSession]:
        return list(self._active.values()) + self._history

    def customer_sessions(self) -> list[VisitorSession]:
        return [s for s in self.all_sessions() if not s.is_staff]

    def unique_customer_count(self) -> int:
        ids = {s.visitor_id for s in self.customer_sessions()}
        return len(ids)

    def conversion_rate(self) -> float:
        customers = self.customer_sessions()
        if not customers:
            return 0.0
        purchased = sum(1 for s in customers if s.purchased)
        return (purchased / len(customers)) * 100.0

    def abandonment_rate(self) -> float:
        billing_visitors = [
            s for s in self.customer_sessions()
            if s.billing_entry_time is not None
        ]
        if not billing_visitors:
            return 0.0
        abandoned = sum(1 for s in billing_visitors if s.billing_abandoned)
        return (abandoned / len(billing_visitors)) * 100.0
