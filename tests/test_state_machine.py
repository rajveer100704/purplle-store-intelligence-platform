"""
tests/test_state_machine.py – Unit tests for VisitorStateMachine.

Covers all states, valid transitions, illegal transitions,
re-entry logic, and event type returns.
"""

import pytest
from src.state_machine import VisitorStateMachine, VisitorState


class TestVisitorStateMachine:
    def _sm(self) -> VisitorStateMachine:
        return VisitorStateMachine(visitor_id="test-visitor")

    # ── Initial state ──────────────────────────────────────────────────────

    def test_initial_state_is_outside(self):
        sm = self._sm()
        assert sm.state == VisitorState.OUTSIDE

    # ── ENTRY ──────────────────────────────────────────────────────────────

    def test_entry_from_outside(self):
        sm = self._sm()
        event = sm.trigger("entry_line_crossed")
        assert event == "ENTRY"
        assert sm.state == VisitorState.ENTERED

    def test_cannot_enter_twice(self):
        sm = self._sm()
        sm.trigger("entry_line_crossed")
        with pytest.raises(ValueError, match="Illegal transition"):
            sm.trigger("entry_line_crossed")

    # ── ZONE events ────────────────────────────────────────────────────────

    def test_zone_enter_from_entered(self):
        sm = self._sm()
        sm.trigger("entry_line_crossed")
        event = sm.trigger("zone_enter")
        assert event == "ZONE_ENTER"
        assert sm.state == VisitorState.IN_ZONE

    def test_zone_dwell_selfloop(self):
        sm = self._sm()
        sm.trigger("entry_line_crossed")
        sm.trigger("zone_enter")
        event = sm.trigger("zone_dwell")
        assert event == "ZONE_DWELL"
        assert sm.state == VisitorState.IN_ZONE

    def test_zone_exit_returns_to_entered(self):
        sm = self._sm()
        sm.trigger("entry_line_crossed")
        sm.trigger("zone_enter")
        event = sm.trigger("zone_exit")
        assert event == "ZONE_EXIT"
        assert sm.state == VisitorState.ENTERED

    # ── BILLING ────────────────────────────────────────────────────────────

    def test_billing_enter_from_entered(self):
        sm = self._sm()
        sm.trigger("entry_line_crossed")
        event = sm.trigger("billing_enter")
        assert event is None  # BILLING_QUEUE_JOIN emitted conditionally
        assert sm.state == VisitorState.IN_BILLING

    def test_billing_exit_abandon(self):
        sm = self._sm()
        sm.trigger("entry_line_crossed")
        sm.trigger("billing_enter")
        event = sm.trigger("billing_exit")
        assert event is None  # BILLING_QUEUE_ABANDON emitted by emitter
        assert sm.state == VisitorState.ENTERED



    # ── EXIT ───────────────────────────────────────────────────────────────

    def test_exit_from_entered(self):
        sm = self._sm()
        sm.trigger("entry_line_crossed")
        event = sm.trigger("exit_line_crossed")
        assert event == "EXIT"
        assert sm.state == VisitorState.EXITED

    def test_exit_from_in_zone(self):
        sm = self._sm()
        sm.trigger("entry_line_crossed")
        sm.trigger("zone_enter")
        event = sm.trigger("exit_line_crossed")
        assert event == "EXIT"

    # ── REENTRY ────────────────────────────────────────────────────────────

    def test_reentry_after_exit(self):
        sm = self._sm()
        sm.trigger("entry_line_crossed")
        sm.trigger("exit_line_crossed")
        event = sm.trigger("entry_line_crossed")
        assert event == "REENTRY"
        assert sm.state == VisitorState.REENTERED

    def test_normalise_after_reentry(self):
        sm = self._sm()
        sm.trigger("entry_line_crossed")
        sm.trigger("exit_line_crossed")
        sm.trigger("entry_line_crossed")  # REENTRY
        sm.trigger("normalise")
        assert sm.state == VisitorState.ENTERED

    # ── Helper methods ─────────────────────────────────────────────────────

    def test_is_inside_after_entry(self):
        sm = self._sm()
        assert not sm.is_inside()
        sm.trigger("entry_line_crossed")
        assert sm.is_inside()

    def test_not_inside_after_exit(self):
        sm = self._sm()
        sm.trigger("entry_line_crossed")
        sm.trigger("exit_line_crossed")
        assert not sm.is_inside()

    def test_is_in_billing(self):
        sm = self._sm()
        sm.trigger("entry_line_crossed")
        assert not sm.is_in_billing()
        sm.trigger("billing_enter")
        assert sm.is_in_billing()



    def test_can_trigger(self):
        sm = self._sm()
        assert sm.can_trigger("entry_line_crossed")
        assert not sm.can_trigger("zone_enter")  # not yet inside
