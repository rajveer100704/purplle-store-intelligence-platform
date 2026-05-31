"""
api/schemas.py – Pydantic v2 request/response models.

All models use strict validation and clear field descriptions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ──────────────────────────────────────────────────────────────────────────────
# Valid event types (challenge-defined, no PURCHASE)
# ──────────────────────────────────────────────────────────────────────────────

VALID_EVENT_TYPES = {
    "ENTRY",
    "EXIT",
    "ZONE_ENTER",
    "ZONE_EXIT",
    "ZONE_DWELL",
    "BILLING_QUEUE_JOIN",
    "BILLING_QUEUE_ABANDON",
    "REENTRY",
}


# ──────────────────────────────────────────────────────────────────────────────
# Ingest schemas
# ──────────────────────────────────────────────────────────────────────────────

class EventIn(BaseModel):
    event_id: str = Field(..., description="Unique event identifier (UUID4 recommended)")
    store_id: str = Field(..., min_length=1)
    camera_id: str = Field(..., min_length=1)
    visitor_id: str = Field(..., min_length=1)
    event_type: str = Field(..., description=f"One of: {', '.join(sorted(VALID_EVENT_TYPES))}")
    timestamp: datetime = Field(..., description="ISO-8601 UTC timestamp")
    zone_id: str | None = Field(None)
    dwell_ms: int | None = Field(None, ge=0)
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    is_staff: bool = Field(False)
    session_seq: int = Field(1, ge=1)
    uncertain_reid: bool = Field(False)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if v not in VALID_EVENT_TYPES:
            raise ValueError(
                f"Invalid event_type '{v}'. Must be one of: {sorted(VALID_EVENT_TYPES)}"
            )
        return v

    @model_validator(mode="after")
    def validate_zone_fields(self) -> "EventIn":
        zone_required = {"ZONE_ENTER", "ZONE_EXIT", "ZONE_DWELL",
                         "BILLING_QUEUE_JOIN", "BILLING_QUEUE_ABANDON"}
        if self.event_type in zone_required and not self.zone_id:
            raise ValueError(f"zone_id is required for event_type={self.event_type!r}")
        if self.event_type == "ZONE_DWELL" and self.dwell_ms is None:
            raise ValueError("dwell_ms is required for ZONE_DWELL events")
        return self


class IngestRequest(BaseModel):
    """Accepts a list directly (see /events/ingest endpoint for list handling)."""
    pass


class RejectedEvent(BaseModel):
    event_id: str
    errors: list[str]


class IngestResponse(BaseModel):
    accepted: int
    rejected: list[RejectedEvent]
    total: int


# ──────────────────────────────────────────────────────────────────────────────
# Metrics response
# ──────────────────────────────────────────────────────────────────────────────

class MetricsResponse(BaseModel):
    store_id: str
    footfall: int
    unique_visitors: int
    conversion_rate: float = Field(..., description="Percentage 0–100")
    avg_dwell_per_zone: dict[str, float] = Field(
        default_factory=dict, description="Zone → avg dwell in seconds"
    )
    queue_depth: int
    abandonment_rate: float = Field(..., description="Percentage 0–100")
    brand_conversion: dict[str, float] = Field(
        default_factory=dict, description="Brand zone_id -> conversion percentage"
    )
    total_revenue: float | None = Field(None, description="Total matched POS revenue")
    computed_at: datetime


# ──────────────────────────────────────────────────────────────────────────────
# Funnel response
# ──────────────────────────────────────────────────────────────────────────────

class FunnelDropoff(BaseModel):
    entry_to_zone: int
    zone_to_billing: int
    billing_to_purchase: int


class FunnelResponse(BaseModel):
    store_id: str
    entry: int
    zone_visit: int
    billing: int
    purchase: int
    dropoff: FunnelDropoff
    computed_at: datetime


# ──────────────────────────────────────────────────────────────────────────────
# Heatmap response
# ──────────────────────────────────────────────────────────────────────────────

class ZoneHeatmap(BaseModel):
    visits: int
    avg_dwell_s: float
    score: int = Field(..., ge=0, le=100, description="Engagement score 0–100")
    brand: str | None = Field(None, description="Brand name associated with this zone")


class HeatmapResponse(BaseModel):
    store_id: str
    zones: dict[str, ZoneHeatmap]
    computed_at: datetime


# ──────────────────────────────────────────────────────────────────────────────
# Anomaly response
# ──────────────────────────────────────────────────────────────────────────────

class AnomalyItem(BaseModel):
    type: str
    severity: Literal["INFO", "WARN", "CRITICAL"]
    store_id: str
    action: str
    details: dict[str, Any] = Field(default_factory=dict)


class AnomaliesResponse(BaseModel):
    store_id: str
    anomalies: list[AnomalyItem]
    computed_at: datetime


# ──────────────────────────────────────────────────────────────────────────────
# Health response
# ──────────────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: Literal["OK", "DEGRADED"]
    last_event_per_store: dict[str, str] = Field(
        default_factory=dict, description="store_id → ISO timestamp"
    )
    stale_feeds: list[str] = Field(
        default_factory=list, description="Store IDs with no events in last 10 min"
    )
    db_event_count: int
    checked_at: datetime
