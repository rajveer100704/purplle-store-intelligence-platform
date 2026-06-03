# CCTV Store Intelligence Platform — Submission Package

**Team**: Purplle Hackathon 2026
**Store**: Brigade Road, Bangalore (ST1008)
**Submission Date**: 2026-05-31

---

## What This System Does

This platform converts raw CCTV footage from active cameras into **brand-level retail intelligence** — connecting physical visitor behavior to actual POS transactions. 

### Generalization Validation
*   **Store Count**: 3 distinct physical stores
*   **Camera Streams**: 13 total CCTV camera streams
*   **Code Changes Between Stores**: **0** (configured entirely via `StoreRegistry` layout configuration)

**Inputs**:
- 13 CCTV cameras across 3 stores (Brigade Road ST1008, Store 1, Store 2)
- Physical store layout zones (manual brand polygons for ST1008; automatically generated display zones for STORE_1/STORE_2)
- POS transaction CSV (Brigade Road ST1008)

**Outputs**:
- Per-visitor brand zone journeys
- Conversion funnel (Entry → Zone → Billing → Purchase)
- Zone-level heatmaps & alerts
- POS-correlated conversion rate with brand attribution (or queue-based proxy when POS is unavailable)

---

## Quick Start

### 🌐 View Hosted Live Dashboard (No Setup Required)
You can view the fully populated, production-ready dashboard instantly on Streamlit Community Cloud:
👉 **[Live App Link](https://purplle-store-intelligence-platform-auydydswabnuuscjznvlpd.streamlit.app)**
*(Select **`ST1008`** in the left sidebar dropdown to load the Brigade Road store data).*

### 💻 Run Locally
```bash
# Install dependencies
pip install -r requirements.txt

# Run E2E pipeline & compile validation reports
python scripts/run_demo.py
# (Rebuilds store_intelligence.db locally if missing, runs calibration, and compiles all reports)

# Start API + Local Dashboard
uvicorn src.api.main:app --port 8000 &
streamlit run dashboard/app.py
```

---

## Contents of This Folder

| File | Description |
|---|---|
| **`README.md`** | This file — start here |
| **`data_provenance.md`** | ⭐ **Read this if any metrics look inconsistent** — explains the two validation modes |
| **`executive_summary.md`** | 1-page business brief — problem, solution, results (both modes) |
| **`architecture_onepager.md`** | Technical architecture — CV pipeline, zones, POS correlation |
| **`multi_store_generalization.md`** | ⭐ **Multi-store generalization summary** — how the platform generalizes to 3 stores and 13 cameras |
| **`real_run_report.md`** | Results from running on actual CCTV footage (5 cameras, 326 events, 131 visitors) |
| **`api_validation.md`** | API contract validation — all 6 endpoints pass (real CCTV data) |
| **`sample_events.jsonl`** | First 50 real pipeline output events (machine-readable) |
| **`dashboard.png`** | Dashboard screenshot (business demo mode — POS-aligned) |
| **`heatmap.png`** | Zone heatmap visualization (real CCTV data) |
| **`funnel.png`** | Visitor conversion funnel (business demo mode) |
| **`anomaly_panel.png`** | Anomaly detection output (business demo mode) |

---

## Key Results

> **ℹ️ Two validation modes were used.** Read [`data_provenance.md`](./data_provenance.md) for the full explanation. Short version: real CCTV footage proves the CV stack; a demo with POS-aligned timestamps proves POS correlation and the full funnel.

### Real CCTV Run (Multi-Store Generalization)

| Store | Cameras | Visitors | Total Events | Zone Visit % | Conversion Method |
|---|---|---|---|---|---|
| **ST1008** | 5 | 131 | 326 | 41.2% | POS-matched |
| **STORE_1** | 4 | 130 | 470 | 77.7% | queue proxy |
| **STORE_2** | 4 | 111 | 361 | 47.7% | queue proxy |

*   **Total streams processed**: 13 cameras across 3 independent stores.
*   **Code changes required**: **Zero** (fully generalized codebase).
*   *Note*: Display zone analysis for STORE_1 and STORE_2 was validated using automatically generated default zones (no brand-level retail accuracy implied).

### Business Demo (POS Correlation Validation)

| Metric | Value |
|---|---|
| Simulated Customers | 40 |
| POS Transactions | 24 unique invoices |
| Matched Revenue | Rs. 34,331.71 |
| POS Match Rate | 87.5% |
| Funnel Conversion Rate | 40.0% |
| Checkout Abandonment | 7.7% |

---

## Full Documentation Index

```
Purplle_Hackathon/
├── README.md                          # Project overview
├── docs/
│   ├── architecture/
│   │   ├── DESIGN.md                  # Full architecture design document
│   │   ├── CHOICES.md                 # Key technical decisions
│   │   └── architecture_onepager.md   # 1-page architecture brief
│   ├── reports/
│   │   ├── executive_summary.md       # Business brief
│   │   ├── data_provenance.md         # Explains validation modes
│   │   ├── api_validation.md          # API contract validation
│   │   ├── real_run_report.md         # Real CCTV validation report
│   │   └── multi_store_generalization.md # Generalization summary
│   ├── interview/
│   │   ├── interview_prep.md          # ⭐ Interview prep & demo guide
│   │   └── interview_qa.md            # 14 technical Q&As
│   ├── architecture_audit.md          # FSM + schema consistency audit
│   ├── limitations.md                 # Honest system limitations
│   └── risk_register.md               # Risk register with mitigations
├── assets/
│   ├── screenshots/                   # Dashboard, heatmap, funnel, and anomaly pngs
│   ├── layouts/                       # layout_image_0 & 1 pngs
│   └── slides/                        # Pitch deck PDF
├── evaluation/
│   ├── cross_store_validation.md      # comparative dashboard
│   ├── store_coverage_report.md       # Generalization evidence
│   ├── ST1008_validation_report.md    # Brigade Road validation report
│   ├── STORE_1_validation_report.md   # Store 1 validation report
│   ├── STORE_2_validation_report.md   # Store 2 validation report
│   ├── reid_validation.md             # ReID threshold sweep evidence
│   ├── staff_validation.md            # Staff detection accuracy
│   └── failure_analysis.md            # Failure modes and root causes
└── results/
    └── real_events.jsonl              # 326 events from real CCTV run
```

---

## Architecture in 4 Lines

```
CCTV Video → YOLOv8s person detection → ByteTrack multi-object tracking
→ OSNet ReID cross-camera re-identification → Zone polygon assignment
→ VisitorStateMachine (6 states) → Session analytics
→ POSCorrelatorV2 brand-attribution → FastAPI + Streamlit dashboard
```

---

## Technical Decisions (Quick Reference)

| Component | Choice | Why |
|---|---|---|
| Detection | YOLOv8s | Best accuracy/speed on CPU; COCO pre-trained handles retail |
| Tracking | ByteTrack | Uses low-confidence boxes — handles occlusion |
| ReID | OSNet x0.25 | Designed for person ReID; 12ms/crop on CPU |
| Database | SQLite | Zero-config; SQLAlchemy abstraction allows easy swap to PostgreSQL |
| API | FastAPI | Async, auto-docs, Pydantic schema validation |
| Zones | Shapely polygons | Exact geometric containment vs bounding box heuristics |
