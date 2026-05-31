"""
tracker_lifecycle.py – Track Lifecycle Manager.

Manages camera-local track lifecycle (ACTIVE, LOST, RECOVERED, EXPIRED)
and determines boundary-based exit vs. occlusion quiet expiration.
"""

from __future__ import annotations

import math
from enum import Enum, auto
from typing import Any
import numpy as np

from .tracker import Track
from .config import TRACK_LOST_TIMEOUT, OCCLUSION_TIMEOUT


class TrackLifecycleState(Enum):
    ACTIVE = auto()
    LOST = auto()
    RECOVERED = auto()
    EXPIRED = auto()


class TrackStateInfo:
    def __init__(
        self,
        track_id: int,
        xyxy: np.ndarray,
        confidence: float,
        first_seen_time: float,
        last_seen_time: float,
    ) -> None:
        self.track_id = track_id
        self.xyxy = xyxy
        self.confidence = confidence
        self.first_seen_time = first_seen_time
        self.last_seen_time = last_seen_time
        self.state = TrackLifecycleState.ACTIVE
        self.lost_since_time: float | None = None
        self.prev_center: tuple[float, float] | None = None
        self.prev_entry_side: float | None = None
        self.prev_exit_side: float | None = None
        self.visitor_id: str | None = None
        self.uncertain_reid: bool = False
        self.current_zone: str | None = None


def _point_to_line_distance(pt: tuple[float, float], line: list) -> float:
    """Distance from point pt to line segment line [[x1, y1], [x2, y2]]."""
    if not line or len(line) < 2:
        return float("inf")
    (x1, y1), (x2, y2) = line
    px, py = pt
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    
    # Projection factor
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


class TrackLifecycleManager:
    """
    Manages track lifecycles on a per-camera basis.
    Determines valid tracks, lost tracks, recovery, and boundary-based exits.
    """

    def __init__(
        self,
        exit_line: list | None = None,
        boundary_threshold: float = 0.10,
        lost_timeout: float = TRACK_LOST_TIMEOUT,
        occlusion_timeout: float = OCCLUSION_TIMEOUT,
        min_track_age: int = 1,
    ) -> None:
        self.exit_line = exit_line
        self.boundary_threshold = boundary_threshold
        self.lost_timeout = lost_timeout
        self.occlusion_timeout = occlusion_timeout
        self.min_track_age = min_track_age
        self.tracks_db: dict[int, TrackStateInfo] = {}

    def update(
        self,
        active_tracks: list[Track],
        frame_time: float,
        frame_width: int,
        frame_height: int,
    ) -> tuple[list[TrackStateInfo], list[tuple[TrackStateInfo, str]]]:
        """
        Update the manager with the current frame's tracks.

        Returns
        -------
        valid_active : list[TrackStateInfo]
            Tracks currently visible and confirmed valid.
        lifecycle_signals : list[tuple[TrackStateInfo, str]]
            Signals of state changes: e.g. (track_info, 'EXIT') or (track_info, 'RECOVERED')
        """
        current_ids = set()
        signals: list[tuple[TrackStateInfo, str]] = []
        valid_active: list[TrackStateInfo] = []

        # ── 1. Update/Add visible tracks ──────────────────────────────────────
        for track in active_tracks:
            tid = track.track_id
            current_ids.add(tid)
            
            # Filter noise / unconfirmed tracks
            if track.age < self.min_track_age:
                continue

            if tid not in self.tracks_db:
                # New track
                info = TrackStateInfo(
                    track_id=tid,
                    xyxy=track.xyxy,
                    confidence=track.confidence,
                    first_seen_time=frame_time,
                    last_seen_time=frame_time,
                )
                self.tracks_db[tid] = info
                valid_active.append(info)
            else:
                info = self.tracks_db[tid]
                info.xyxy = track.xyxy
                info.confidence = track.confidence
                info.last_seen_time = frame_time

                if info.state == TrackLifecycleState.LOST:
                    info.state = TrackLifecycleState.ACTIVE
                    info.lost_since_time = None
                    signals.append((info, "RECOVERED"))

                valid_active.append(info)

        # ── 2. Identify and progress lost tracks ────────────────────────────────
        all_tids = list(self.tracks_db.keys())
        for tid in all_tids:
            info = self.tracks_db[tid]
            if info.state == TrackLifecycleState.EXPIRED:
                continue

            if tid not in current_ids:
                # Track is missing in this frame
                if info.state != TrackLifecycleState.LOST:
                    info.state = TrackLifecycleState.LOST
                    info.lost_since_time = frame_time

                # Check for expiration timeouts
                lost_duration = frame_time - info.lost_since_time
                if lost_duration >= self.lost_timeout:
                    # Determine if near exit boundary
                    is_near = self._is_near_exit_boundary(
                        info.xyxy, frame_width, frame_height
                    )
                    
                    if is_near:
                        info.state = TrackLifecycleState.EXPIRED
                        signals.append((info, "EXIT"))
                    elif lost_duration >= self.occlusion_timeout:
                        info.state = TrackLifecycleState.EXPIRED
                        signals.append((info, "EXPIRED_SILENT"))

        # Clean up expired tracks
        self.tracks_db = {
            tid: info for tid, info in self.tracks_db.items()
            if info.state != TrackLifecycleState.EXPIRED
        }

        return valid_active, signals

    def _is_near_exit_boundary(
        self, xyxy: np.ndarray, w: int, h: int
    ) -> bool:
        """True if the bounding box is near the image edge or the exit line."""
        x1, y1, x2, y2 = xyxy
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2

        # Check image margins (10%)
        mx = w * self.boundary_threshold
        my = h * self.boundary_threshold
        if (x1 < mx) or (x2 > w - mx) or (y1 < my) or (y2 > h - my):
            return True

        # Check exit line proximity (within 50px)
        if self.exit_line:
            dist = _point_to_line_distance((cx, cy), self.exit_line)
            if dist <= 50.0:
                return True

        return False
