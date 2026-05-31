"""
tests/test_pos.py – Unit tests for POS parsing and correlation.
"""

import json
from pathlib import Path
import pytest
from datetime import datetime, timezone
from src.pos.parser import parse_pos_csv, get_pos_summary
from src.pos.correlator import POSCorrelatorV2
from src.session_manager import SessionManager, VisitorSession


def test_pos_parser_real_format(tmp_path):
    csv_content = (
        "order_id,invoice_number,order_date,order_time,store_id,store_name,customer_name,brand_name,product_name,qty,total_amount\n"
        "1001,INV1,10-04-2026,16:55:36,ST1008,Brigade,Guest,Lakme,lipstick,1,150.0\n"
        "1001,INV1,10-04-2026,16:55:36,ST1008,Brigade,Guest,Faces Canada,compact,2,300.0\n"
    )
    csv_file = tmp_path / "pos_transactions.csv"
    csv_file.write_text(csv_content)
    
    txns = parse_pos_csv(csv_file, "ST1008")
    assert len(txns) == 1
    txn = txns[0]
    assert txn.invoice_number == "INV1"
    assert txn.store_id == "ST1008"
    assert txn.total_amount == 450.0
    assert txn.total_qty == 3
    assert txn.brands == {"Lakme", "Faces Canada"}
    
    summary = get_pos_summary(txns)
    assert summary["count"] == 1
    assert summary["total_revenue"] == 450.0
    assert summary["brands"] == ["Faces Canada", "Lakme"]


def test_pos_correlator_brand_conversion(tmp_path):
    # Mock transactions
    csv_content = (
        "order_id,invoice_number,order_date,order_time,store_id,store_name,customer_name,brand_name,product_name,qty,total_amount\n"
        "1001,INV1,10-04-2026,12:00:00,ST1008,Brigade,Guest,Lakme,lipstick,1,150.0\n"
    )
    csv_file = tmp_path / "pos_transactions.csv"
    csv_file.write_text(csv_content)
    
    txns = parse_pos_csv(csv_file, "ST1008")
    
    session_mgr = SessionManager(store_id="ST1008")
    t = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc).timestamp()
    
    # Session 1: Visited Lakme and bought Lakme
    s1 = session_mgr.open_session("V101", "CAM1", t - 60)
    s1.visited_brands = ["LAKME"]
    session_mgr.close_session("V101", t)
    
    correlator = POSCorrelatorV2(txns, store_id="ST1008", match_window=300)
    matched = correlator.correlate(session_mgr)
    
    assert matched == 1
    assert s1.converted is True
    assert s1.brands_purchased == ["Lakme"]
    
    # Check brand conversion stats
    stats = correlator.brand_conversion_stats(session_mgr)
    # LAKME should have 1 visitor and 1 buyer
    assert "LAKME" in stats
    assert stats["LAKME"]["visitors"] == 1
    assert stats["LAKME"]["buyers"] == 1
    assert stats["LAKME"]["conversion_pct"] == 100.0
    
    # Check journey paths
    paths = correlator.journey_paths(session_mgr)
    assert len(paths) == 1
    assert paths[0]["path"] == ["LAKME"]
    assert paths[0]["count"] == 1
    
    # Correlation summary
    summary = correlator.correlation_summary()
    assert summary["total_transactions"] == 1
    assert summary["matched"] == 1
    assert summary["unmatched"] == 0
    assert summary["total_revenue_matched"] == 150.0
