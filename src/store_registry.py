"""
src/store_registry.py – Central registry for all stores and their camera topologies.

Provides:
  CameraRole  – ENTRY | ZONE | BILLING | QUEUE | REAR | UNKNOWN
  StoreConfig – per-store metadata (cameras, POS availability)
  StoreRegistry – lightweight lookup built from store_config.json

Usage
-----
    from src.store_registry import build_registry
    registry = build_registry("src/layout/store_config.json")
    cfg = registry.get("STORE_1")
    print(cfg.pos_available)          # False
    print(cfg.cameras_by_role("ENTRY"))  # ["CAM 3 - entry"]
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────────
# Camera Role Abstraction
# ──────────────────────────────────────────────────────────────────────────────

class CameraRole(str, Enum):
    """Semantic role of a camera within a store."""
    ENTRY   = "ENTRY"    # Counts visitors entering
    ZONE    = "ZONE"     # Monitors brand / product zones
    BILLING = "BILLING"  # Covers checkout / cash counter
    QUEUE   = "QUEUE"    # Monitors queue area (separate from billing)
    REAR    = "REAR"     # Rear displays / supplementary floor view
    UNKNOWN = "UNKNOWN"  # Role not specified in config


# ──────────────────────────────────────────────────────────────────────────────
# Store Config
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class CameraInfo:
    """Metadata for a single camera."""
    camera_id: str
    role: CameraRole
    description: str
    video_file: str | None
    frame_size: list[int] = field(default_factory=lambda: [1920, 1080])

    @property
    def has_video(self) -> bool:
        return bool(self.video_file)


@dataclass
class StoreConfig:
    """All metadata for a single store."""
    store_id: str
    store_name: str
    city: str
    store_open_hour: int
    cameras: list[CameraInfo]
    pos_available: bool
    pos_csv_path: str | None  # Absolute or relative path to POS CSV, None if unavailable
    data_root: str | None     # Root directory where footage resides

    def cameras_by_role(self, role: CameraRole | str) -> list[CameraInfo]:
        """Return all cameras with the given role."""
        target = CameraRole(role) if isinstance(role, str) else role
        return [c for c in self.cameras if c.role == target]

    @property
    def camera_count(self) -> int:
        return len(self.cameras)

    @property
    def entry_camera_count(self) -> int:
        return len(self.cameras_by_role(CameraRole.ENTRY))

    @property
    def zone_camera_count(self) -> int:
        return len(self.cameras_by_role(CameraRole.ZONE))

    @property
    def billing_camera_count(self) -> int:
        return len(self.cameras_by_role(CameraRole.BILLING))


# ──────────────────────────────────────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────────────────────────────────────

class StoreRegistry:
    """Lightweight in-memory registry of all known stores."""

    def __init__(self, stores: dict[str, StoreConfig]) -> None:
        self._stores = stores

    def get(self, store_id: str) -> StoreConfig | None:
        """Return StoreConfig for the given store_id, or None if not registered."""
        return self._stores.get(store_id.upper())

    def require(self, store_id: str) -> StoreConfig:
        """Return StoreConfig or raise KeyError if not registered."""
        cfg = self.get(store_id)
        if cfg is None:
            raise KeyError(
                f"Store '{store_id}' is not registered. "
                f"Known stores: {list(self._stores.keys())}"
            )
        return cfg

    def list_all(self) -> list[StoreConfig]:
        """Return list of all registered StoreConfig objects."""
        return list(self._stores.values())

    def is_registered(self, store_id: str) -> bool:
        return store_id.upper() in self._stores

    def __repr__(self) -> str:
        return f"StoreRegistry(stores={list(self._stores.keys())})"


# ──────────────────────────────────────────────────────────────────────────────
# Factory – build from store_config.json
# ──────────────────────────────────────────────────────────────────────────────

_ROLE_KEYWORDS: dict[CameraRole, list[str]] = {
    CameraRole.ENTRY:   ["entry", "entrance", "door"],
    CameraRole.BILLING: ["billing", "checkout", "cash", "counter", "payment"],
    CameraRole.QUEUE:   ["queue"],
    CameraRole.REAR:    ["rear", "back", "display"],
    CameraRole.ZONE:    ["zone", "floor", "aisle", "main"],
}


def _infer_role(camera_id: str, description: str, video_file: str | None) -> CameraRole:
    """
    Infer CameraRole from config fields.
    Priority: explicit 'role' field > description keywords > video filename keywords > UNKNOWN.
    """
    combined = f"{camera_id} {description} {video_file or ''}".lower()
    for role, keywords in _ROLE_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return role
    return CameraRole.UNKNOWN


def build_registry(
    config_path: str | Path,
    pos_csv_path: str | None = None,
) -> StoreRegistry:
    """
    Build a StoreRegistry from store_config.json.

    Parameters
    ----------
    config_path : str | Path
        Path to store_config.json.
    pos_csv_path : str | None
        Default POS CSV path for stores that have pos_available=true but no
        explicit pos_csv_path in config. Defaults to 'data/pos_transactions.csv'.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"store_config.json not found at {config_path}")

    with open(config_path) as f:
        raw = json.load(f)

    default_pos = pos_csv_path or "data/pos_transactions.csv"
    stores: dict[str, StoreConfig] = {}

    for store_id, store_data in raw.get("stores", {}).items():
        sid = store_id.upper()

        # ── Cameras ──────────────────────────────────────────────────────────
        cameras: list[CameraInfo] = []
        for cam in store_data.get("cameras", []):
            cam_id = cam.get("camera_id", "UNKNOWN")
            desc   = cam.get("description", "")
            vfile  = cam.get("video_file")

            # Explicit role field takes precedence
            if "role" in cam:
                try:
                    role = CameraRole(cam["role"].upper())
                except ValueError:
                    role = CameraRole.UNKNOWN
            else:
                role = _infer_role(cam_id, desc, vfile)

            cameras.append(CameraInfo(
                camera_id=cam_id,
                role=role,
                description=desc,
                video_file=vfile,
                frame_size=cam.get("frame_size", [1920, 1080]),
            ))

        # ── POS availability ─────────────────────────────────────────────────
        pos_available = store_data.get("pos_available", True)
        if pos_available:
            store_pos_path = store_data.get("pos_csv_path") or default_pos
        else:
            store_pos_path = None

        stores[sid] = StoreConfig(
            store_id=sid,
            store_name=store_data.get("store_name", sid),
            city=store_data.get("city", ""),
            store_open_hour=store_data.get("store_open_hour", 10),
            cameras=cameras,
            pos_available=pos_available,
            pos_csv_path=store_pos_path,
            data_root=store_data.get("data_root"),
        )

    return StoreRegistry(stores)


# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton (lazy)
# ──────────────────────────────────────────────────────────────────────────────

_registry_singleton: StoreRegistry | None = None


def get_registry(config_path: str | Path | None = None) -> StoreRegistry:
    """
    Return the module-level registry singleton.
    Builds it on first call using config_path (or default path).
    """
    global _registry_singleton
    if _registry_singleton is None:
        from pathlib import Path as _Path
        default = _Path(__file__).parent / "layout" / "store_config.json"
        _registry_singleton = build_registry(config_path or default)
    return _registry_singleton
