"""
tests/test_api_ingest.py – Integration tests for POST /events/ingest.

Uses FastAPI's TestClient (synchronous) via httpx.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def _event(**overrides) -> dict:
    base = {
        "event_id": str(uuid.uuid4()),
        "store_id": "S1",
        "camera_id": "CAM1",
        "visitor_id": str(uuid.uuid4()),
        "event_type": "ENTRY",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence": 0.9,
        "is_staff": False,
        "session_seq": 1,
    }
    base.update(overrides)
    return base


class TestIngestEndpoint:
    def test_ingest_single_entry_event(self):
        resp = client.post("/events/ingest", json=[_event()])
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] == 1
        assert data["rejected"] == []

    def test_ingest_idempotent(self):
        evt = _event()
        r1 = client.post("/events/ingest", json=[evt])
        r2 = client.post("/events/ingest", json=[evt])
        assert r1.json()["accepted"] == 1
        # Second ingest should silently skip (merge deduplication)
        assert r2.json()["accepted"] == 1  # merged = no-op for same event_id

    def test_ingest_zone_dwell_requires_dwell_ms(self):
        evt = _event(
            event_type="ZONE_DWELL",
            zone_id="SKINCARE",
            # dwell_ms intentionally missing
        )
        resp = client.post("/events/ingest", json=[evt])
        assert resp.status_code == 200
        data = resp.json()
        assert data["rejected"][0]["event_id"] == evt["event_id"]

    def test_ingest_zone_enter_requires_zone_id(self):
        evt = _event(event_type="ZONE_ENTER")  # no zone_id
        resp = client.post("/events/ingest", json=[evt])
        data = resp.json()
        assert len(data["rejected"]) == 1

    def test_ingest_invalid_event_type(self):
        evt = _event(event_type="PURCHASE")  # not in schema
        resp = client.post("/events/ingest", json=[evt])
        data = resp.json()
        assert len(data["rejected"]) == 1
        assert "PURCHASE" in data["rejected"][0]["errors"][0]

    def test_ingest_batch_mixed_valid_invalid(self):
        events = [
            _event(),
            _event(event_type="ZONE_ENTER", zone_id="SKINCARE"),
            _event(event_type="INVALID_TYPE"),   # rejected
            _event(event_type="ZONE_DWELL", zone_id="BILLING"),   # missing dwell_ms
        ]
        resp = client.post("/events/ingest", json=events)
        data = resp.json()
        assert data["accepted"] == 2
        assert len(data["rejected"]) == 2

    def test_ingest_exceeds_batch_limit(self):
        events = [_event() for _ in range(501)]
        resp = client.post("/events/ingest", json=events)
        assert resp.status_code == 422

    def test_ingest_billing_queue_join_valid(self):
        evt = _event(
            event_type="BILLING_QUEUE_JOIN",
            zone_id="BILLING",
            metadata={"queue_depth": 3},
        )
        resp = client.post("/events/ingest", json=[evt])
        assert resp.json()["accepted"] == 1

    def test_ingest_reentry_valid(self):
        evt = _event(event_type="REENTRY", session_seq=2)
        resp = client.post("/events/ingest", json=[evt])
        assert resp.json()["accepted"] == 1

    def test_ingest_low_confidence_not_rejected(self):
        """Challenge: do not suppress low-confidence events."""
        evt = _event(confidence=0.01)
        resp = client.post("/events/ingest", json=[evt])
        assert resp.json()["accepted"] == 1
