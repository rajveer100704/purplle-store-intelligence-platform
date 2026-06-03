# Interview Q&A Pack — CCTV Store Intelligence Platform

**Purpose**: Prepare concise, authoritative answers to the most likely technical interview questions about this system. Each answer is grounded in actual implementation decisions.

---

## Architecture Decisions

### Q1: Why ByteTrack instead of DeepSORT or SORT?

**Answer**: ByteTrack uses **all detection boxes** — not just high-confidence ones — for association. This matters because partially occluded people (walking behind a display shelf) often produce low-confidence detections. ByteTrack's two-stage matching (`BYTE`) recovers these as re-associations rather than creating new track IDs. DeepSORT requires an appearance model at tracking time (extra latency), while SORT has no appearance model at all (high ID-switch rate in crowds). ByteTrack gives us the best accuracy-speed balance on CPU.

---

### Q2: Why OSNet (osnet_x0_25) for ReID?

**Answer**: OSNet (Omni-Scale Network) is designed specifically for person re-identification and learns discriminative features at multiple scales simultaneously — capturing both fine-grained clothing texture and coarse body shape. We use the `x0_25` variant (25% width multiplier) which runs in ~12ms/crop on CPU compared to 50ms+ for ResNet-50 based ReID. At 512-dimensional embeddings, cosine similarity gives us a highly reliable distance metric that degrades gracefully when clothing/lighting changes.

---

### Q3: Why a 0.75 match threshold for ReID?

**Answer**: The threshold was empirically validated using 100 manually labelled pairs (50 positive, 50 negative) from real store footage (see `evaluation/reid_validation.md`). At `0.75`, the system achieves **95.3% precision**, **82.0% recall**, and a low **4.0% false merge rate**. Going lower (e.g., `0.65`) increases recall to 92.0% but drops precision to 88.5% and raises the false merge rate to 12.0%—meaning different customers would occasionally be merged, corrupting footfall and funnel metrics. 0.75 provides the optimal trade-off prioritizing precision for metric credibility.

---

### Q4: Why SQLite and not PostgreSQL?

**Answer**: SQLite is sufficient for the hackathon context (single-machine, ~500 events/day per store). Its file-based architecture means zero setup time, portability, and compatibility with SQLAlchemy async (`aiosqlite`). The data access layer is already abstracted behind SQLAlchemy models, so swapping to PostgreSQL requires changing only the connection string (`DATABASE_URL` env variable) and the driver (`asyncpg`). The schema and queries are PostgreSQL-compatible already.

---

### Q5: Why a ±5 minute POS correlation window?

**Answer**: The 5-minute window (300 seconds) reflects empirical timing between physical payment at the POS terminal and the customer's physical exit from the store. In a beauty retail store like Purplle/Brigade, a customer at the billing counter takes 1–3 minutes to scan items, pay, and collect bags. Adding a 1–2 minute buffer for cross-camera blind spots and delayed exit detection gives us a 5-minute window. This was also validated against the provided POS data: all manual matches fell within a 3.5-minute window, and 5 minutes gives sufficient headroom.

---

### Q6: Why use skip-frames (frame skipping) in the pipeline?

**Answer**: Processing every frame of 5 full HD 1080p videos at 30fps through YOLO and ByteTrack takes ~15–20 minutes on CPU. Frame skipping (every Nth frame) reduces this proportionally while maintaining trajectory continuity — person positions between skipped frames are interpolated by ByteTrack's Kalman filter. At skip-frames=5, we process 1/5th of frames and run in ~3 minutes with negligible trajectory degradation (movement between frames is <50px for walking speed).

---

### Q7: Why not train a custom YOLO model on store footage?

**Answer**: YOLOv8s pre-trained on COCO already generalizes extremely well to person detection in retail environments. Training a custom model would require a labelled dataset of ~5,000+ bounding boxes, GPU compute, and weeks of iteration — none of which is available in a hackathon context. The pre-trained model achieves ~0.85 precision at 0.25 confidence threshold on the provided footage (observed during calibration). A custom model would provide marginal gains and significant engineering overhead.

---

## System Design

### Q8: How do you handle someone who leaves and comes back?

**Answer**: The `VisitorStateMachine` has a dedicated `REENTERED` state. When a visitor's embedding matches an existing gallery entry after a prior `EXIT` event, the system emits a `REENTRY` event rather than a new `ENTRY`. The session manager opens a new session with `session_seq=2` (incrementing), preserving the historical session under the same `visitor_id`. The brand visit history is maintained across both sessions for funnel analysis.

---

### Q9: How do you handle identity when someone is occluded?

**Answer**: The `TrackLifecycleManager` distinguishes between two cases: (1) **Temporary occlusion**: track goes `LOST` but recovers within `TRACK_LOST_TIMEOUT` (5 seconds). The same track_id is resumed. (2) **Genuine disappearance**: track goes `LOST` and doesn't recover. If the last known position was near the exit boundary (within 10% of frame edge or 50px from exit line), an `EXIT` signal is emitted. Otherwise the track expires silently (`EXPIRED_SILENT`) — preventing phantom exit events.

---

### Q10: How do you prevent staff from inflating footfall metrics?

**Answer**: A multi-rule scoring heuristic assigns points for: (1) Pre-open arrival before `STORE_OPEN_HOUR`, (2) Presence ratio >70% of camera clip duration, (3) Clothing in the blue-hue HSV range (110–130) indicating a uniform, and (4) Appearance in multiple cameras simultaneously. A score ≥ 3/4 flags the visitor as staff. All staff-flagged sessions are excluded from customer footfall, funnel, and conversion metrics — but preserved in the database with `is_staff=True` for audit.

---

### Q11: How does POS correlation handle multiple customers buying at the same time?

**Answer**: The `POSCorrelatorV2` first filters POS transactions to within the ±5 minute window of each session's exit timestamp. For sessions that both match the same transaction, it applies a **brand overlap check**: it computes the intersection of `session.visited_brands` with `transaction.brands_purchased`. The session with the higher overlap count gets the attribution. If overlap is equal, the session with the closest exit timestamp wins (temporal proximity tie-breaker).

---

### Q12: What happens if the cameras have different clocks?

**Answer**: This is documented in `evaluation/failure_analysis.md` as a known limitation. Currently, the pipeline uses video start time (`datetime.now(UTC)`) as the epoch for all events — meaning all cameras in the same batch run are synchronized to the same wall clock. In production, cameras should be NTP-synchronized and their RTSP streams should carry embedded timestamps. The `video_start_time` parameter in `EventEmitter` is designed to accept a real timestamp from any source.

---

## Metrics & Validation

### Q13: How do you know your ReID threshold is correct?

**Answer**: We ran a validation sweep using 100 manually annotated pairs (50 positive, 50 negative) extracted from real store footage. We swept the cosine similarity threshold from `0.60` to `0.85` and computed precision, recall, and false merge rates for each step. At `0.75`, we achieved 95.3% precision, 82.0% recall, and a 4.0% false merge rate. The detailed sweep is documented in `evaluation/reid_validation.md`. We also ran an exploratory statistical sweep across a larger automated dataset, documented in `evaluation/reid_calibration_report.md`.

---

### Q14: How do you know the staff detection is accurate?

**Answer**: We manually labelled 12 tracks across 3 cameras with ground-truth staff/customer labels (see `evaluation/annotations/staff_labels.csv`). The pipeline correctly classified 3/3 staff members (100% recall) and 9/9 customers correctly (100% precision at staff detection). The full validation is in `evaluation/staff_validation.md`.
