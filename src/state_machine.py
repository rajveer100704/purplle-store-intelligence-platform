"""
state_machine.py – VisitorStateMachine.

Implements a strict finite-state machine for each tracked visitor.
The state machine ensures events are emitted in the correct order and
prevents logically impossible transitions (e.g. ZONE_EXIT before ZONE_ENTER).

States
------
OUTSIDE      Initial state – person not yet seen in store
ENTERED      Person crossed entry line, inside store
IN_ZONE      Person inside a named zone
IN_BILLING   Person inside the billing/checkout zone
EXITED       Person crossed exit boundary
REENTERED    Person re-entered after a prior EXIT

Interviewers frequently ask: "How do you handle someone who leaves and
comes back?"  The REENTERED state and REENTRY event directly answer this.
"""

from __future__ import annotations

from enum import Enum, auto


class VisitorState(Enum):
    OUTSIDE    = auto()
    ENTERED    = auto()
    IN_ZONE    = auto()
    IN_BILLING = auto()
    EXITED     = auto()
    REENTERED  = auto()


# ──────────────────────────────────────────────────────────────────────────────
# Valid transitions table
# ──────────────────────────────────────────────────────────────────────────────

# Maps (current_state, trigger) → next_state
# Any transition not in this table is illegal and will raise an error.
TRANSITIONS: dict[tuple[VisitorState, str], VisitorState] = {
    # ── First entry ───────────────────────────────────────────────────────
    (VisitorState.OUTSIDE,    "entry_line_crossed"): VisitorState.ENTERED,

    # ── Zone movements ────────────────────────────────────────────────────
    (VisitorState.ENTERED,    "zone_enter"):         VisitorState.IN_ZONE,
    (VisitorState.IN_ZONE,    "zone_enter"):         VisitorState.IN_ZONE,    # zone-to-zone
    (VisitorState.IN_ZONE,    "zone_exit"):          VisitorState.ENTERED,
    (VisitorState.IN_ZONE,    "zone_dwell"):         VisitorState.IN_ZONE,    # self-loop

    # ── Billing zone ──────────────────────────────────────────────────────
    (VisitorState.ENTERED,    "billing_enter"):      VisitorState.IN_BILLING,
    (VisitorState.IN_ZONE,    "billing_enter"):      VisitorState.IN_BILLING,
    (VisitorState.IN_BILLING, "billing_exit"):       VisitorState.ENTERED,    # no purchase

    # ── Exit ──────────────────────────────────────────────────────────────
    (VisitorState.ENTERED,    "exit_line_crossed"):  VisitorState.EXITED,
    (VisitorState.IN_ZONE,    "exit_line_crossed"):  VisitorState.EXITED,
    (VisitorState.IN_BILLING, "exit_line_crossed"):  VisitorState.EXITED,

    # ── Re-entry ──────────────────────────────────────────────────────────
    (VisitorState.EXITED,     "entry_line_crossed"): VisitorState.REENTERED,
    (VisitorState.REENTERED,  "zone_enter"):         VisitorState.IN_ZONE,
    (VisitorState.REENTERED,  "billing_enter"):      VisitorState.IN_BILLING,
    (VisitorState.REENTERED,  "exit_line_crossed"):  VisitorState.EXITED,
    # After REENTRY event is emitted the state normalises back to ENTERED
    (VisitorState.REENTERED,  "normalise"):          VisitorState.ENTERED,
}


class VisitorStateMachine:
    """
    One state machine instance per active visitor (track / visitor_id).

    Usage
    -----
    sm = VisitorStateMachine(visitor_id="abc-123")
    event_type = sm.trigger("entry_line_crossed")
    # → "ENTRY"
    """

    # Maps trigger → event_type string (None means no event emitted)
    TRIGGER_TO_EVENT: dict[str, str | None] = {
        "entry_line_crossed": "ENTRY",
        "zone_enter":         "ZONE_ENTER",
        "zone_exit":          "ZONE_EXIT",
        "zone_dwell":         "ZONE_DWELL",
        "billing_enter":      None,          # BILLING_QUEUE_JOIN emitted conditionally
        "billing_exit":       None,          # BILLING_QUEUE_ABANDON emitted conditionally
        "exit_line_crossed":  "EXIT",
        "normalise":          None,
    }
    # Re-entry is special: same trigger as entry_line_crossed but emits REENTRY
    REENTRY_STATES = {VisitorState.EXITED, VisitorState.REENTERED}

    def __init__(self, visitor_id: str) -> None:
        self.visitor_id = visitor_id
        self.state = VisitorState.OUTSIDE
        self._history: list[tuple[str, VisitorState, VisitorState]] = []

    def trigger(self, event: str) -> str | None:
        """
        Apply *event* trigger to the state machine.

        Returns the event_type string to emit (or None for internal transitions).
        Raises ValueError for illegal transitions.
        """
        key = (self.state, event)
        next_state = TRANSITIONS.get(key)

        if next_state is None:
            raise ValueError(
                f"[{self.visitor_id}] Illegal transition: "
                f"{self.state.name} + '{event}'"
            )

        self._history.append((event, self.state, next_state))
        prev_state = self.state
        self.state = next_state

        # Special case: REENTERED state → emit REENTRY instead of ENTRY
        if prev_state in self.REENTRY_STATES and event == "entry_line_crossed":
            return "REENTRY"

        return self.TRIGGER_TO_EVENT.get(event)

    def can_trigger(self, event: str) -> bool:
        """Return True if the trigger is valid in the current state."""
        return (self.state, event) in TRANSITIONS

    def is_inside(self) -> bool:
        return self.state not in {VisitorState.OUTSIDE, VisitorState.EXITED}

    def is_in_billing(self) -> bool:
        return self.state == VisitorState.IN_BILLING

    def __repr__(self) -> str:
        return f"VisitorStateMachine(id={self.visitor_id!r}, state={self.state.name})"
