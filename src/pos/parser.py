"""
pos/parser.py – POS transaction CSV parser.

Handles both the *real* Brigade Bangalore POS CSV (39 columns,
``order_date`` + ``order_time``) and the generic format used in
previous pipeline versions (``timestamp`` + ``store_id``).

Groups line-items by ``invoice_number`` into ``POSTransaction``
objects so a single checkout visit maps to one transaction with
multiple ``POSLineItem`` entries.

Usage
-----
    from src.pos.parser import parse_pos_csv
    transactions = parse_pos_csv("data/pos_transactions.csv", store_id="ST1008")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


# ──────────────────────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class POSLineItem:
    """A single product line within a POS transaction."""
    brand_name: str
    product_name: str
    sub_category: str
    qty: int
    amount: float           # total_amount for this line

    def __repr__(self) -> str:
        return f"LineItem({self.brand_name!r}, qty={self.qty}, amt={self.amount:.2f})"


@dataclass
class POSTransaction:
    """
    One checkout transaction (may contain multiple line items / brands).
    Keyed by ``invoice_number``.
    """
    invoice_number: str
    order_id: str
    store_id: str
    store_name: str
    timestamp: datetime       # UTC datetime of the transaction
    customer_name: str
    items: list[POSLineItem] = field(default_factory=list)

    # Computed properties
    @property
    def total_amount(self) -> float:
        return sum(item.amount for item in self.items)

    @property
    def total_qty(self) -> int:
        return sum(item.qty for item in self.items)

    @property
    def brands(self) -> set[str]:
        """Unique brand names purchased in this transaction."""
        return {item.brand_name for item in self.items if item.brand_name}

    @property
    def epoch(self) -> float:
        """Unix epoch seconds."""
        return self.timestamp.timestamp()

    def __repr__(self) -> str:
        return (
            f"POSTxn({self.invoice_number}, "
            f"{self.timestamp.strftime('%H:%M:%S')}, "
            f"items={len(self.items)}, "
            f"amt={self.total_amount:.2f}, "
            f"brands={self.brands})"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Parsers
# ──────────────────────────────────────────────────────────────────────────────

def _detect_csv_format(df: pd.DataFrame) -> str:
    """Detect whether this is the 'real' or 'generic' POS CSV format."""
    cols = set(df.columns)
    if "order_date" in cols and "order_time" in cols:
        return "real"
    if "timestamp" in cols:
        return "generic"
    # Fallback: try to guess
    if "invoice_number" in cols:
        return "real"
    return "generic"


def _parse_real_csv(
    df: pd.DataFrame,
    store_id: str | None = None,
) -> list[POSTransaction]:
    """
    Parse the Brigade Bangalore POS CSV format.

    Columns used: order_id, invoice_number, order_date, order_time,
    store_id, store_name, customer_name, brand_name, product_name,
    sub_category, qty, total_amount
    """
    # Filter by store_id if provided
    if store_id and "store_id" in df.columns:
        df = df[df["store_id"].astype(str).str.upper() == store_id.upper()].copy()

    if df.empty:
        return []

    # Combine date + time → datetime
    df["_datetime"] = pd.to_datetime(
        df["order_date"].astype(str) + " " + df["order_time"].astype(str),
        format="mixed",
        dayfirst=True,
        utc=True,
        errors="coerce",
    )
    df = df.dropna(subset=["_datetime"])

    # Group by invoice_number
    transactions: list[POSTransaction] = []
    grouped = df.groupby("invoice_number", sort=False)

    for invoice_num, group in grouped:
        first = group.iloc[0]
        items: list[POSLineItem] = []

        for _, row in group.iterrows():
            items.append(POSLineItem(
                brand_name=str(row.get("brand_name", "")).strip(),
                product_name=str(row.get("product_name", "")).strip(),
                sub_category=str(row.get("sub_category", "")).strip(),
                qty=int(row.get("qty", 1)),
                amount=float(row.get("total_amount", 0.0)),
            ))

        transactions.append(POSTransaction(
            invoice_number=str(invoice_num),
            order_id=str(first.get("order_id", "")),
            store_id=str(first.get("store_id", store_id or "")),
            store_name=str(first.get("store_name", "")),
            timestamp=first["_datetime"].to_pydatetime(),
            customer_name=str(first.get("customer_name", "Guest")),
            items=items,
        ))

    # Sort by timestamp
    transactions.sort(key=lambda t: t.epoch)
    return transactions


def _parse_generic_csv(
    df: pd.DataFrame,
    store_id: str | None = None,
) -> list[POSTransaction]:
    """
    Parse the generic POS CSV format (columns: timestamp, store_id, amount).
    Backward-compatible with the old pos_correlator.py expectations.
    """
    if "timestamp" not in df.columns:
        return []

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"])

    if store_id and "store_id" in df.columns:
        df = df[df["store_id"].astype(str).str.upper() == store_id.upper()].copy()

    transactions: list[POSTransaction] = []
    for idx, row in df.iterrows():
        txn_id = str(row.get("txn_id", row.get("invoice_number", f"TXN_{idx}")))
        amount = float(row.get("amount", row.get("total_amount", 0.0)))

        items = [POSLineItem(
            brand_name=str(row.get("brand_name", "Unknown")),
            product_name=str(row.get("product_name", "")),
            sub_category=str(row.get("sub_category", "")),
            qty=int(row.get("qty", 1)),
            amount=amount,
        )]

        transactions.append(POSTransaction(
            invoice_number=txn_id,
            order_id=str(row.get("order_id", txn_id)),
            store_id=str(row.get("store_id", store_id or "")),
            store_name=str(row.get("store_name", "")),
            timestamp=row["timestamp"].to_pydatetime(),
            customer_name=str(row.get("customer_name", "Guest")),
            items=items,
        ))

    transactions.sort(key=lambda t: t.epoch)
    return transactions


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def parse_pos_csv(
    csv_path: str | Path,
    store_id: str | None = None,
) -> list[POSTransaction]:
    """
    Load and parse a POS CSV file.  Auto-detects the format.

    Parameters
    ----------
    csv_path : path to the CSV file
    store_id : optional store filter (e.g. "ST1008")

    Returns
    -------
    list[POSTransaction] sorted by timestamp
    """
    path = Path(csv_path)
    if not path.exists():
        return []

    df = pd.read_csv(path)
    fmt = _detect_csv_format(df)

    if fmt == "real":
        return _parse_real_csv(df, store_id)
    else:
        return _parse_generic_csv(df, store_id)


def get_pos_summary(transactions: list[POSTransaction]) -> dict[str, Any]:
    """Quick summary stats for validation reports (never hardcoded)."""
    if not transactions:
        return {"count": 0, "total_revenue": 0.0, "brands": [], "time_range": ""}

    brands: set[str] = set()
    for t in transactions:
        brands.update(t.brands)

    return {
        "count": len(transactions),
        "total_revenue": round(sum(t.total_amount for t in transactions), 2),
        "total_items": sum(t.total_qty for t in transactions),
        "brands": sorted(brands),
        "time_range": (
            f"{transactions[0].timestamp.strftime('%H:%M:%S')} - "
            f"{transactions[-1].timestamp.strftime('%H:%M:%S')}"
        ),
        "unique_customers": len({t.customer_name for t in transactions}),
    }
