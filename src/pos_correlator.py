"""
pos_correlator.py – POS transaction ↔ visitor session correlation (Legacy wrapper).

This is a backward-compatibility wrapper that delegates to src/pos/parser.py
and src/pos/correlator.py.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd
from .pos.parser import parse_pos_csv
from .pos.correlator import POSCorrelatorV2


class POSCorrelator:
    """
    Loads and correlates POS transactions for a single store (Backward compatibility wrapper).
    """

    def __init__(self, pos_csv_path: str | Path, store_id: str) -> None:
        self.store_id = store_id
        self.transactions = parse_pos_csv(pos_csv_path, store_id=store_id)
        self.v2 = POSCorrelatorV2(self.transactions, store_id=store_id)

        # Build _df for legacy compatibility (e.g. testing accessing correlator.df)
        rows = []
        for txn in self.transactions:
            rows.append({
                "txn_id": txn.invoice_number,
                "store_id": txn.store_id,
                "timestamp": txn.timestamp,
                "amount": txn.total_amount,
                "_ts_epoch": txn.epoch,
                "_matched": False,
                "_visitor_id": None,
            })
        if rows:
            self._df = pd.DataFrame(rows)
        else:
            self._df = pd.DataFrame(columns=["txn_id", "store_id", "timestamp", "amount", "_ts_epoch", "_matched", "_visitor_id"])

    @property
    def df(self) -> pd.DataFrame:
        return self._df

    def correlate(self, session_manager: Any) -> int:
        count = self.v2.correlate(session_manager)

        # Update self._df based on v2 matched status to keep legacy tests happy
        matched_map = {visitor_id: txn.invoice_number for visitor_id, txn in self.v2.matched_transactions()}
        for i, row in self._df.iterrows():
            txn_id = row["txn_id"]
            for vid, tid in matched_map.items():
                if tid == txn_id:
                    self._df.at[i, "_matched"] = True
                    self._df.at[i, "_visitor_id"] = vid
                    break
        return count

    def matched_transactions(self) -> pd.DataFrame:
        return self._df[self._df["_matched"]].copy()

    def unmatched_transactions(self) -> pd.DataFrame:
        return self._df[~self._df["_matched"]].copy()
