# Store Intelligence Platform — Executive Summary

## Problem Statement
Traditional physical retail stores operate as "black boxes" compared to online e-commerce platforms. While e-commerce sites track visitor page clicks, drop-offs, and brand interest, physical retail stores lack visibility into visitor journeys, shelf-level conversions, checkout abandonment rates, and queue bottlenecks.

## Proposed Solution
The CCTV Store Intelligence Platform bridges this gap. By utilizing existing CCTV security cameras, the physical store layout, and POS transaction logs, it creates a unified retail intelligence stream. The platform extracts spatial-temporal trajectories, resolves identities across cameras, and correlates visits to actual purchases without collecting personally identifiable information (PII).

---

## Technical Approach

```
Security Video (CCTV) → YOLOv8s & ByteTrack → OSNet ReID Gallery → 6-State FSM
                                                                        │
Physical Layout JSON ───────→ Zone Geometry Registry (Shapely) ◄────────┘
                                      │
POS Invoice CSV ────────────→ POS Correlator V2 (±5 min match window)
                                      │
                                      ▼
                      FastAPI API & Streamlit Dashboard
```

1. **Computer Vision Layer**: YOLOv8s person detection coupled with ByteTrack for local tracking.
2. **Cross-Camera ReID**: OSNet_x0_25 computes 512-dimensional embeddings to match visitors across cameras.
3. **Zone Mapping (Layout)**: Shapely polygons map physical coordinate display shelves to brand zones (e.g. Lakme).
4. **POS Correlation Layer**: Reconciles session exits with transaction times within a ±5-minute window.
5. **Business API**: Exposes metrics, heatmaps, and funnels.

---

## Key Results & Metrics

The platform was validated in two complementary modes. See [`data_provenance.md`](./data_provenance.md) for the full explanation.

### Mode 1 — Real CCTV Validation (Brigade Road, ST1008)

These numbers come from running the full pipeline on 5 actual CCTV cameras (~70 min footage):

- **Footfall Tracking**: **131 unique visitors** detected and tracked across 5 cameras.
- **Zone Engagement**: 54 visitors (41.2%) entered at least one brand zone.
- **Events Generated**: 326 business events (ENTRY, EXIT, ZONE_ENTER, ZONE_EXIT, ZONE_DWELL).
- **Processing Performance**: ~7 min wall-clock on CPU (5 cameras, `--skip-frames 10`).

### Mode 2 — End-to-End Business Demo (POS Correlation Validation)

These numbers come from `scripts/generate_demo.py` using the real 24-invoice POS CSV with timestamp-aligned synthetic journeys, demonstrating full funnel capability:

- **Footfall**: 40 simulated customer sessions (24 purchasers + 14 browsers + 2 queue abandoners).
- **POS Match Rate**: **87.5%** — the correlator linked 35 of 40 sessions to a POS invoice within the ±5-minute window.
- **Funnel Conversion Rate**: **40%** — 16 of 40 visitors completed the full entry → zone → billing → purchase journey.
- **Matched Revenue**: Rs. 34,331.71 in correlated sales value.
- **Checkout Abandonment**: 7.7% queue drop-off rate.
- **Operational Alerts**: Dead zones (e.g. Minimalist displays) flagged automatically on inactive visitor periods.

> **87.5% vs 40%**: These are different metrics. 87.5% is the POS system's ability to link a visitor track to a receipt (match rate). 40% is the retail conversion funnel (how many store entrants completed a purchase journey). See [`data_provenance.md`](./data_provenance.md) for the full breakdown.

> **Why two modes?** The real CCTV footage timestamps (2026-05-30) do not align with the POS invoice dates (2026-04-10), so POS correlation is validated through the demo. See [`data_provenance.md`](./data_provenance.md) for the complete rationale.

---

## Limitations & Future Roadmap
- **Limitations**: ReID handovers are affected by extreme lighting/clothing similarity. Brand attribution assumes interest based on spatial proximity.
- **Roadmap**: Integrate clothing color histograms in ReID, map face/gaze directions to shelf products, and scale the POS correlator using interval tree mappings.
