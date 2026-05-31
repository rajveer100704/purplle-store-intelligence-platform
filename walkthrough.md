# CCTV Store Intelligence Platform — Walkthrough

We have successfully upgraded and hardened the CCTV Store Intelligence Platform into a **resource-driven Retail Intelligence System**. The platform is now fully validated, documented, and packaged for reviewer submission.

---

## 1. Physical Layout Integration (`src/layout/`)

The store layout maps raw camera pixels to semantic retail zones:

- **`src/layout/store_config.json`**: Acts as a semantic zone registry mapping 20 brands (e.g., Lakme, Faces Canada, Minimalist, Good Vibes) to normalized polygon coordinates.
- **`src/layout/parser.py`**:
  - Defines the `StoreConfig` and `CameraConfig` dataclasses.
  - Implements `load_store_config` to read the layout JSON and construct Shapely `Polygon` structures.
  - Dynamically scales normalized coordinate polygons to the actual camera resolution (`frame_size`).
- **`tools/zone_calibrator.py`**: An interactive OpenCV calibrator that allows drawing zone boundaries on video frames, with a robust grid-fallback mechanism mapping brands to top/bottom layout walls.

---

## 2. POS Transaction & Conversion Layer (`src/pos/`)

Rather than guessing conversions, real transaction logs serve as the ground truth for purchase behavior:

- **`src/pos/parser.py`**:
  - Automatically detects the CSV format (legacy single-timestamp vs. real multi-column POS containing `order_date`, `order_time`, `invoice_number`, `total_amount`).
  - Groups items by `invoice_number` to reconstruct multi-item transactions.
- **`src/pos/correlator.py`**:
  - Matches visitor exit times with transaction timestamps within a sliding `±5 minute` window.
  - Implements the corrected brand conversion logic:
    $$\text{brand\_conversion} = \text{visited\_brands} \cap \text{brands\_purchased}$$
  - Computes conversion rates and customer journey paths.

---

## 3. End-to-End Pipeline & API Enhancements

- **`src/pipeline.py` & `src/scanner.py`**: Auto-discover `store_config.json` and POS files.
- **`src/session_manager.py`**: Tracks visited and purchased brands per session and filters out store personnel using a 4-rule staff scoring heuristic.
- **`src/event_emitter.py`**: Uses brand names as zone IDs (`LAKME`, `FACES_CANADA`) instead of generic labels (`ZONE_4`).
- **`src/anomaly_engine.py`**: Generates operational alerts utilizing brand names (e.g., `"DEAD_ZONE: Zone 'Minimalist' has had no visitors for 60 min"`).
- **FastAPI REST API**:
  - **`GET /heatmap`**: Returns visits, average dwell, and brand metadata.
  - **`GET /funnel`**: Includes actual POS purchase as the final stage (Entry → Zone Visit → Billing → POS Purchase).
  - **`GET /metrics`**: Serves footfall, conversion rate, matched transactions, total matched POS revenue, and brand-level conversion percentages.

---

## 4. Verification & Testing

### Automated Tests
The test suite covers parsing, scaling, correlation, and API responses:
- **82 tests passed successfully** with **80.71%** coverage, exceeding the required 80% threshold.

### E2E Simulation (Mode 2 - Business Demo)
The validation script **`scripts/generate_demo.py`** successfully processed simulated visitor events and POS records, generating the validation report at `demo/demo_summary.md`:
- **Footfall**: 40 unique visitors
- **Total Transactions Matched**: 21 / 24 POS transactions (87.5% Match Rate)
- **Matched Revenue**: Rs. 31,269.76
- **Funnel Conversion Rate**: 52.5% (21/40 sessions)
- **Billing Queue Abandonment**: 7.7%
- **Operational Alerts**: Dead zone detected for Minimalist shelf (66 minutes without activity).

### Real CCTV Video Validation (Mode 1 - Real CCTV Run)
The validator **`scripts/generate_real_validation.py`** parsed the 326 events from the 5-camera CCTV footage (Brigade Road) to verify the CV and tracking stack:
- **Footfall**: 131 unique visitors
- **Zone engagement**: 14 visitors (10.7%) entered a brand zone
- **Billing queue visitors**: 0 (due to camera angle constraints at the counter)
- **POS matched purchases**: 0 (expected due to timestamp gap between 2026-04-10 POS logs and 2026-05-30 video run)
- Full details in `submission/data_provenance.md` and `submission/real_run_report.md`.

### Performance & Benchmarking
The script **`scripts/benchmark.py`** measured pipeline metrics on the target environment:
- **Average FPS**: 3.8 frames/sec (YOLOv8s + ByteTrack + ReID fallback on CPU)
- **Peak RAM**: 476.7 MB (Memory Overhead: 260.1 MB)
- **Average Ingestion Latency**: 16.3 ms per single event POST
