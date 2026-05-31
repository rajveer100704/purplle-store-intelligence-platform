"""
layout/parser.py – Store layout configuration loader.

Loads store_config.json and converts zone definitions into runtime
StoreConfig / CameraConfig dataclasses with Shapely polygons.

Polygons in the JSON are stored as normalised [0, 1] coordinates.
At runtime they are scaled to pixel coordinates for the camera's
frame size.

Usage
-----
    from src.layout.parser import load_store_config
    cfg = load_store_config("src/layout/store_config.json", "ST1008")
    cam = cfg.get_camera("CAM1")
    zones = cam.pixel_zones(1920, 1080)  # dict[str, Polygon]
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shapely.geometry import Polygon


# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ZoneConfig:
    """One named zone (brand shelf, service area, billing, etc.)."""
    zone_id: str
    brand: str | None
    polygon_norm: list[list[float]]   # normalised [0, 1] coords
    zone_type: str = "brand"          # brand | service_area | billing | queue
    wall: str | None = None           # top | bottom | None
    position: int | None = None       # left-to-right index on the wall

    def to_pixel_polygon(self, w: int, h: int) -> Polygon:
        """Scale normalised coords to pixel coords and return a Shapely Polygon."""
        pts = [(x * w, y * h) for x, y in self.polygon_norm]
        return Polygon(pts)


@dataclass
class CameraConfig:
    """Per-camera configuration (entry/exit lines, frame size)."""
    camera_id: str
    description: str
    frame_size: tuple[int, int]
    entry_line: list[list[int]] | None = None
    exit_line: list[list[int]] | None = None

    def pixel_entry_line(self) -> list[list[int]] | None:
        return self.entry_line

    def pixel_exit_line(self) -> list[list[int]] | None:
        return self.exit_line


@dataclass
class StoreConfig:
    """Full configuration for one store, including all zones and cameras."""
    store_id: str
    store_name: str
    city: str
    store_open_hour: int
    cameras: list[CameraConfig]
    brand_zones: list[ZoneConfig]
    billing_zone: ZoneConfig | None = None
    queue_zone: ZoneConfig | None = None

    def get_camera(self, camera_id: str) -> CameraConfig | None:
        """Lookup camera config by ID (case-insensitive)."""
        for cam in self.cameras:
            if cam.camera_id.upper() == camera_id.upper():
                return cam
        return None

    def all_zone_ids(self) -> list[str]:
        """All zone IDs including billing and queue."""
        ids = [z.zone_id for z in self.brand_zones]
        if self.billing_zone:
            ids.append(self.billing_zone.zone_id)
        if self.queue_zone:
            ids.append(self.queue_zone.zone_id)
        return ids

    def brand_zone_ids(self) -> list[str]:
        """Zone IDs that correspond to product brands (excludes service areas)."""
        return [z.zone_id for z in self.brand_zones if z.brand is not None]

    def zone_brand_map(self) -> dict[str, str]:
        """Map zone_id → brand name for brand zones only."""
        return {
            z.zone_id: z.brand
            for z in self.brand_zones
            if z.brand is not None
        }

    def pixel_zones(self, w: int, h: int) -> dict[str, Polygon]:
        """Build all zone polygons scaled to pixel coordinates."""
        zones: dict[str, Polygon] = {}
        for z in self.brand_zones:
            zones[z.zone_id] = z.to_pixel_polygon(w, h)
        if self.billing_zone:
            zones[self.billing_zone.zone_id] = self.billing_zone.to_pixel_polygon(w, h)
        if self.queue_zone:
            zones[self.queue_zone.zone_id] = self.queue_zone.to_pixel_polygon(w, h)
        return zones

    def to_legacy_layout(self) -> dict[str, Any]:
        """Convert to the legacy store_layout dict format for backward compat.

        Returns a dict matching the format expected by the existing
        ``event_emitter._load_zones()`` function so the system works
        with no other code changes during migration.
        """
        cameras_list = []
        for cam in self.cameras:
            cameras_list.append({
                "camera_id": cam.camera_id,
                "entry_line": cam.entry_line,
                "exit_line": cam.exit_line,
            })

        zones_list = []
        for z in self.brand_zones:
            zones_list.append({
                "zone_id": z.zone_id,
                "polygon": z.polygon_norm,
                "brand": z.brand,
            })

        if self.billing_zone:
            zones_list.append({
                "zone_id": self.billing_zone.zone_id,
                "polygon": self.billing_zone.polygon_norm,
            })
        if self.queue_zone:
            zones_list.append({
                "zone_id": self.queue_zone.zone_id,
                "polygon": self.queue_zone.polygon_norm,
            })

        return {
            "stores": {
                self.store_id: {
                    "cameras": cameras_list,
                    "zones": zones_list,
                }
            }
        }


# ──────────────────────────────────────────────────────────────────────────────
# Loader
# ──────────────────────────────────────────────────────────────────────────────

def _parse_zone(raw: dict[str, Any], zone_type: str = "brand") -> ZoneConfig:
    """Parse a single zone entry from JSON."""
    return ZoneConfig(
        zone_id=raw["zone_id"],
        brand=raw.get("brand"),
        polygon_norm=raw.get("polygon", []),
        zone_type=raw.get("type", zone_type),
        wall=raw.get("wall"),
        position=raw.get("position"),
    )


def _parse_camera(raw: dict[str, Any]) -> CameraConfig:
    """Parse a camera entry from JSON."""
    fs = raw.get("frame_size", [1920, 1080])
    return CameraConfig(
        camera_id=raw["camera_id"],
        description=raw.get("description", ""),
        frame_size=(fs[0], fs[1]),
        entry_line=raw.get("entry_line"),
        exit_line=raw.get("exit_line"),
    )


def load_store_config(
    config_path: str | Path,
    store_id: str | None = None,
) -> StoreConfig | None:
    """
    Load a StoreConfig from a JSON file.

    Parameters
    ----------
    config_path : path to store_config.json
    store_id : if provided, load only this store.
               If None and only one store exists, load that one.

    Returns
    -------
    StoreConfig or None if the file / store doesn't exist.
    """
    path = Path(config_path)
    if not path.exists():
        return None

    with open(path) as f:
        data = json.load(f)

    stores = data.get("stores", {})
    if not stores:
        return None

    # Pick the right store
    if store_id:
        store_data = stores.get(store_id) or stores.get(store_id.upper())
    else:
        # Default to first (and likely only) store
        store_id = next(iter(stores))
        store_data = stores[store_id]

    if not store_data:
        return None

    cameras = [_parse_camera(c) for c in store_data.get("cameras", [])]
    brand_zones = [_parse_zone(z) for z in store_data.get("brand_zones", [])]

    billing_raw = store_data.get("billing_zone")
    billing_zone = _parse_zone(billing_raw, "billing") if billing_raw else None

    queue_raw = store_data.get("queue_zone")
    queue_zone = _parse_zone(queue_raw, "queue") if queue_raw else None

    return StoreConfig(
        store_id=store_id,
        store_name=store_data.get("store_name", store_id),
        city=store_data.get("city", ""),
        store_open_hour=store_data.get("store_open_hour", 9),
        cameras=cameras,
        brand_zones=brand_zones,
        billing_zone=billing_zone,
        queue_zone=queue_zone,
    )
