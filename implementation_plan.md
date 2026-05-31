# Implementation Plan – Resolution of 10 Critical Flaws (Final Version)

This final plan addresses the 10 architectural weaknesses, incorporating all six requested adjustments from the senior reviewer. These changes guarantee a robust, production-grade, and interview-defensible architecture.

---

## User Review Required

> [!IMPORTANT]
> Key modifications and additions made in this version:
> 1. **Presence-Ratio Staff Rules**: Replaced hardcoded durations with clips-length presence ratios (`camera_presence_ratio = time_on_camera / clip_duration`).
> 2. **ReID Calibration with Labeled Pairs**: Created a systematic calibration dataset in `evaluation/reid_pairs.csv` mapping frame crop pairs to ground truth labels (`same_person` 0/1) to sweep the threshold.
> 3. **Track Lifecycle Ownership Flow**: Set up the pipeline sequence as:
>    `ByteTrack` $\rightarrow$ `TrackLifecycleManager` $\rightarrow$ `ReID` $\rightarrow$ `SessionManager` $\rightarrow$ `EventEmitter`
>    `TrackLifecycleManager` filters out invalid/unconfirmed tracks before ReID computation.
>    `EventEmitter` maps track expiration signals to exits.
> 4. **Improved Queue Inference Geometry**: Fallback queue polygons are computed using the billing centroid and entrance edge, constructing a 25% waiting area at the front.
> 5. **Performance Benchmarking**: Added `evaluation/performance_report.md` detailing average processing FPS, peak RAM, and API latency.
> 6. **Centralized Configuration**: All thresholds and parameters are gathered in `src/config.py`.

---

## Proposed Changes

### Configuration Centralization (`src/config.py`)
- **[NEW] [config.py](file:///c:/Users/BIT/Purplle_Hackathon/src/config.py)**
  - Centralize parameters:
    - `REID_MATCH_THRESHOLD = 0.75`
    - `REID_NEW_ID_THRESHOLD = 0.50`
    - `TRACK_LOST_TIMEOUT = 5.0`
    - `OCCLUSION_TIMEOUT = 60.0`
    - `QUEUE_SPIKE_SIGMA = 2.0`
    - `CONVERSION_DROP_PCT = 15.0`
    - `DEAD_ZONE_MINUTES = 60.0`
    - `STAFF_SCORE_THRESHOLD = 3`
    - `STAFF_HUE_RANGE = (100, 140)`
    - `STAFF_PRESENCE_RATIO_SINGLE = 0.70`
    - `STAFF_PRESENCE_RATIO_MULTI = 0.20`

### Component 1: Visitor State Machine (`src/state_machine.py`)
- **[MODIFY]** Remove the `PURCHASED` state from `VisitorState` and transition rules for `pos_matched`.
- **[MODIFY]** Update transitions to keep it purely mapping real-time tracking locations.

### Component 2: Session Manager & Staff Heuristic (`src/session_manager.py`)
- **[MODIFY]** Add `converted: bool = False`, `purchase_amount: float | None = None`, and `camera_durations: dict[str, float] = {}` to `VisitorSession`.
- **[MODIFY]** Implement ratio-based staff rules in `_score_staff(session, clip_duration)`:
  - `presence_ratio = time_on_camera / clip_duration`
  - Spent $> 70\%$ of the clip on any single camera $\rightarrow$ +2 points.
  - Spent $> 20\%$ of the clip on $\ge 2$ cameras $\rightarrow$ +2 points.
  - Presence ratio in total video frames $> 30\%$ $\rightarrow$ +2 points.
  - Pre-opening entry $\rightarrow$ +2 points, uniform hue $\rightarrow$ +1 point.

### Component 3: ReID Threshold Calibration (`scripts/calibrate_reid.py` & `evaluation/reid_pairs.csv`)
- **[NEW] [reid_pairs.csv](file:///c:/Users/BIT/Purplle_Hackathon/evaluation/reid_pairs.csv)**
  - Ground truth label pairs (`img1`, `img2`, `same_person` 0/1) for calibration.
- **[NEW] [calibrate_reid.py](file:///c:/Users/BIT/Purplle_Hackathon/scripts/calibrate_reid.py)**
  - Load calibration pairs, run detector & OSNet ReID on CCTV clips to extract real crops, match crops, sweep thresholds (0.50 to 0.90), and output precision/recall logs.

### Component 4: Track Lifecycle Manager (`src/tracker_lifecycle.py` & `src/pipeline.py` & `src/event_emitter.py`)
- **[NEW] [tracker_lifecycle.py](file:///c:/Users/BIT/Purplle_Hackathon/src/tracker_lifecycle.py)**
  - Implement `TrackLifecycleManager` to track `ACTIVE`, `LOST`, `RECOVERED`, and `EXPIRED` status of camera-local tracks.
  - Track validity: check if age >= threshold.
- **[MODIFY]** **Ownership Flow in `src/pipeline.py`**:
  - Receive tracks from `ByteTracker`.
  - Pass through `TrackLifecycleManager` to identify active/expired tracks.
  - For active valid tracks, pass crops to `OSNetReID` to associate with a global `visitor_id`.
  - Feed visitor movements, entries, and exits to `SessionManager` and `EventEmitter`.
- **[MODIFY]** **EventEmitter Exit Logic**:
  - Expired track near the boundary (within 10% of edges or 50px of exit line) triggers a visitor `EXIT` event.
  - Expired track far from the boundary triggers quiet expiration (occlusion handling) without a false exit event.

### Component 5: Robust Queue Inference Geometry (`src/event_emitter.py`)
- **[MODIFY]** Implement `infer_queue_polygon(billing_polygon)`:
  - Locate billing centroid.
  - Locate entrance edge of the billing polygon.
  - Project a 25% area block towards the entrance side to form the inferred queue zone.

### Component 6: Evaluation & Performance Framework (`evaluation/` & `results/` & `scripts/`)
- **[NEW] [performance_report.md](file:///c:/Users/BIT/Purplle_Hackathon/evaluation/performance_report.md)**
  - Table of benchmarking metrics: Avg FPS, Peak RAM, Avg API Latency, Events/sec.
- **[NEW] [benchmark.py](file:///c:/Users/BIT/Purplle_Hackathon/scripts/benchmark.py)**
  - Script to run pipeline on sample clips and log system performance.
- **[NEW] [evaluation_report.md](file:///c:/Users/BIT/Purplle_Hackathon/evaluation/evaluation_report.md)**
  - Manual validation confusion matrix and ground truth annotations.

---

## Verification Plan

### Automated Tests
- Run `pytest tests/ --cov=src` to verify that all unit/integration tests pass.
- Adjust existing tests in `test_session_manager.py` and `test_state_machine.py` to match the updated states and configuration defaults.

### Manual Verification
- Run `python -m src.scanner` on local footage files and verify resilient video matching.
- Run `python scripts/calibrate_reid.py` and inspect the output metrics.
- Run `python scripts/benchmark.py` to compile the performance report.
