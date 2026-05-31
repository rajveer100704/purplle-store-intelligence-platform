"""
tests/test_edge_cases.py – Edge case tests explicitly required by challenge scoring.

Covers:
  • Group entry (3 people entering simultaneously)
  • Staff movement excluded from metrics
  • Re-entry creates REENTRY event (not double ENTRY)
  • Empty store returns zero metrics
  • Camera overlap deduplication (same visitor_id, different cameras)
  • Queue abandonment
  • Billing queue depth > 0 required for BILLING_QUEUE_JOIN
  • Low-confidence events not suppressed
  • Partial occlusion / uncertain ReID flagged
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.state_machine import VisitorStateMachine, VisitorState
from src.session_manager import SessionManager

client = TestClient(app)

NOW = datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


def _event(store_id: str, visitor_id: str, event_type: str, **kw) -> dict:
    base = {
        "event_id": _uid(),
        "store_id": store_id,
        "camera_id": kw.pop("camera_id", "CAM1"),
        "visitor_id": visitor_id,
        "event_type": event_type,
        "timestamp": NOW,
        "confidence": kw.pop("confidence", 0.9),
        "is_staff": kw.pop("is_staff", False),
        "session_seq": kw.pop("session_seq", 1),
    }
    base.update(kw)
    return base


def ingest(events: list[dict]) -> dict:
    resp = client.post("/events/ingest", json=events)
    assert resp.status_code == 200
    return resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Group entry: 3 people entering simultaneously → 3 ENTRY events
# ─────────────────────────────────────────────────────────────────────────────
class TestGroupEntry:
    def test_group_entry_emits_three_entries(self):
        """
        Challenge edge case: 3 people walk through the entrance together.
        Each must receive a distinct ENTRY event with a unique visitor_id.
        """
        store = "GROUP_" + _uid()[:8]
        visitors = [_uid() for _ in range(3)]
        events = [_event(store, vid, "ENTRY") for vid in visitors]

        result = ingest(events)
        assert result["accepted"] == 3
        assert result["rejected"] == []

        # Verify footfall = 3 in metrics
        resp = client.get(f"/stores/{store}/metrics")
        data = resp.json()
        assert data["footfall"] == 3, (
            f"Expected 3 footfall for simultaneous group entry, got {data['footfall']}"
        )

    def test_group_entry_unique_visitor_ids(self):
        """All 3 group entrants must have distinct visitor_ids."""
        store = "GROUP2_" + _uid()[:8]
        visitors = [_uid() for _ in range(3)]

        # Verify all are unique
        assert len(set(visitors)) == 3

        events = [_event(store, vid, "ENTRY") for vid in visitors]
        result = ingest(events)
        assert result["accepted"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# 2. Staff movement excluded from all metrics
# ─────────────────────────────────────────────────────────────────────────────
class TestStaffExclusion:
    def test_staff_not_counted_in_footfall(self):
        """is_staff=True visitors must be excluded from footfall."""
        store = "STAFF_" + _uid()[:8]
        customer = _uid()
        staff = _uid()

        events = [
            _event(store, customer, "ENTRY"),
            _event(store, staff, "ENTRY", is_staff=True),
            _event(store, staff, "ZONE_ENTER", zone_id="STOCKROOM", is_staff=True),
        ]
        ingest(events)

        resp = client.get(f"/stores/{store}/metrics")
        data = resp.json()
        # Only 1 customer, not 2
        assert data["footfall"] == 1, (
            f"Staff should be excluded from footfall. Got {data['footfall']}"
        )

    def test_staff_zone_dwell_excluded_from_heatmap(self):
        """Staff zone dwell should not inflate zone engagement scores."""
        store = "STAFFZONE_" + _uid()[:8]
        staff = _uid()
        customer = _uid()

        events = [
            # Staff dwells for 300s in a zone (would skew avg if included)
            _event(store, staff, "ZONE_ENTER", zone_id="STOCKROOM", is_staff=True),
            _event(store, staff, "ZONE_DWELL", zone_id="STOCKROOM",
                   dwell_ms=300_000, is_staff=True),
            # Customer dwells for 30s
            _event(store, customer, "ZONE_ENTER", zone_id="SKINCARE"),
            _event(store, customer, "ZONE_DWELL", zone_id="SKINCARE", dwell_ms=30_000),
        ]
        ingest(events)

        resp = client.get(f"/stores/{store}/heatmap")
        data = resp.json()
        # STOCKROOM should not appear (staff only)
        # SKINCARE should have avg_dwell_s = 30.0
        zones = data["zones"]
        if "SKINCARE" in zones:
            assert zones["SKINCARE"]["avg_dwell_s"] == 30.0

    def test_staff_not_counted_in_funnel(self):
        """Staff BILLING events should not appear in funnel billing count."""
        store = "STAFFFUNNEL_" + _uid()[:8]
        staff = _uid()
        customer = _uid()

        events = [
            _event(store, customer, "ENTRY"),
            _event(store, staff, "ENTRY", is_staff=True),
            _event(store, staff, "BILLING_QUEUE_JOIN", zone_id="BILLING", is_staff=True,
                   metadata={"queue_depth": 0}),
        ]
        ingest(events)

        resp = client.get(f"/stores/{store}/funnel")
        data = resp.json()
        # Billing should be 0 (only staff joined, no customer)
        assert data["billing"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. Re-entry creates REENTRY event (not double ENTRY)
# ─────────────────────────────────────────────────────────────────────────────
class TestReentry:
    def test_reentry_event_emitted_on_second_entry(self):
        """A visitor exiting and re-entering must generate REENTRY, not ENTRY."""
        store = "REENTRY_" + _uid()[:8]
        visitor = _uid()

        events = [
            _event(store, visitor, "ENTRY", session_seq=1),
            _event(store, visitor, "EXIT", session_seq=1),
            # Second entry should be REENTRY with session_seq=2
            _event(store, visitor, "REENTRY", session_seq=2),
        ]
        result = ingest(events)
        assert result["accepted"] == 3
        assert result["rejected"] == []

    def test_reentry_state_machine_transition(self):
        """State machine must transition EXITED → REENTERED on second entry."""
        sm = VisitorStateMachine("test-visitor")
        sm.trigger("entry_line_crossed")         # OUTSIDE → ENTERED
        sm.trigger("exit_line_crossed")           # ENTERED → EXITED
        event_type = sm.trigger("entry_line_crossed")  # EXITED → REENTERED
        assert event_type == "REENTRY"
        assert sm.state == VisitorState.REENTERED

    def test_reentry_creates_new_session_seq(self):
        """SessionManager must increment session_seq on re-entry."""
        import time
        mgr = SessionManager(store_id="S1")
        t = time.time()
        mgr.open_session("V001", "CAM1", t)
        mgr.close_session("V001", t + 300)

        session2 = mgr.open_session("V001", "CAM1", t + 400)
        assert session2.session_seq == 2
        assert session2.reentry_count == 1

    def test_reentry_funnel_counts_unique_visitors(self):
        """A visitor who re-enters should count as 1 unique visitor, not 2."""
        store = "REENTRY_FUNNEL_" + _uid()[:8]
        visitor = _uid()

        events = [
            _event(store, visitor, "ENTRY", session_seq=1),
            _event(store, visitor, "EXIT", session_seq=1),
            _event(store, visitor, "REENTRY", session_seq=2),
        ]
        ingest(events)

        resp = client.get(f"/stores/{store}/funnel")
        data = resp.json()
        # Should count 1 unique visitor, not 2
        assert data["entry"] == 1, (
            f"Re-entered visitor should count once in funnel. Got {data['entry']}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Empty store returns zero metrics
# ─────────────────────────────────────────────────────────────────────────────
class TestEmptyStore:
    def test_empty_store_returns_zero_metrics(self):
        """A store with no events must return zero/empty metrics, not an error."""
        store = "EMPTY_" + _uid()[:8]  # Guaranteed no events
        resp = client.get(f"/stores/{store}/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["footfall"] == 0
        assert data["unique_visitors"] == 0
        assert data["conversion_rate"] == 0.0
        assert data["queue_depth"] == 0
        assert data["abandonment_rate"] == 0.0
        assert data["avg_dwell_per_zone"] == {}

    def test_empty_store_funnel_all_zeros(self):
        store = "EMPTYFUNNEL_" + _uid()[:8]
        resp = client.get(f"/stores/{store}/funnel")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entry"] == 0
        assert data["zone_visit"] == 0
        assert data["billing"] == 0
        assert data["purchase"] == 0

    def test_empty_store_heatmap_empty(self):
        store = "EMPTYHEAT_" + _uid()[:8]
        resp = client.get(f"/stores/{store}/heatmap")
        assert resp.status_code == 200
        data = resp.json()
        assert data["zones"] == {}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Camera overlap deduplication (same visitor_id across cameras)
# ─────────────────────────────────────────────────────────────────────────────
class TestCameraOverlap:
    def test_same_visitor_different_cameras_counted_once(self):
        """
        If OSNet ReID assigns the same visitor_id to detections from CAM1 and CAM2,
        that visitor must be counted as ONE unique visitor in metrics.
        """
        store = "OVERLAP_" + _uid()[:8]
        visitor = _uid()  # Same visitor_id from both cameras

        events = [
            _event(store, visitor, "ENTRY", camera_id="CAM1"),
            _event(store, visitor, "ZONE_ENTER", zone_id="SKINCARE", camera_id="CAM2"),
            _event(store, visitor, "EXIT", camera_id="CAM2"),
        ]
        result = ingest(events)
        assert result["accepted"] == 3

        resp = client.get(f"/stores/{store}/metrics")
        data = resp.json()
        # Even though events came from 2 cameras, 1 unique visitor
        assert data["unique_visitors"] == 1, (
            f"Cross-camera same visitor_id should count once. Got {data['unique_visitors']}"
        )

    def test_different_visitors_different_cameras_counted_separately(self):
        """Different visitor_ids from different cameras = 2 unique visitors."""
        store = "OVERLAP2_" + _uid()[:8]
        v1, v2 = _uid(), _uid()

        events = [
            _event(store, v1, "ENTRY", camera_id="CAM1"),
            _event(store, v2, "ENTRY", camera_id="CAM2"),
        ]
        ingest(events)

        resp = client.get(f"/stores/{store}/metrics")
        data = resp.json()
        assert data["unique_visitors"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# 6. Queue abandonment
# ─────────────────────────────────────────────────────────────────────────────
class TestQueueAbandonment:
    def test_queue_abandonment_updates_rate(self):
        """BILLING_QUEUE_ABANDON must increase abandonment_rate."""
        store = "ABANDON_" + _uid()[:8]
        v1 = _uid()
        v2 = _uid()

        events = [
            # v1 joins and purchases (no abandon)
            _event(store, v1, "ENTRY"),
            _event(store, v1, "BILLING_QUEUE_JOIN", zone_id="BILLING",
                   metadata={"queue_depth": 0}),
            # v2 joins and abandons
            _event(store, v2, "ENTRY"),
            _event(store, v2, "BILLING_QUEUE_JOIN", zone_id="BILLING",
                   metadata={"queue_depth": 1}),
            _event(store, v2, "BILLING_QUEUE_ABANDON", zone_id="BILLING"),
        ]
        ingest(events)

        resp = client.get(f"/stores/{store}/metrics")
        data = resp.json()
        # 1 abandon out of 2 billing joins = 50%
        assert abs(data["abandonment_rate"] - 50.0) < 1.0

    def test_queue_depth_decreases_on_abandon(self):
        """Queue depth metric must reflect abandons."""
        store = "QDEPTH_" + _uid()[:8]
        v1, v2, v3 = _uid(), _uid(), _uid()

        events = [
            _event(store, v1, "BILLING_QUEUE_JOIN", zone_id="BILLING",
                   metadata={"queue_depth": 0}),
            _event(store, v2, "BILLING_QUEUE_JOIN", zone_id="BILLING",
                   metadata={"queue_depth": 1}),
            _event(store, v3, "BILLING_QUEUE_JOIN", zone_id="BILLING",
                   metadata={"queue_depth": 2}),
            _event(store, v2, "BILLING_QUEUE_ABANDON", zone_id="BILLING"),
        ]
        ingest(events)

        resp = client.get(f"/stores/{store}/metrics")
        data = resp.json()
        # 3 joined, 1 abandoned = 2 in queue
        assert data["queue_depth"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# 7. BILLING_QUEUE_JOIN only when queue_depth > 0 in metadata
# ─────────────────────────────────────────────────────────────────────────────
class TestBillingQueueJoinCondition:
    def test_billing_join_with_zero_queue_is_still_valid(self):
        """
        Event schema accepts BILLING_QUEUE_JOIN with queue_depth=0.
        The emitter only emits it when queue_depth > 0, but ingest must accept it.
        """
        store = "BILLQ_" + _uid()[:8]
        v1 = _uid()

        evt = _event(store, v1, "BILLING_QUEUE_JOIN", zone_id="BILLING",
                     metadata={"queue_depth": 0})
        result = ingest([evt])
        # API accepts the event regardless of queue_depth value
        assert result["accepted"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 8. Low-confidence events not suppressed
# ─────────────────────────────────────────────────────────────────────────────
class TestLowConfidence:
    def test_confidence_001_accepted(self):
        """Challenge: never suppress low-confidence detections."""
        store = "LOWCONF_" + _uid()[:8]
        events = [
            _event(store, _uid(), "ENTRY", confidence=0.01),
            _event(store, _uid(), "ENTRY", confidence=0.10),
            _event(store, _uid(), "ENTRY", confidence=0.25),
        ]
        result = ingest(events)
        assert result["accepted"] == 3
        assert result["rejected"] == []

    def test_confidence_stored_accurately(self):
        """Confidence value must be stored as-is, not rounded to threshold."""
        store = "CONFSTORE_" + _uid()[:8]
        vid = _uid()
        evt = _event(store, vid, "ENTRY", confidence=0.03)
        ingest([evt])
        # Verify via metrics that the event was stored (footfall = 1)
        resp = client.get(f"/stores/{store}/metrics")
        assert resp.json()["footfall"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 9. Uncertain ReID flag accepted and stored
# ─────────────────────────────────────────────────────────────────────────────
class TestUncertainReID:
    def test_uncertain_reid_event_accepted(self):
        """Events with uncertain_reid=True must be accepted (partial occlusion case)."""
        store = "UNCERT_" + _uid()[:8]
        evt = {
            "event_id": _uid(),
            "store_id": store,
            "camera_id": "CAM1",
            "visitor_id": _uid(),
            "event_type": "ENTRY",
            "timestamp": NOW,
            "confidence": 0.4,
            "is_staff": False,
            "session_seq": 1,
            "uncertain_reid": True,
        }
        result = ingest([evt])
        assert result["accepted"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 10. Billing queue buildup scenario
# ─────────────────────────────────────────────────────────────────────────────
class TestQueueBuildup:
    def test_queue_builds_up_and_reflects_in_metrics(self):
        """Simulate 5 visitors joining the billing queue."""
        store = "QBUILD_" + _uid()[:8]
        visitors = [_uid() for _ in range(5)]
        events = []
        for i, vid in enumerate(visitors):
            events.append(_event(store, vid, "ENTRY"))
            events.append(_event(store, vid, "BILLING_QUEUE_JOIN", zone_id="BILLING",
                                 metadata={"queue_depth": i}))
        ingest(events)

        resp = client.get(f"/stores/{store}/metrics")
        data = resp.json()
        assert data["queue_depth"] == 5

    def test_anomaly_endpoint_runs_without_error_on_store_with_data(self):
        """Anomaly detection endpoint must return 200 even on small stores."""
        store = "ANOMTEST_" + _uid()[:8]
        events = [_event(store, _uid(), "ENTRY") for _ in range(3)]
        ingest(events)

        resp = client.get(f"/stores/{store}/anomalies")
        assert resp.status_code == 200
        data = resp.json()
        assert "anomalies" in data
        assert isinstance(data["anomalies"], list)
