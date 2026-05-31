"""
tests/test_pipeline_integration.py – Integration tests to cover pipeline components.
"""

import json
from pathlib import Path
import numpy as np
import pytest
from src.scanner import scan, _discover_camera_store, _validate_video
from src.pos_correlator import POSCorrelator
from src.reid import OSNetReID
from src.session_manager import SessionManager, VisitorSession
from src.event_emitter import EventEmitter
from src.tracker_lifecycle import TrackStateInfo
from src.config import REID_MATCH_THRESHOLD


def test_scanner_discovery(tmp_path):
    # Create mock layout
    layout = {
        "stores": {
            "S1": {
                "cameras": [
                    {"camera_id": "CAM1", "video_file": "cam1_test.mp4"}
                ]
            }
        }
    }
    
    # 1. Test layout mapping
    store_id, camera_id, warn = _discover_camera_store(
        Path("cam1_test.mp4"), layout
    )
    assert store_id == "S1"
    assert camera_id == "CAM1"
    assert warn is None

    # 2. Test filename fallback mapping
    store_id, camera_id, warn = _discover_camera_store(
        Path("S2_CAM2.avi"), layout
    )
    assert store_id == "S2"
    assert camera_id == "CAM2"
    assert warn is None

    # 3. Test metadata heuristics fallback
    store_id, camera_id, warn = _discover_camera_store(
        Path("unknown_file.mov"), layout, width=1920
    )
    assert store_id == "S1"
    assert camera_id == "CAM3"  # CAM3 is guessed for width >= 1920
    assert warn is not None


def test_pos_correlator_matching(tmp_path):
    # Write mock POS csv
    csv_path = tmp_path / "pos_transactions.csv"
    csv_path.write_text("txn_id,store_id,timestamp,amount\ntxn_1,S1,2026-05-30T06:45:00Z,150.0\n")
    
    correlator = POSCorrelator(csv_path, store_id="S1")
    assert len(correlator.df) == 1
    
    session_mgr = SessionManager(store_id="S1")
    # Open and close session near 12:05:00 (timestamp epoch 1780123500.0)
    t = 1780123500.0
    session_mgr.open_session("V100", "CAM1", t - 60)
    session_mgr.close_session("V100", t)
    
    matched = correlator.correlate(session_mgr)
    assert matched == 1
    assert session_mgr._history[0].converted is True
    assert session_mgr._history[0].purchase_amount == 150.0


def test_reid_gallery():
    reid = OSNetReID()
    reid.reset()
    assert reid.gallery_size() == 0
    
    # Create fake crop (100x100 BGR)
    crop = np.zeros((100, 100, 3), dtype=np.uint8)
    vid, uncertain = reid.identify(crop, frame_index=0)
    
    assert isinstance(vid, str)
    assert len(vid) > 0
    assert reid.gallery_size() == 1


def test_event_emitter_logic():
    layout = {
        "stores": {
            "S1": {
                "zones": [
                    {"zone_id": "SKINCARE", "polygon": [[20, 20], [100, 20], [100, 100], [20, 100]]},
                    {"zone_id": "BILLING", "polygon": [[200, 200], [300, 200], [300, 300], [200, 300]]}
                ],
                "cameras": [
                    {"camera_id": "CAM1", "entry_line": [[10, 10], [50, 10]], "exit_line": [[10, 80], [50, 80]]}
                ]
            }
        }
    }
    
    session_mgr = SessionManager(store_id="S1")
    reid = OSNetReID()
    
    emitter = EventEmitter(
        store_id="S1",
        camera_id="CAM1",
        store_layout=layout,
        session_manager=session_mgr,
        reid_gallery=reid,
        fps=30.0,
    )
    
    # Create a mock active track info
    info = TrackStateInfo(
        track_id=1,
        xyxy=np.array([10, 0, 20, 10]),  # center will be (15, 5)
        confidence=0.9,
        first_seen_time=1.0,
        last_seen_time=1.0
    )
    info.visitor_id = "V_TEST"
    
    # Frame 0: Crosses entry line
    # entry line is [[10, 10], [50, 10]]. Move from y=5 to y=15 (crosses line)
    info.prev_entry_side = -1.0
    info.xyxy = np.array([10, 10, 20, 20])  # center (15, 15)
    
    events = emitter.process_frame(None, [info], frame_idx=0)
    assert len(events) == 1
    assert events[0].event_type == "ENTRY"
    
    # Frame 1: Enters SKINCARE zone
    info.xyxy = np.array([30, 30, 40, 40])  # center (35, 35) - inside SKINCARE
    events = emitter.process_frame(None, [info], frame_idx=1)
    assert len(events) == 1
    assert events[0].event_type == "ZONE_ENTER"
    assert events[0].zone_id == "SKINCARE"
