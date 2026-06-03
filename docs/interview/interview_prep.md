# Interview Preparation & Demo Guide

This guide is designed to prepare you for the technical evaluation and interview rounds for the Store Intelligence Platform. It contains the core metrics, the demo structure, and answers to challenging technical questions.

---

## 1. The 15 Critical Numbers (Cheat Sheet)

You should know these numbers by heart. They are sourced directly from the final validation runs and reports:

### Computer Vision & System Performance
*   **3.8 FPS**: Average pipeline processing speed (including YOLOv8s detection, ByteTrack tracking, and OSNet ReID) on CPU.
*   **476.7 MB**: Peak RAM consumption of the pipeline process during execution.
*   **16.3 ms**: Average ingestion latency of a single event `POST` request to the FastAPI endpoint.
*   **82 tests**: The total count of unit and integration tests passing in the test suite.
*   **80.71%**: The exact test coverage achieved (exceeding the 80.0% coverage gate).

### cross-Camera ReID Calibration
*   **0.75**: The selected operating cosine similarity threshold for cross-camera ReID matching.
*   **0.55**: The new ID threshold below which a track is guaranteed to be treated as a new visitor.
*   **95.3%**: The precision achieved at the `0.75` threshold (prioritized to prevent false identity merges).
*   **82.0%**: The recall achieved at the `0.75` threshold.
*   **4.0%**: The False Merge Rate (FMR) at the `0.75` threshold.

### Validation Mode 1 — Real CCTV Validation (Brigade Road)
*   **131**: Unique customer visitors tracked across all 5 cameras.
*   **326**: Structured business events generated and ingested.
*   **54**: Unique visitors who engaged with at least one brand zone (41.2% zone engagement rate).
*   **0**: POS matches & Billing queue visitors (expected due to camera occlusion at the counter and the date/timestamp gap between the real footage and POS CSV).

### Validation Mode 2 — End-to-End Business Demo
*   **40**: Simulated customer sessions processed.
*   **21 / 24**: POS transactions successfully correlated within the `±5 minute` window (87.5% Match Rate).
*   **₹31,269.76**: Total revenue successfully matched and attributed to customer journeys.
*   **52.5%**: Funnel conversion rate (21 purchases out of 40 sessions).
*   **7.7%**: Billing queue abandonment rate.

---

## 2. The 10-Minute Demo Flow

When presenting the platform, stick to this structured sequence to show both engineering depth and business impact:

*   **Minute 1: Problem Statement**
    *   Explain the retail "black box" problem: physical stores lack the behavioral funnel visibility (entry → zone engagement → billing drop-off → purchase) that e-commerce sites take for granted.
*   **Minute 2: Core Architecture Overview**
    *   Walk through the unified stream: `Security Video (CCTV) → YOLOv8s & ByteTrack → OSNet ReID Gallery → 6-State FSM → POS Correlator V2 → FastAPI & Streamlit`.
*   **Minute 3: Store Layout Integration**
    *   Detail how normalized layout zone coordinates are mapped from `store_config.json` and scaled to camera dimensions via Shapely polygons for pixel-perfect brand zone assignment.
*   **Minute 4: Event Schema & Emission**
    *   Describe the unified event contract (`visitor_id`, `event_type`, `timestamp`, `zone_id`, `confidence`). Emphasize that coordinates are processed at the edge, emitting lightweight metadata (no PII).
*   **Minute 5: Session Manager & Staff Filtering Heuristic**
    *   Explain how customer sessions are managed. Present the 4-rule staff scoring heuristic (pre-open arrival, presence ratio, long dwell, HSV uniform color) used to filter employees from business metrics.
*   **Minute 6: POS Correlation Engine**
    *   Explain how the correlator attributes receipts to exit times within a ±5-minute window, resolves multiple exit overlaps using brand visited overlap matching, and calculates matched revenue.
*   **Minute 7: Validation Evidence (The Two Modes)**
    *   Defend the validation setup: Mode 1 (Real CCTV) proves the CV and tracking stack on uncontrolled footage. Mode 2 (Business Demo) proves the POS correlation and funnel analytics when timestamps are aligned.
*   **Minute 8: Failure Analysis & Edge Cases**
    *   Be transparent: detail how occlusions, lighting-induced ReID failures, and POS timestamp drift are mitigated (Kalman state persistence, `uncertain_reid` flags, sliding window parameters).
*   **Minute 9: Live Dashboard walkthrough**
    *   Showcase the Streamlit UI: metrics cards, Plotly funnel chart, engagement scores bar chart, and the live operational anomaly alert panel.
*   **Minute 10: Limitations & Future Roadmap**
    *   Outline the production roadmap: integrating clothing color histograms in ReID, gaze/face direction shelf mapping, and POS interval trees scaling.

---

## 3. Tough Interview Q&A Corner

### Q: Why is your ReID validation dataset size only 100 pairs?
**Answer**: "The objective of the ReID validation sweep was not to train or fine-tune an appearance model, but rather to establish the optimal threshold selection for an off-the-shelf pre-trained model (OSNet_x0_25). The 100 manually verified pairs (50 positive, 50 negative) extracted from real store footage were sufficient to compare candidate thresholds and identify an operating point (`0.75`) that prioritizes high precision (95.3%) to prevent false merges, which would otherwise corrupt visitor session analytics."

### Q: Why didn't you train or fine-tune a custom YOLO model?
**Answer**: "Fine-tuning YOLO on our specific dataset carried a high risk of overfitting due to the relatively small number of video clips available. Additionally, the pre-trained YOLOv8s model generalizes exceptionally well to person detection in retail environments out of the box. We determined that the highest engineering return on investment for this hackathon lay in building robust logic around layout mapping, ReID handover, FSM session tracking, and POS correlation rather than spending resources on custom detector training."

### Q: How does the system handle temporary tracking loss or occlusions?
**Answer**: "We handle occlusions in two layers. The tracking layer (ByteTrack) maintains Kalman filter state trajectories for up to 30 frames when a bounding box disappears. The pipeline layer (TrackLifecycleManager) manages track expiration: if a track is lost and does not reappear within 5 seconds, it is expired. If it was last seen near an exit boundary, we emit an `EXIT` event; if lost in the middle of the store, it is expired silently after 60 seconds, preventing phantom exits from inflating metrics."
