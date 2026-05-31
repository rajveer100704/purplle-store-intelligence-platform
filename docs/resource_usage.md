# Store Intelligence Platform — Resource Utilization Mapping

This document maps how the three primary hackathon resources (Store Layout, POS Transaction CSV, and CCTV Video Feeds) are utilized as core pipeline assets.

---

## Resource Mapping Ledger

| Resource Name | Source Asset | Direct Pipeline Mapping | Business Value Generated |
|---|---|---|---|
| **Store Layout** | `data/store_layout.xlsx` & blueprint image. | Converted into [store_config.json](file:///c:/Users/BIT/Purplle_Hackathon/src/layout/store_config.json) containing 20 brand Display Zones mapped as Shapely coordinates. | Replaces generic zone labels (`ZONE_4`) with semantic brand IDs (`LAKME`), enabling display-specific engagement heatmaps. |
| **POS Transaction Logs** | `data/pos_transactions.csv` containing invoice order lists. | Parsed by `src/pos/parser.py` and correlated to visitor exits via `src/pos/correlator.py`. | Translates CV track exits into actual customer conversions, matched revenue, and checkout abandonments. |
| **CCTV Video Feeds** | 5 video files (`CAM 1` to `CAM 5`) under `CCTV Footage/`. | Streamed through YOLOv8s detection, ByteTrack tracking, and OSNet ReID gallery. | Provides the core trajectory datasets: footfall entries, exits, queue waits, and dwell times. |

---

## Combined Integration Flow

```
1. Physical Store Layout  ──────────┐
   (Excel Blueprint coordinates)    │
                                    ▼
                             Store Config JSON (Zone Polygons)
                                    │
                                    ▼
2. CCTV Security Feeds ─────────────┼──→ EventEmitter (Brand-named events)
   (Entrance, aisles, cashier)      │
                                    ▼
                             Visitor Session Engine (Visited brands)
                                    │
                                    ▼
3. POS Transaction logs ────────────┼──→ POS Correlator V2 (Match exits & brands)
   (Invoices, items, amounts)       │
                                    ▼
                              Retail Intelligence metrics (API / Dashboard)
```
