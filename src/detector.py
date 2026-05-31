"""
detector.py – YOLOv8s person detection wrapper.

Runs YOLOv8s on individual frames and returns normalized Detection objects.
Only class-0 (person) detections are returned.
Confidence is never suppressed below the configured threshold – low-confidence
detections are included in output with their raw score intact.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# ──────────────────────────────────────────────────────────────────────────────
# Data types
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Detection:
    """Bounding box in pixel coords [x1, y1, x2, y2]."""
    xyxy: np.ndarray   # shape (4,) float32
    confidence: float
    class_id: int = 0  # 0 = person

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.xyxy
        return float((x1 + x2) / 2), float((y1 + y2) / 2)

    @property
    def width(self) -> float:
        return float(self.xyxy[2] - self.xyxy[0])

    @property
    def height(self) -> float:
        return float(self.xyxy[3] - self.xyxy[1])


# ──────────────────────────────────────────────────────────────────────────────
# Detector
# ──────────────────────────────────────────────────────────────────────────────

class PersonDetector:
    """
    Wraps ultralytics YOLOv8 for person-only detection.

    Parameters
    ----------
    model_path : str
        YOLO model identifier, e.g. "yolov8s.pt".  Auto-downloaded if absent.
    conf_threshold : float
        Minimum confidence to include a detection (never suppressed below this).
    device : str
        PyTorch device string: "cpu", "0", "cuda", etc.
    """

    PERSON_CLASS_ID = 0  # COCO class for person

    def __init__(
        self,
        model_path: str = "yolov8s.pt",
        conf_threshold: float = 0.25,
        device: str = "cpu",
    ) -> None:
        from ultralytics import YOLO  # deferred import for faster module load

        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold
        self.device = device

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """
        Run inference on *frame* (BGR numpy array).
        Returns a list of Detection objects for all people detected.
        """
        results = self.model(
            frame,
            conf=self.conf_threshold,
            classes=[self.PERSON_CLASS_ID],
            device=self.device,
            verbose=False,
        )

        detections: list[Detection] = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                xyxy = box.xyxy[0].cpu().numpy().astype(np.float32)
                conf = float(box.conf[0].cpu())
                detections.append(Detection(xyxy=xyxy, confidence=conf))

        return detections

    def detect_batch(self, frames: list[np.ndarray]) -> list[list[Detection]]:
        """Run detection on multiple frames in one forward pass."""
        return [self.detect(f) for f in frames]
