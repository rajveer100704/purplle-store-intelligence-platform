# CCTV Store Intelligence Platform — Submission Package

**Team**: Purplle Hackathon 2026
**Store**: Brigade Road, Bangalore (ST1008)
**Submission Date**: 2026-05-31

---

## What This System Does

This platform converts raw CCTV footage from 5 cameras into **brand-level retail intelligence** — connecting physical visitor behavior to actual POS transactions. It is built specifically for the Purplle Brigade Road store.

**Input**:
- 5 CCTV cameras (CAM1–CAM5)
- Store layout with 20 brand zones (Lakme, Minimalist, Aqualogica, Foxtale, etc.)
- POS transaction CSV (24 invoices from 2026-04-10)

**Output**:
- Per-visitor brand zone journeys
- Conversion funnel (Entry → Zone → Billing → Purchase)
- Zone-level heatmaps
- Anomaly detection (dead zones, queue spikes, conversion drops)
- POS-correlated conversion rate with brand attribution

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run one-command demo (synthetic data, POS-aligned)
python scripts/run_demo.py

# Run real pipeline on CCTV footage
python -m src.pipeline --data "PATH_TO_CCTV" --output results/real_events.jsonl --skip-frames 10

# Start API + Dashboard
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

### Real CCTV Run (CV Stack Validation)

| Metric | Value |
|---|---|
| Videos Processed | 5 cameras |
| Total Events | 326 |
| Unique Visitors | 131 |
| Zone Visitors | 54 (41.2%) |
| Top Brand Zone | FOH (Front of House — 35 visits) |
| Processing Speed | ~7 min wall-clock (CPU, skip-frames=10) |

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
├── DESIGN.md                          # Full architecture design document
├── docs/
│   ├── executive_summary.md           # Business brief
│   ├── architecture_audit.md          # FSM + schema consistency audit
│   ├── interview_qa.md                # 14 technical Q&As
│   ├── interview_prep.md              # ⭐ Interview prep & demo guide
│   ├── limitations.md                 # Honest system limitations
│   └── risk_register.md               # Risk register with mitigations
├── evaluation/
│   ├── real_run_report.md             # Real CCTV pipeline results
│   ├── api_validation.md              # API contract validation
│   ├── docker_validation.md           # Docker startup validation
│   ├── reproducibility.md             # Python versions, config, seeds
│   ├── reid_validation.md             # ReID threshold sweep evidence
│   ├── staff_validation.md            # Staff detection accuracy
│   ├── failure_analysis.md            # Failure modes and root causes
│   ├── dataset_profile.md             # Video characteristics
│   └── annotations/
│       ├── reid_pairs.csv             # 15 manually labelled ReID pairs
│       ├── staff_labels.csv           # Ground-truth staff labels
│       └── manual_counts.json         # Per-camera manual entry/exit counts
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
