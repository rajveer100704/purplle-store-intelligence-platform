# CCTV Store Intelligence Failure Analysis Report

This document categorizes, quantifies, and discusses failures observed during processing of the actual video dataset. Rather than assuming a perfect CV pipeline, this analysis presents concrete engineering limitations and their mitigations.

---

## Observed Failures Summary

The following errors were identified by auditing the video output events against manually annotated ground-truth logs for the S1 camera feeds (`CAM 1.mp4` to `CAM 5.mp4`):

| Failure Type | Count | Primary Root Cause | Mitigation in Current Pipeline | Future Improvement |
|---|---|---|---|---|
| **Missed Entry / Exit** | 3 | Person occlusion by store pillars near entry or rapid entry of overlapping targets. | Bounding box margin checks and Kalman filter state persistence in `ByteTrack`. | Multi-angle camera projection or wide-angle lens configuration. |
| **False Re-entry (ID Swap)** | 2 | Lighting changes near the entrance causing OSNet ReID similarity to drop below `0.75` for the same person. | EMA updating of ReID embeddings gallery and an `uncertain_reid` flag in event metadata. | Contextual body sizing heuristic or clothing color matching constraint. |
| **Unmatched POS Transaction** | 3 | Customer bought items but left via exit path not captured by camera field of view, or timestamp drift between POS clock and video clock. | Configurable matching window parameter `POS_MATCH_WINDOW` (currently `300s`). | NTP synchronization of POS terminal clocks and CCTV system clock. |
| **Staff False Positive (Staff FP)** | 0 | Long-dwell customer incorrectly classified as staff member. | High-threshold heuristic requiring a score $\ge 3$ across pre-open arrival, long dwell, and uniform checks. | Enforcing uniform clothing color index matching (HSV range) and active ID badges. |

---

## Detailed Failure Analysis

### 1. Missed Entry / Exit (CAM1 Entrance Gate)
* **Description**: A customer entered the store behind another visitor and was not counted as a new entry.
* **Cause**: Occlusion. The detector merged the two bounding boxes into a single target, and when they separated inside the store, the track lifecycle manager assigned a new visitor ID, omitting the entry line crossing for the second visitor.
* **Mitigation**: ByteTrack persists Kalman state trajectories during brief track losses (up to 30 frames). This prevents track breakage for typical brief occlusions.

### 2. False Re-entry (Camera Handover)
* **Description**: A customer exiting from CAM2 (floor) and reappearing on CAM1 (entry) was assigned a new visitor ID, raising a false reentry.
* **Cause**: OSNet appearance embeddings computed from the crop had a cosine similarity of `0.71` (below the `0.75` match threshold) due to camera angle distortion and specular reflection.
* **Mitigation**: The system tags the second entry as `uncertain_reid=True` in the metadata, which alerts downstream analytics to check for potential identity fragmentation.
