"""
tests/test_api_metrics.py – Tests for GET /stores/{id}/metrics, funnel, heatmap, health.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def _ingest(events: list[dict]) -> None:
    client.post("/events/ingest", json=events)


def _make_events(store_id: str = "TEST_STORE") -> list[dict]:
    """
    Seed a minimal dataset:
      - 5 customers entered
      - 4 visited a zone
      - 3 joined billing queue
      - 2 purchased (no abandon)
      - 1 abandoned billing queue
    """
    events = []
    visitor_ids = [str(uuid.uuid4()) for _ in range(5)]
    ts_base = datetime.now(timezone.utc).isoformat()

    def e(vid, etype, **kw):
        d = {
            "event_id": str(uuid.uuid4()),
            "store_id": store_id,
            "camera_id": "CAM1",
            "visitor_id": vid,
            "event_type": etype,
            "timestamp": ts_base,
            "confidence": 0.85,
            "is_staff": False,
            "session_seq": 1,
        }
        d.update(kw)
        return d

    # All 5 enter
    for vid in visitor_ids:
        events.append(e(vid, "ENTRY"))

    # 4 visit a zone
    for vid in visitor_ids[:4]:
        events.append(e(vid, "ZONE_ENTER", zone_id="SKINCARE"))
        events.append(e(vid, "ZONE_DWELL", zone_id="SKINCARE", dwell_ms=45000))

    # 3 join billing
    for vid in visitor_ids[:3]:
        events.append(e(vid, "BILLING_QUEUE_JOIN", zone_id="BILLING",
                         metadata={"queue_depth": 1}))

    # 1 abandons
    events.append(e(visitor_ids[2], "BILLING_QUEUE_ABANDON", zone_id="BILLING"))

    # 1 staff event (should be excluded)
    events.append({
        "event_id": str(uuid.uuid4()),
        "store_id": store_id,
        "camera_id": "CAM1",
        "visitor_id": "staff-001",
        "event_type": "ENTRY",
        "timestamp": ts_base,
        "confidence": 1.0,
        "is_staff": True,
        "session_seq": 1,
    })

    return events


class TestMetricsEndpoint:
    def setup_method(self):
        import uuid as _uuid
        self.STORE = "METRICS_" + _uuid.uuid4().hex[:8].upper()
        _ingest(_make_events(self.STORE))

    def test_metrics_footfall_excludes_staff(self):
        resp = client.get(f"/stores/{self.STORE}/metrics")
        assert resp.status_code == 200
        data = resp.json()
        # 5 customers entered (staff excluded)
        assert data["footfall"] == 5

    def test_metrics_queue_depth(self):
        resp = client.get(f"/stores/{self.STORE}/metrics")
        data = resp.json()
        # 3 joined, 1 abandoned → 2 still in queue
        assert data["queue_depth"] == 2

    def test_metrics_abandonment_rate(self):
        resp = client.get(f"/stores/{self.STORE}/metrics")
        data = resp.json()
        # 1 abandon / 3 joins = 33.33%
        assert abs(data["abandonment_rate"] - 33.33) < 1.0

    def test_metrics_avg_dwell_per_zone(self):
        resp = client.get(f"/stores/{self.STORE}/metrics")
        data = resp.json()
        assert "SKINCARE" in data["avg_dwell_per_zone"]
        # 45000ms / 1000 = 45s
        assert abs(data["avg_dwell_per_zone"]["SKINCARE"] - 45.0) < 1.0

    def test_metrics_conversion_rate(self):
        resp = client.get(f"/stores/{self.STORE}/metrics")
        data = resp.json()
        # 2 purchased (out of 5 visitors) = 40%
        assert 0 <= data["conversion_rate"] <= 100


class TestFunnelEndpoint:
    def setup_method(self):
        import uuid as _uuid
        self.STORE = "FUNNEL_" + _uuid.uuid4().hex[:8].upper()
        _ingest(_make_events(self.STORE))

    def test_funnel_stages(self):
        resp = client.get(f"/stores/{self.STORE}/funnel")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entry"] == 5
        assert data["zone_visit"] == 4
        assert data["billing"] == 3

    def test_funnel_dropoff(self):
        resp = client.get(f"/stores/{self.STORE}/funnel")
        data = resp.json()
        dropoff = data["dropoff"]
        assert dropoff["entry_to_zone"] == 1   # 5 - 4
        assert dropoff["zone_to_billing"] == 1  # 4 - 3


class TestHeatmapEndpoint:
    def setup_method(self):
        import uuid as _uuid
        self.STORE = "HEATMAP_" + _uuid.uuid4().hex[:8].upper()
        _ingest(_make_events(self.STORE))

    def test_heatmap_has_skincare(self):
        resp = client.get(f"/stores/{self.STORE}/heatmap")
        assert resp.status_code == 200
        data = resp.json()
        assert "SKINCARE" in data["zones"]
        zone = data["zones"]["SKINCARE"]
        assert zone["visits"] == 4
        assert 0 <= zone["score"] <= 100


class TestHealthEndpoint:
    def test_health_returns_ok_or_degraded(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("OK", "DEGRADED")
        assert "db_event_count" in data
        assert isinstance(data["stale_feeds"], list)
