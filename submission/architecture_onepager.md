# Store Intelligence Platform — Architecture One-Pager

A high-performance, edge-capable retail analytics system that processes security CCTV streams, physical layout mappings, and POS invoices to extract display-level customer conversion metrics.

---

## 1. Multi-Layer Design

```
+-----------------------------------------------------------------------------------+
|                           Retail Intelligence layers                              |
+-----------------------------------------------------------------------------------+
|  [Layer 1] Zone Geometry Registry                                                 |
|  - Maps coordinates of physical brand displays from store_config.json             |
|                                                                                   |
|  [Layer 2] CV Stream Processing                                                   |
|  - Person Detection (YOLOv8s) → Trajectory Tracking (ByteTrack)                  |
|  - Cross-camera Handover Identity (OSNet ReID COS Gallery)                        |
|  - Visitor FSM (ENTRY, EXIT, ZONE_ENTER, ZONE_EXIT, DWELL, QUEUE_JOIN)            |
|                                                                                   |
|  [Layer 3] POS Correlation Engine                                                 |
|  - Pairs session exits to actual store receipts within a ±5 minute window         |
|  - Resolves brand conversion: visited_brand ∩ purchased_brand                      |
+-----------------------------------------------------------------------------------+
|                            FastAPI API & Streamlit UI                             |
+-----------------------------------------------------------------------------------+
```

---

## 2. Technical Component Breakdown

### A. Computer Vision Layer
- **YOLOv8s Person Wrapper**: Pretrained detection of individuals with a configured confidence threshold of `0.25`.
- **ByteTrack Tracker**: Keeps tracks across frames using bounding box intersection-over-union (IoU) and Kalman state filters.
- **TrackLifecycleManager**: Prevents false exit events from brief occlusions by waiting for a `lost_timeout` (5.0s) before expiring tracks. Exits are only emitted if the track expires near the image margins or exit line.
- **OSNet Cross-Camera ReID**: Extracts 512-dimensional appearance embeddings per crop. Gallery maps similar identities using cosine similarity ($> 0.75$ same identity, $< 0.55$ new identity, middle band marked as ambiguous).

### B. Retail Intelligence & Calibration Layer
- **Physical Zone Mapping**: Scales normalized coordinates from the layout JSON to match the camera's resolution. Tests zone entry/exit using Shapely polygon collision detection.
- **Staff Recognition**: Excludes store staff from commercial metrics (footfall, queue abandonment, conversions) using a scoring model based on pre-opening arrival, long dwell, appearance density, and uniform color.

### C. POS Transaction Correlation
- **POS Parser**: Group invoices by checkout receipt time.
- **Match Correlation**: Evaluates checkout times against visitor exits. Attributes conversions correctly using the intersection of visited shelves and purchased items.
- **Scaling Capability**: For large deployments, matching scales from $O(N \times M)$ to $O(N \log M)$ using sorted timestamps and binary search window checks.
