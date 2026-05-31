"""
tests/test_session_manager.py – Unit tests for SessionManager.

Covers session lifecycle, zone tracking, billing queue, staff scoring,
re-entry, conversion rate, and abandonment rate.
"""

import time
import pytest
from src.session_manager import SessionManager


class TestSessionManager:
    def _mgr(self) -> SessionManager:
        return SessionManager(store_id="S1")

    def _now(self) -> float:
        return time.time()

    # ── Session lifecycle ──────────────────────────────────────────────────

    def test_open_session(self):
        mgr = self._mgr()
        session = mgr.open_session("V001", "CAM1", self._now())
        assert session.visitor_id == "V001"
        assert session.session_seq == 1
        assert session.is_active()

    def test_close_session(self):
        mgr = self._mgr()
        t = self._now()
        mgr.open_session("V001", "CAM1", t)
        session = mgr.close_session("V001", t + 60)
        assert session is not None
        assert not session.is_active()
        assert session.exit_time == t + 60

    def test_reentry_increments_seq(self):
        mgr = self._mgr()
        t = self._now()
        mgr.open_session("V001", "CAM1", t)
        mgr.close_session("V001", t + 60)
        # Re-enter
        session2 = mgr.open_session("V001", "CAM1", t + 120)
        assert session2.session_seq == 2
        assert session2.reentry_count == 1

    def test_get_active(self):
        mgr = self._mgr()
        t = self._now()
        mgr.open_session("V001", "CAM1", t)
        assert mgr.get_active("V001") is not None
        mgr.close_session("V001", t + 10)
        assert mgr.get_active("V001") is None

    # ── Zone management ────────────────────────────────────────────────────

    def test_enter_zone(self):
        mgr = self._mgr()
        t = self._now()
        mgr.open_session("V001", "CAM1", t)
        mgr.enter_zone("V001", "SKINCARE", t + 5)
        session = mgr.get_active("V001")
        assert session.current_zone == "SKINCARE"
        assert "SKINCARE" in session.zones_visited

    def test_exit_zone(self):
        mgr = self._mgr()
        t = self._now()
        mgr.open_session("V001", "CAM1", t)
        mgr.enter_zone("V001", "SKINCARE", t + 5)
        mgr.exit_zone("V001", t + 40)
        session = mgr.get_active("V001")
        assert session.current_zone is None

    def test_dwell_fires_after_30s(self):
        mgr = self._mgr()
        t = self._now()
        mgr.open_session("V001", "CAM1", t)
        mgr.enter_zone("V001", "SKINCARE", t)
        # Before 30s: no dwell
        assert mgr.check_dwell("V001", "SKINCARE", t + 20) is None
        # After 30s: dwell fires
        dwell = mgr.check_dwell("V001", "SKINCARE", t + 31)
        assert dwell is not None
        assert dwell >= 30000  # ms

    # ── Billing queue ──────────────────────────────────────────────────────

    def test_billing_queue_join(self):
        mgr = self._mgr()
        t = self._now()
        mgr.open_session("V001", "CAM1", t)
        mgr.open_session("V002", "CAM1", t)
        mgr.join_billing_queue("V001", t + 10)  # V001 joins first
        depth = mgr.join_billing_queue("V002", t + 15)
        assert depth == 1  # 1 person already in queue

    def test_billing_queue_abandon(self):
        mgr = self._mgr()
        t = self._now()
        mgr.open_session("V001", "CAM1", t)
        mgr.join_billing_queue("V001", t + 10)
        should_abandon = mgr.leave_billing_queue("V001", t + 40)
        assert should_abandon is True

    def test_no_abandon_if_purchased(self):
        mgr = self._mgr()
        t = self._now()
        mgr.open_session("V001", "CAM1", t)
        mgr.join_billing_queue("V001", t + 10)
        mgr.mark_purchased("V001")
        should_abandon = mgr.leave_billing_queue("V001", t + 40)
        assert should_abandon is False

    def test_queue_depth(self):
        mgr = self._mgr()
        t = self._now()
        mgr.open_session("V001", "CAM1", t)
        mgr.open_session("V002", "CAM1", t)
        mgr.join_billing_queue("V001", t)
        mgr.join_billing_queue("V002", t + 5)
        assert mgr.current_queue_depth() == 2
        mgr.leave_billing_queue("V002", t + 30)
        assert mgr.current_queue_depth() == 1

    # ── Staff detection ────────────────────────────────────────────────────

    def test_staff_score_long_dwell(self):
        mgr = self._mgr()
        t = self._now()
        session = mgr.open_session("V_STAFF", "CAM1", t)
        session.camera_durations = {"CAM1": 400.0}
        session.dominant_hue = 120.0  # matches uniform hue range [100, 140]
        session = mgr.close_session("V_STAFF", t + 400.0)
        assert session.is_staff is True


    # ── Aggregation ────────────────────────────────────────────────────────

    def test_conversion_rate_zero_if_no_purchase(self):
        mgr = self._mgr()
        t = self._now()
        mgr.open_session("V001", "CAM1", t)
        mgr.close_session("V001", t + 60)
        assert mgr.conversion_rate() == 0.0

    def test_conversion_rate_with_purchase(self):
        mgr = self._mgr()
        t = self._now()
        mgr.open_session("V001", "CAM1", t)
        mgr.mark_purchased("V001")
        mgr.close_session("V001", t + 60)
        assert mgr.conversion_rate() == 100.0

    def test_abandonment_rate(self):
        mgr = self._mgr()
        t = self._now()
        for vid in ["V001", "V002", "V003"]:
            mgr.open_session(vid, "CAM1", t)
        mgr.join_billing_queue("V001", t + 10)
        mgr.join_billing_queue("V002", t + 10)
        mgr.join_billing_queue("V003", t + 10)
        mgr.mark_purchased("V001")
        mgr.leave_billing_queue("V002", t + 30)   # abandon
        mgr.leave_billing_queue("V003", t + 30)   # abandon
        for vid in ["V001", "V002", "V003"]:
            mgr.close_session(vid, t + 60)
        # 2 out of 3 billing visitors abandoned
        rate = mgr.abandonment_rate()
        assert abs(rate - 66.67) < 1.0
