"""
reid.py – OSNet ReID appearance embedding gallery.

Converts camera-local ByteTrack track_ids into globally unique visitor_ids
by matching appearance embeddings across cameras and re-entries.

Model: osnet_x0_25 from torchreid (lightweight, 512-dim embedding).
Match thresholds:
  ≥ MATCH_THRESHOLD  → same person, merge visitor_id
  ≤ NEW_ID_THRESHOLD → new person, assign new visitor_id
  in between         → uncertain, assign new visitor_id + flag uncertain_reid=True
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field

import cv2
import numpy as np

# ──────────────────────────────────────────────────────────────────────────────
from .config import REID_MATCH_THRESHOLD as MATCH_THRESHOLD, REID_NEW_ID_THRESHOLD as NEW_ID_THRESHOLD, REID_MODEL_NAME


# ──────────────────────────────────────────────────────────────────────────────
# Gallery entry
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class GalleryEntry:
    visitor_id: str
    embedding: np.ndarray    # shape (512,) float32, L2-normalised
    last_seen_frame: int
    uncertain: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# ReID engine
# ──────────────────────────────────────────────────────────────────────────────

class OSNetReID:
    """
    Maintains a gallery of visitor appearance embeddings.

    One instance is shared across all cameras for a given store to enable
    cross-camera identity matching.
    """

    def __init__(
        self,
        match_threshold: float = MATCH_THRESHOLD,
        new_id_threshold: float = NEW_ID_THRESHOLD,
        model_name: str = REID_MODEL_NAME,
        device: str = "cpu",
    ) -> None:
        self.match_threshold = match_threshold
        self.new_id_threshold = new_id_threshold
        self._gallery: dict[str, GalleryEntry] = {}  # visitor_id → entry
        self._model = None
        self._device = device
        self._model_name = model_name

    def _load_model(self) -> None:
        """Lazy-load OSNet to avoid slow startup when ReID is not used."""
        if self._model is not None:
            return
        try:
            import torchreid
            self._model = torchreid.models.build_model(
                name=self._model_name,
                num_classes=1000,
                pretrained=True,
            )
            self._model = self._model.to(self._device)
            self._model.eval()
        except Exception as exc:
            # Graceful fallback: use random embeddings (for testing without GPU)
            import warnings
            warnings.warn(
                f"torchreid model load failed ({exc}). "
                "Using random embeddings (no real ReID)."
            )
            self._model = "fallback"

    def _extract_embedding(self, crop: np.ndarray) -> np.ndarray:
        """Extract a 512-dim L2-normalised embedding from a BGR crop."""
        self._load_model()

        if self._model == "fallback" or crop is None or crop.size == 0:
            emb = np.random.randn(512).astype(np.float32)
            return emb / (np.linalg.norm(emb) + 1e-8)

        import torch
        import torchvision.transforms as T

        transform = T.Compose([
            T.ToPILImage(),
            T.Resize((256, 128)),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406],
                        std=[0.229, 0.224, 0.225]),
        ])

        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        tensor = transform(rgb).unsqueeze(0).to(self._device)

        with torch.no_grad():
            feat = self._model(tensor)

        emb = feat.squeeze().cpu().numpy().astype(np.float32)
        # L2 normalise
        norm = np.linalg.norm(emb)
        return emb / (norm + 1e-8)

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))  # both already L2-normalised

    def identify(
        self,
        crop: np.ndarray,
        frame_index: int,
    ) -> tuple[str, bool]:
        """
        Match *crop* against the gallery.

        Returns
        -------
        visitor_id : str
            UUID4 string, stable across frames and cameras for the same person.
        uncertain_reid : bool
            True when similarity is in the ambiguous range [new_id_threshold, match_threshold).
        """
        emb = self._extract_embedding(crop)

        best_id: str | None = None
        best_sim: float = -1.0

        for vid, entry in self._gallery.items():
            sim = self._cosine_similarity(emb, entry.embedding)
            if sim > best_sim:
                best_sim = sim
                best_id = vid

        uncertain = False

        if best_sim >= self.match_threshold and best_id is not None:
            # Matched: update embedding with exponential moving average
            alpha = 0.1
            updated = (1 - alpha) * self._gallery[best_id].embedding + alpha * emb
            norm = np.linalg.norm(updated)
            self._gallery[best_id].embedding = updated / (norm + 1e-8)
            self._gallery[best_id].last_seen_frame = frame_index
            return best_id, False

        elif best_sim >= self.new_id_threshold and best_id is not None:
            # Ambiguous range – new ID but flag it
            uncertain = True

        new_id = str(uuid.uuid4())
        self._gallery[new_id] = GalleryEntry(
            visitor_id=new_id,
            embedding=emb,
            last_seen_frame=frame_index,
            uncertain=uncertain,
        )
        return new_id, uncertain

    def gallery_size(self) -> int:
        return len(self._gallery)

    def reset(self) -> None:
        """Clear gallery (between stores, not between cameras of same store)."""
        self._gallery.clear()
