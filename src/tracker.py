"""
tracker.py – ByteTrack multi-object tracker wrapper.

ByteTrack is more robust than DeepSORT for:
  • Occlusion (uses IoU + Kalman)
  • Fast-moving targets
  • Crowded scenes (multiple simultaneous entries)

Uses the `supervision` library's ByteTrack implementation which requires
no external weight files.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import supervision as sv

from .detector import Detection


# ──────────────────────────────────────────────────────────────────────────────
# Data types
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Track:
    """A tracked bounding box with a persistent camera-local track ID."""
    track_id: int
    xyxy: np.ndarray        # shape (4,) float32
    confidence: float
    age: int                # frames since first detection
    is_confirmed: bool      # True after tracker has confirmed the track

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.xyxy
        return float((x1 + x2) / 2), float((y1 + y2) / 2)

    def crop(self, frame: np.ndarray) -> np.ndarray:
        """Return the bounding-box crop from *frame* (BGR)."""
        x1, y1, x2, y2 = map(int, self.xyxy)
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        return frame[y1:y2, x1:x2]


# ──────────────────────────────────────────────────────────────────────────────
# Tracker
# ──────────────────────────────────────────────────────────────────────────────

class ByteTracker:
    """
    Wraps supervision.ByteTrack for per-camera multi-object tracking.

    One instance per camera stream.  track_id values are camera-local;
    global visitor_id deduplication is handled by OSNetReID (reid.py).
    """

    def __init__(
        self,
        frame_rate: float = 30.0,
        track_activation_threshold: float = 0.25,
        lost_track_buffer: int = 30,
        minimum_matching_threshold: float = 0.8,
        minimum_consecutive_frames: int = 1,
    ) -> None:
        self._tracker = sv.ByteTrack(
            track_activation_threshold=track_activation_threshold,
            lost_track_buffer=lost_track_buffer,
            minimum_matching_threshold=minimum_matching_threshold,
            minimum_consecutive_frames=minimum_consecutive_frames,
            frame_rate=frame_rate,
        )
        self._frame_count = 0

    def update(
        self,
        detections: list[Detection],
        frame: np.ndarray | None = None,
    ) -> list[Track]:
        """
        Feed detections for the current frame and return confirmed tracks.

        Parameters
        ----------
        detections : list[Detection]
            Detections from the current frame.
        frame : np.ndarray, optional
            Current BGR frame (unused by ByteTrack itself, kept for API symmetry
            with ReID which needs the frame).
        """
        self._frame_count += 1

        if not detections:
            # Still update tracker with empty to age out lost tracks
            sv_dets = sv.Detections.empty()
        else:
            xyxy = np.stack([d.xyxy for d in detections])
            confs = np.array([d.confidence for d in detections], dtype=np.float32)
            class_ids = np.zeros(len(detections), dtype=int)
            sv_dets = sv.Detections(
                xyxy=xyxy,
                confidence=confs,
                class_id=class_ids,
            )

        tracked = self._tracker.update_with_detections(sv_dets)

        results: list[Track] = []
        if len(tracked) == 0:
            return results

        for i in range(len(tracked)):
            tid = int(tracked.tracker_id[i]) if tracked.tracker_id is not None else -1
            box = tracked.xyxy[i].astype(np.float32)
            conf = float(tracked.confidence[i]) if tracked.confidence is not None else 0.0
            results.append(
                Track(
                    track_id=tid,
                    xyxy=box,
                    confidence=conf,
                    age=self._frame_count,
                    is_confirmed=True,
                )
            )

        return results

    def reset(self) -> None:
        """Reset tracker state (call between videos)."""
        self._tracker.reset()
        self._frame_count = 0
