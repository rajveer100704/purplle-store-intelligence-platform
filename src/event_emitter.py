"""
event_emitter.py – Event generation engine.

Processes active track updates and lifecycle signals to emit challenge-compliant events:
ENTRY, EXIT, ZONE_ENTER, ZONE_EXIT, ZONE_DWELL, BILLING_QUEUE_JOIN, BILLING_QUEUE_ABANDON, REENTRY.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any
from shapely.geometry import Point, Polygon

from .state_machine import VisitorStateMachine, VisitorState
from .session_manager import SessionManager
from .tracker_lifecycle import TrackStateInfo


@dataclass
class Event:
    event_id: str
    store_id: str
    camera_id: str
    visitor_id: str
    event_type: str
    timestamp: str
    zone_id: str | None = None
    dwell_ms: int | None = None
    confidence: float = 1.0
    is_staff: bool = False
    session_seq: int = 1
    uncertain_reid: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "event_id": self.event_id,
            "store_id": self.store_id,
            "camera_id": self.camera_id,
            "visitor_id": self.visitor_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "is_staff": self.is_staff,
            "session_seq": self.session_seq,
        }
        if self.zone_id is not None:
            d["zone_id"] = self.zone_id
        if self.dwell_ms is not None:
            d["dwell_ms"] = self.dwell_ms
        if self.uncertain_reid:
            d["uncertain_reid"] = True
        if self.metadata:
            d["metadata"] = self.metadata
        return d


def _load_zones(layout: dict[str, Any], store_id: str) -> dict[str, Polygon]:
    """Parse zone polygons from store_layout for a given store."""
    zones: dict[str, Polygon] = {}
    stores = layout.get("stores", {})
    store_data = stores.get(store_id, stores.get(store_id.lower(), {}))
    for zone in store_data.get("zones", []):
        name = zone.get("zone_id") or zone.get("name", "UNKNOWN")
        coords = zone.get("polygon", zone.get("coordinates", []))
        if coords:
            zones[name] = Polygon(coords)
    return zones


def _load_entry_exit_lines(
    layout: dict[str, Any], store_id: str, camera_id: str
) -> tuple[list | None, list | None]:
    stores = layout.get("stores", {})
    store_data = stores.get(store_id, stores.get(store_id.lower(), {}))
    for cam in store_data.get("cameras", []):
        if str(cam.get("camera_id", "")).upper() == camera_id.upper():
            return cam.get("entry_line"), cam.get("exit_line")
    return None, None


def _side_of_line(line: list, point: tuple[float, float]) -> float:
    """Signed cross-product to determine which side of a line segment."""
    (x1, y1), (x2, y2) = line
    px, py = point
    return (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)


class EventEmitter:
    """
    Consumes track lifecycle signals and position updates to emit events.
    """

    BILLING_ZONE_KEYWORDS = {"billing", "checkout", "cashier", "register", "till"}

    def __init__(
        self,
        store_id: str,
        camera_id: str,
        store_layout: dict[str, Any],
        session_manager: SessionManager,
        reid_gallery: Any,
        fps: float = 30.0,
        video_start_time: Any = None,
        clip_duration: float = 0.0,
        total_video_frames: int = 0,
    ) -> None:
        from datetime import datetime, timezone

        from .layout.parser import StoreConfig
        from .config import STORE_CONFIG_PATH
        from .layout.parser import load_store_config

        self.store_id = store_id
        self.camera_id = camera_id
        self.session_manager = session_manager
        self.reid = reid_gallery
        self.fps = fps
        self.video_start_time = video_start_time or datetime.now(timezone.utc)
        self.clip_duration = clip_duration
        self.total_video_frames = total_video_frames

        # Support StoreConfig class or dictionary fallback
        self.store_config = None
        if isinstance(store_layout, StoreConfig):
            self.store_config = store_layout
        elif isinstance(store_layout, dict) and "stores" in store_layout:
            try:
                from .layout.parser import load_store_config
                from .config import STORE_CONFIG_PATH
                self.store_config = load_store_config(STORE_CONFIG_PATH, store_id)
            except Exception:
                pass

        if self.store_config is not None:
            cam_cfg = self.store_config.get_camera(camera_id)
            w, h = cam_cfg.frame_size if cam_cfg else (1920, 1080)
            self.zones = self.store_config.pixel_zones(w, h)
            self.entry_line = cam_cfg.pixel_entry_line() if cam_cfg else None
            self.exit_line = cam_cfg.pixel_exit_line() if cam_cfg else None
            self.brand_map = self.store_config.zone_brand_map()
            self.billing_zones = {self.store_config.billing_zone.zone_id} if self.store_config.billing_zone else set()
            self.queue_zones = {
                self.store_config.queue_zone.zone_id: self.zones[self.store_config.queue_zone.zone_id]
            } if (self.store_config.queue_zone and self.store_config.queue_zone.zone_id in self.zones) else {}
        else:
            self.zones = _load_zones(store_layout, store_id)
            self.entry_line, self.exit_line = _load_entry_exit_lines(
                store_layout, store_id, camera_id
            )
            self.billing_zones = {
                z for z in self.zones
                if any(k in z.lower() for k in self.BILLING_ZONE_KEYWORDS)
            }
            self.queue_zones = {
                z: poly for z, poly in self.zones.items()
                if "queue" in z.lower()
            }
            # Extract brand map from legacy dict
            self.brand_map = {}
            stores = store_layout.get("stores", {})
            store_data = stores.get(store_id, stores.get(store_id.lower(), {}))
            for z in store_data.get("zones", []):
                if "brand" in z and z["brand"]:
                    self.brand_map[z["zone_id"]] = z["brand"]
                elif "zone_id" in z:
                    # Fallback to mapping uppercase zone_id directly
                    self.brand_map[z["zone_id"]] = z["zone_id"]


        # Inferred queue zones
        self.inferred_queue_zones: dict[str, Polygon] = {}
        if not self.queue_zones:
            for bz in self.billing_zones:
                billing_poly = self.zones.get(bz)
                if billing_poly:
                    self.inferred_queue_zones[bz] = self._infer_queue_polygon(billing_poly)

        # FSM instances persistent by visitor_id
        self._visitor_fsms: dict[str, VisitorStateMachine] = {}
        # Track-specific state helper (e.g. queue state)
        self._track_queue_state: dict[int, bool] = {}  # track_id -> in_queue
        self._events: list[Event] = []

    def _frame_time(self, frame_idx: int) -> float:
        return self.video_start_time.timestamp() + (frame_idx / self.fps)

    def _iso(self, frame_idx: int) -> str:
        from datetime import datetime, timezone
        ts = self._frame_time(frame_idx)
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

    def _make_event(
        self,
        event_type: str,
        visitor_id: str,
        frame_idx: int,
        confidence: float = 1.0,
        zone_id: str | None = None,
        dwell_ms: int | None = None,
        is_staff: bool = False,
        session_seq: int = 1,
        uncertain_reid: bool = False,
        metadata: dict | None = None,
    ) -> Event:
        return Event(
            event_id=str(uuid.uuid4()),
            store_id=self.store_id,
            camera_id=self.camera_id,
            visitor_id=visitor_id,
            event_type=event_type,
            timestamp=self._iso(frame_idx),
            zone_id=zone_id,
            dwell_ms=dwell_ms,
            confidence=confidence,
            is_staff=is_staff,
            session_seq=session_seq,
            uncertain_reid=uncertain_reid,
            metadata=metadata or {},
        )

    def _zone_at(self, center: tuple[float, float]) -> str | None:
        pt = Point(center)
        for zone_id, poly in self.zones.items():
            if poly.contains(pt):
                return zone_id
        return None

    def _crossed_line(
        self,
        line: list | None,
        prev_side: float | None,
        center: tuple[float, float],
    ) -> tuple[bool, float]:
        if line is None:
            return False, 0.0
        side = _side_of_line(line, center)
        if prev_side is not None and prev_side * side < 0:
            return True, side
        return False, side

    def _is_inside_store(self, center: tuple[float, float]) -> bool:
        if not self.entry_line:
            return True
        (x1, y1), (x2, y2) = self.entry_line
        if abs(x2 - x1) < abs(y2 - y1):  # vertical-ish line
            # Store is to the right of the entry line
            return center[0] > max(x1, x2)
        else:  # horizontal-ish line
            # Store is below the entry line (y is larger)
            return center[1] > max(y1, y2)

    def _infer_queue_polygon(self, billing_poly: Polygon) -> Polygon:
        """Infer queue zone from centroid and entrance edge."""
        centroid = billing_poly.centroid
        cx, cy = centroid.x, centroid.y

        if self.entry_line:
            (x1, y1), (x2, y2) = self.entry_line
            ref_x, ref_y = (x1 + x2) / 2, (y1 + y2) / 2
        else:
            ref_x, ref_y = 0.0, 0.0

        dx = ref_x - cx
        dy = ref_y - cy

        minx, miny, maxx, maxy = billing_poly.bounds
        width = maxx - minx
        height = maxy - miny

        if abs(dx) > abs(dy):
            if dx < 0:
                split_x = minx + 0.25 * width
                slice_poly = Polygon([(minx, miny), (split_x, miny), (split_x, maxy), (minx, maxy)])
            else:
                split_x = maxx - 0.25 * width
                slice_poly = Polygon([(split_x, miny), (maxx, miny), (maxx, maxy), (split_x, maxy)])
        else:
            if dy < 0:
                split_y = miny + 0.25 * height
                slice_poly = Polygon([(minx, miny), (maxx, miny), (maxx, split_y), (minx, split_y)])
            else:
                split_y = maxy - 0.25 * height
                slice_poly = Polygon([(minx, split_y), (maxx, split_y), (maxx, maxy), (minx, maxy)])

        inferred = billing_poly.intersection(slice_poly)
        if inferred.is_empty:
            return billing_poly
        return inferred

    def _is_in_queue_zone(self, center: tuple[float, float], billing_zone: str) -> bool:
        pt = Point(center)
        for q_poly in self.queue_zones.values():
            if q_poly.contains(pt):
                return True
        inferred = self.inferred_queue_zones.get(billing_zone)
        if inferred and inferred.contains(pt):
            return True
        return False

    def process_frame(
        self,
        frame: Any,  # unused here, kept for back-compat
        valid_active_infos: list[TrackStateInfo],
        frame_idx: int,
        lifecycle_signals: list[tuple[TrackStateInfo, str]] | None = None,
    ) -> list[Event]:
        """
        Process tracks for one frame. Returns newly emitted events.
        """
        frame_events: list[Event] = []
        frame_time = self._frame_time(frame_idx)
        lifecycle_signals = lifecycle_signals or []

        # ── 1. Process active tracks ──────────────────────────────────────────
        for info in valid_active_infos:
            tid = info.track_id
            x1, y1, x2, y2 = info.xyxy
            center = ((x1 + x2) / 2, (y1 + y2) / 2)
            vid = info.visitor_id

            if not vid:
                continue

            if vid not in self._visitor_fsms:
                self._visitor_fsms[vid] = VisitorStateMachine(vid)

            sm = self._visitor_fsms[vid]

            # Increment presence frame count and track durations
            session = self.session_manager.get_active(vid)
            if session:
                session.frame_count += 1
                session.camera_durations[self.camera_id] = (
                    session.camera_durations.get(self.camera_id, 0.0) + (1.0 / self.fps)
                )

            # Check entry crossing
            crossed_entry, new_entry_side = self._crossed_line(
                self.entry_line, info.prev_entry_side, center
            )
            if info.prev_entry_side is None:
                if self._is_inside_store(center):
                    crossed_entry = True
                    if self.entry_line:
                        new_entry_side = _side_of_line(self.entry_line, center)
            info.prev_entry_side = new_entry_side

            if crossed_entry and sm.can_trigger("entry_line_crossed"):
                event_type = sm.trigger("entry_line_crossed")
                session = self.session_manager.open_session(
                    vid, self.camera_id, frame_time, info.uncertain_reid
                )
                evt = self._make_event(
                    event_type=event_type,
                    visitor_id=vid,
                    frame_idx=frame_idx,
                    confidence=info.confidence,
                    is_staff=session.is_staff,
                    session_seq=session.session_seq,
                    uncertain_reid=info.uncertain_reid,
                )
                frame_events.append(evt)

                if event_type == "REENTRY":
                    sm.trigger("normalise")

            # Check zone containment
            if sm.is_inside():
                zone_now = self._zone_at(center)
                prev_zone = info.current_zone

                if zone_now and zone_now != prev_zone:
                    session = self.session_manager.get_active(vid)

                    if zone_now in self.billing_zones:
                        if sm.can_trigger("billing_enter"):
                            sm.trigger("billing_enter")
                    else:
                        if sm.can_trigger("zone_enter"):
                            event_type = sm.trigger("zone_enter")
                            self.session_manager.enter_zone(vid, zone_now, frame_time)
                            if session and zone_now in self.brand_map:
                                if zone_now not in session.visited_brands:
                                    session.visited_brands.append(zone_now)
                            evt = self._make_event(
                                event_type=event_type,
                                visitor_id=vid,
                                frame_idx=frame_idx,
                                confidence=info.confidence,
                                zone_id=zone_now,
                                is_staff=session.is_staff if session else False,
                                session_seq=session.session_seq if session else 1,
                            )
                            frame_events.append(evt)

                    info.current_zone = zone_now

                elif prev_zone and not zone_now:
                    session = self.session_manager.get_active(vid)

                    if prev_zone in self.billing_zones:
                        if sm.can_trigger("billing_exit"):
                            sm.trigger("billing_exit")
                    else:
                        if sm.can_trigger("zone_exit"):
                            event_type = sm.trigger("zone_exit")
                            self.session_manager.exit_zone(vid, frame_time)
                            evt = self._make_event(
                                event_type=event_type,
                                visitor_id=vid,
                                frame_idx=frame_idx,
                                confidence=info.confidence,
                                zone_id=prev_zone,
                                is_staff=session.is_staff if session else False,
                                session_seq=session.session_seq if session else 1,
                            )
                            frame_events.append(evt)

                    info.current_zone = zone_now

                # Billing Queue check
                if sm.is_in_billing() and zone_now in self.billing_zones:
                    is_in_q = self._is_in_queue_zone(center, zone_now)
                    was_in_q = self._track_queue_state.get(tid, False)

                    if is_in_q and not was_in_q:
                        session = self.session_manager.get_active(vid)
                        queue_depth = self.session_manager.join_billing_queue(vid, frame_time)
                        if queue_depth > 0:
                            evt = self._make_event(
                                event_type="BILLING_QUEUE_JOIN",
                                visitor_id=vid,
                                frame_idx=frame_idx,
                                confidence=info.confidence,
                                zone_id=zone_now,
                                is_staff=session.is_staff if session else False,
                                session_seq=session.session_seq if session else 1,
                                metadata={"queue_depth": queue_depth},
                            )
                            frame_events.append(evt)
                        self._track_queue_state[tid] = True

                    elif not is_in_q and was_in_q:
                        session = self.session_manager.get_active(vid)
                        should_abandon = self.session_manager.leave_billing_queue(vid, frame_time)
                        if should_abandon:
                            evt = self._make_event(
                                event_type="BILLING_QUEUE_ABANDON",
                                visitor_id=vid,
                                frame_idx=frame_idx,
                                confidence=info.confidence,
                                zone_id=zone_now,
                                is_staff=session.is_staff if session else False,
                                session_seq=session.session_seq if session else 1,
                                metadata={"queue_depth": self.session_manager.current_queue_depth()},
                            )
                            frame_events.append(evt)
                        self._track_queue_state[tid] = False

                # Dwell check
                if zone_now and sm.can_trigger("zone_dwell"):
                    dwell_ms = self.session_manager.check_dwell(vid, zone_now, frame_time)
                    if dwell_ms is not None:
                        sm.trigger("zone_dwell")
                        session = self.session_manager.get_active(vid)
                        evt = self._make_event(
                            event_type="ZONE_DWELL",
                            visitor_id=vid,
                            frame_idx=frame_idx,
                            confidence=info.confidence,
                            zone_id=zone_now,
                            dwell_ms=dwell_ms,
                            is_staff=session.is_staff if session else False,
                            session_seq=session.session_seq if session else 1,
                        )
                        frame_events.append(evt)

            # Check exit line crossing
            crossed_exit, new_exit_side = self._crossed_line(
                self.exit_line, info.prev_exit_side, center
            )
            info.prev_exit_side = new_exit_side

            if crossed_exit and sm.can_trigger("exit_line_crossed"):
                event_type = sm.trigger("exit_line_crossed")
                session = self.session_manager.close_session(
                    vid, frame_time, self.total_video_frames, self.clip_duration
                )
                evt = self._make_event(
                    event_type=event_type,
                    visitor_id=vid,
                    frame_idx=frame_idx,
                    confidence=info.confidence,
                    is_staff=session.is_staff if session else False,
                    session_seq=session.session_seq if session else 1,
                )
                frame_events.append(evt)

        # ── 2. Process lifecycle signals ──────────────────────────────────────
        for info, signal in lifecycle_signals:
            vid = info.visitor_id
            tid = info.track_id
            if not vid:
                continue

            sm = self._visitor_fsms.get(vid)
            if sm and sm.is_inside():
                # Clean up queue state
                if self._track_queue_state.get(tid, False):
                    self.session_manager.leave_billing_queue(vid, frame_time)
                    self._track_queue_state[tid] = False

                if signal == "EXIT":
                    if sm.can_trigger("exit_line_crossed"):
                        event_type = sm.trigger("exit_line_crossed")
                        session = self.session_manager.close_session(
                            vid, frame_time, self.total_video_frames, self.clip_duration
                        )
                        evt = self._make_event(
                            event_type=event_type,
                            visitor_id=vid,
                            frame_idx=frame_idx,
                            confidence=0.5,
                            is_staff=session.is_staff if session else False,
                            session_seq=session.session_seq if session else 1,
                        )
                        frame_events.append(evt)

                elif signal == "EXPIRED_SILENT":
                    self.session_manager.close_session(
                        vid, frame_time, self.total_video_frames, self.clip_duration
                    )

        self._events.extend(frame_events)
        return frame_events

    def all_events(self) -> list[Event]:
        return list(self._events)

    def flush(self) -> list[dict[str, Any]]:
        result = [e.to_dict() for e in self._events]
        self._events.clear()
        return result
