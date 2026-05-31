# CCTV Store Intelligence Pipeline — System Limitations

This document lists the architectural limits and assumptions of the current Store Intelligence Platform. Acknowledging these boundaries is vital for managing stakeholders' expectations and setting roadmap milestones.

---

## Technical Constraints

### 1. Cross-Camera ReID Clothing Sensitivity
* **Limit**: The OSNet appearance embedder extracts features from visitor crops (primarily clothing color, texture, and body shape).
* **Consequence**: If multiple visitors wear highly similar clothing (e.g. store uniforms or plain white shirts) on the same day, the ReID gallery may merge separate trajectories.
* **Mitigation**: The pipeline flags matches with borderline similarity (`0.55` to `0.75`) as `uncertain_reid=True` in the database to segregate them from high-confidence analytics.

### 2. Spatial Proximity as a Proxy for Brand Engagement
* **Limit**: The system assumes interest in a brand Display Zone when a visitor's coordinate enters the designated Shapely polygon.
* **Consequence**: A visitor walking down an aisle close to a display shelf without looking at the products will still register a `ZONE_ENTER` event.
* **Mitigation**: A `ZONE_DWELL` event is only emitted after continuous presence for 30 seconds, filtering out quick walk-bys.

### 3. POS Transaction Proximity Matching
* **Limit**: Purchases are attributed using time proximity (within ±5 minutes of the customer's exit).
* **Consequence**: If multiple customers exit the store at the same time, the system may mismatch order attachments if their visited brand profiles overlap.
* **Mitigation**: Brand conversion checks only attribute a transaction to a visitor if there is a non-empty intersection between their visited shelves and the brands on the receipt:
  $$\text{brand\_conversion} = \text{visited\_brands} \cap \text{brands\_purchased}$$

### 4. Queue Queue-depth Inference
* **Limit**: Queue joins are detected using a 2D bounding box checklist.
* **Consequence**: High perspective tilt in camera feeds can cause customers standing near the queue but not in line to be counted, or self-occlusions to hide queue members.
* **Mitigation**: The FSM enforces `BILLING_QUEUE_JOIN` events only when `queue_depth > 0` is reported by the local tracker.
