"""
tests/test_tracker_lifecycle.py – Unit tests for TrackLifecycleManager.
"""

import numpy as np
import pytest
from src.tracker import Track
from src.tracker_lifecycle import TrackLifecycleManager, TrackLifecycleState


def test_lifecycle_basic_transitions():
    mgr = TrackLifecycleManager(lost_timeout=1.0, occlusion_timeout=5.0)
    
    # 1. Add active track
    track = Track(track_id=1, xyxy=np.array([100, 100, 150, 150]), confidence=0.9, age=2, is_confirmed=True)
    active, signals = mgr.update([track], frame_time=1.0, frame_width=1000, frame_height=1000)
    
    assert len(active) == 1
    assert active[0].track_id == 1
    assert active[0].state == TrackLifecycleState.ACTIVE
    assert len(signals) == 0

    # 2. Track goes missing -> state should become LOST
    active, signals = mgr.update([], frame_time=1.5, frame_width=1000, frame_height=1000)
    assert len(active) == 0
    assert len(signals) == 0
    
    info = mgr.tracks_db[1]
    assert info.state == TrackLifecycleState.LOST
    assert info.lost_since_time == 1.5

    # 3. Track reappears -> state should become ACTIVE/RECOVERED
    active, signals = mgr.update([track], frame_time=2.0, frame_width=1000, frame_height=1000)
    assert len(active) == 1
    assert len(signals) == 1
    assert signals[0][1] == "RECOVERED"
    assert active[0].state == TrackLifecycleState.ACTIVE


def test_lifecycle_exit_expiration():
    # Place exit line at y = 950
    exit_line = [[0, 950], [1000, 950]]
    mgr = TrackLifecycleManager(exit_line=exit_line, lost_timeout=1.0, occlusion_timeout=5.0)
    
    # Track near exit line (y coordinate is 940)
    track = Track(track_id=1, xyxy=np.array([500, 930, 520, 950]), confidence=0.9, age=2, is_confirmed=True)
    mgr.update([track], frame_time=1.0, frame_width=1000, frame_height=1000)
    
    # Track disappears -> LOST
    mgr.update([], frame_time=1.5, frame_width=1000, frame_height=1000)
    
    # Track stays missing past lost_timeout (1.0s) -> 1.5 + 1.1 = 2.6
    # It should expire and signal EXIT because it is near the exit line
    active, signals = mgr.update([], frame_time=2.6, frame_width=1000, frame_height=1000)
    
    assert len(active) == 0
    assert len(signals) == 1
    assert signals[0][1] == "EXIT"
    assert 1 not in mgr.tracks_db


def test_lifecycle_occlusion_expiration():
    # Place exit line far away
    exit_line = [[0, 950], [1000, 950]]
    mgr = TrackLifecycleManager(exit_line=exit_line, lost_timeout=1.0, occlusion_timeout=5.0)
    
    # Track far from boundary (in center of frame 500, 500)
    track = Track(track_id=1, xyxy=np.array([490, 490, 510, 510]), confidence=0.9, age=2, is_confirmed=True)
    mgr.update([track], frame_time=1.0, frame_width=1000, frame_height=1000)
    
    # Track disappears -> LOST
    mgr.update([], frame_time=1.5, frame_width=1000, frame_height=1000)
    
    # Past lost_timeout (1.0s) -> should NOT trigger exit because it is not near any boundary
    active, signals = mgr.update([], frame_time=2.6, frame_width=1000, frame_height=1000)
    assert len(signals) == 0
    assert mgr.tracks_db[1].state == TrackLifecycleState.LOST
    
    # Past occlusion_timeout (5.0s) -> 1.5 + 5.1 = 6.6
    # Should expire silently (EXPIRED_SILENT)
    active, signals = mgr.update([], frame_time=6.6, frame_width=1000, frame_height=1000)
    assert len(signals) == 1
    assert signals[0][1] == "EXPIRED_SILENT"
    assert 1 not in mgr.tracks_db
