"""
pos/correlator.py – POS ↔ visitor session correlation (v2).

Matches POS transactions to visitor sessions using exit-time proximity.
Unlike v1, this correlator:

  • Uses ``POSTransaction`` objects (with brand-level line items)
  • Sets ``session.brands_purchased`` for correct brand conversion
  • Correct attribution: brand_conversion = visited_brand ∩ purchased_brand

Usage
-----
    from src.pos.correlator import POSCorrelatorV2
    from src.pos.parser import parse_pos_csv

    txns = parse_pos_csv("data/pos_transactions.csv", store_id="ST1008")
    correlator = POSCorrelatorV2(txns, store_id="ST1008")
    matched = correlator.correlate(session_manager)
"""

from __future__ import annotations

import os
from typing import Any

from .parser import POSTransaction


POS_MATCH_WINDOW = float(os.environ.get("POS_MATCH_WINDOW", "300"))  # ±5 min


class POSCorrelatorV2:
    """
    Matches POS transactions to closed visitor sessions.

    After correlation, each matched session has:
      - session.converted = True
      - session.purchase_amount = total transaction amount
      - session.brands_purchased = brands from the POS receipt
    """

    def __init__(
        self,
        transactions: list[POSTransaction],
        store_id: str,
        match_window: float = POS_MATCH_WINDOW,
    ) -> None:
        self.store_id = store_id
        self.match_window = match_window
        self._transactions = list(transactions)  # copy
        self._matched: list[tuple[str, POSTransaction]] = []  # (visitor_id, txn)

    def correlate(self, session_manager: Any) -> int:
        """
        Match unmatched POS transactions to closed visitor sessions.

        For each closed customer session (non-staff) with an exit_time,
        find the closest POS transaction within ±match_window seconds.

        Returns
        -------
        int : number of newly matched transactions
        """
        matched_txn_ids: set[str] = {
            txn.invoice_number for _, txn in self._matched
        }
        matched_count = 0

        for session in session_manager.customer_sessions():
            if session.converted or session.exit_time is None:
                continue

            best_txn: POSTransaction | None = None
            best_delta = float("inf")

            for txn in self._transactions:
                if txn.invoice_number in matched_txn_ids:
                    continue

                delta = abs(txn.epoch - session.exit_time)
                if delta <= self.match_window and delta < best_delta:
                    best_delta = delta
                    best_txn = txn

            if best_txn is None:
                continue

            # Mark matched
            matched_txn_ids.add(best_txn.invoice_number)
            self._matched.append((session.visitor_id, best_txn))

            # Update session
            session.converted = True
            session.purchase_amount = best_txn.total_amount

            # Set brands_purchased from POS line items
            session.brands_purchased = sorted(best_txn.brands)

            # Also update via session_manager API
            session_manager.mark_purchased(
                session.visitor_id,
                amount=best_txn.total_amount,
            )

            matched_count += 1

        return matched_count

    def matched_transactions(self) -> list[tuple[str, POSTransaction]]:
        """Return list of (visitor_id, POSTransaction) pairs."""
        return list(self._matched)

    def unmatched_transactions(self) -> list[POSTransaction]:
        """Return POS transactions not yet matched to any visitor."""
        matched_ids = {txn.invoice_number for _, txn in self._matched}
        return [t for t in self._transactions if t.invoice_number not in matched_ids]

    def brand_conversion_stats(
        self,
        session_manager: Any,
    ) -> dict[str, dict[str, int]]:
        """
        Compute correct brand conversion: visited_brand ∩ purchased_brand.

        Returns
        -------
        dict[brand_zone_id, {"visitors": N, "buyers": N, "conversion_pct": float}]
        """
        brand_visitors: dict[str, set[str]] = {}   # zone_id → visitor_ids
        brand_buyers: dict[str, set[str]] = {}     # zone_id → visitor_ids who bought that brand

        from src.layout.parser import load_store_config
        from src.config import STORE_CONFIG_PATH
        config = load_store_config(STORE_CONFIG_PATH, self.store_id)
        brand_map = config.zone_brand_map() if config else {}

        for session in session_manager.customer_sessions():
            visited = getattr(session, "visited_brands", [])
            purchased = set(getattr(session, "brands_purchased", []))

            for zone_id in visited:
                brand_visitors.setdefault(zone_id, set()).add(session.visitor_id)

                # Correct attribution: visitor must have purchased the SAME brand (case/naming robust)
                brand_name = brand_map.get(zone_id) or zone_id
                matched_purchase = False
                for p in purchased:
                    if p.upper() == brand_name.upper() or p.replace(" ", "").upper() == brand_name.replace("_", "").upper():
                        matched_purchase = True
                        break

                if matched_purchase:
                    brand_buyers.setdefault(zone_id, set()).add(session.visitor_id)

        result = {}
        for zone_id in sorted(brand_visitors.keys()):
            visitors = len(brand_visitors[zone_id])
            buyers = len(brand_buyers.get(zone_id, set()))
            result[zone_id] = {
                "visitors": visitors,
                "buyers": buyers,
                "conversion_pct": round(
                    (buyers / visitors * 100) if visitors > 0 else 0.0, 1
                ),
            }

        return result

    def journey_paths(
        self,
        session_manager: Any,
        top_n: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Extract top-N most common customer journey paths.

        A journey path is the ordered sequence of brand zones visited
        by a customer before exiting.

        Returns
        -------
        list of {"path": ["LAKME", "FACES_CANADA", "CASH_COUNTER"], "count": N}
        """
        from collections import Counter

        path_counter: Counter[tuple[str, ...]] = Counter()

        for session in session_manager.customer_sessions():
            visited = getattr(session, "visited_brands", [])
            if visited:
                path_counter[tuple(visited)] += 1

        top_paths = path_counter.most_common(top_n)
        return [
            {"path": list(path), "count": count}
            for path, count in top_paths
        ]

    def correlation_summary(self) -> dict[str, Any]:
        """Summary stats for evaluation reports (computed, never hardcoded)."""
        total = len(self._transactions)
        matched = len(self._matched)
        return {
            "total_transactions": total,
            "matched": matched,
            "unmatched": total - matched,
            "match_rate_pct": round(
                (matched / total * 100) if total > 0 else 0.0, 1
            ),
            "total_revenue_matched": round(
                sum(txn.total_amount for _, txn in self._matched), 2
            ),
        }
