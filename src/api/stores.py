"""
api/stores.py – GET /stores endpoint.

Lists all registered stores with camera topology metadata.
Reads from StoreRegistry (not DB) – configuration-level data only.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..store_registry import get_registry
from .schemas import StoreInfo, StoreListResponse

router = APIRouter()


@router.get(
    "/stores",
    response_model=StoreListResponse,
    summary="List all registered stores",
    description=(
        "Returns configuration-level metadata for all registered stores. "
        "Does not query the event database – topology is read from store_config.json."
    ),
)
async def list_stores() -> StoreListResponse:
    registry = get_registry()
    stores = [
        StoreInfo(
            store_id=cfg.store_id,
            store_name=cfg.store_name,
            city=cfg.city,
            pos_available=cfg.pos_available,
            camera_count=cfg.camera_count,
            entry_cameras=[c.camera_id for c in cfg.cameras_by_role("ENTRY")],
            zone_cameras=[c.camera_id for c in cfg.cameras_by_role("ZONE")],
            billing_cameras=[c.camera_id for c in cfg.cameras_by_role("BILLING")],
        )
        for cfg in registry.list_all()
    ]
    return StoreListResponse(stores=stores, total=len(stores))
