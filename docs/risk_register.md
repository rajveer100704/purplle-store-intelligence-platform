# CCTV Store Intelligence Project Risk Register

This document identifies, assesses, and documents mitigation strategies for risks associated with the CCTV Store Intelligence Pipeline in production environments.

---

## Active Risk Ledger

| Risk ID | Risk Description | Probability | Impact | Mitigation Strategy |
|---|---|---|---|---|
| **R-1** | **ReID Confusion (False Identity Merging)**: Similar clothing patterns on different customers merge their sessions. | Medium | Medium | Implement the `uncertain_reid` flag for scores in the `0.55 - 0.75` similarity band to segment dubious handovers. |
| **R-2** | **Camera Blind Spots**: Customers walk through store areas not covered by any CCTV stream. | High | Medium | Store layout parser supports multi-camera coverage registries. Missing regions are mapped to nearest visible displays. |
| **R-3** | **POS Timestamp Drift**: Inaccurate clocks on POS terminals cause exit matching windows to fail. | Medium | High | Maintain a configurable `POS_MATCH_WINDOW` (300 seconds default) and implement NTP server sync checks on host machines. |
| **R-4** | **Queue Geometry Missing / Calibration Error**: Camera tilt or physical desk movement changes queue coordinates. | Low | Medium | Implement the `infer_queue_polygon` fallback, which approximates queue area based on billing desk centroids. |
| **R-5** | **Staff False Positives (FP)**: Employees not wearing uniforms are counted as customers, inflating footfall. | Low | Low | Scoring logic balances uniform HSV matching with early check-ins and long dwell thresholds (threshold $\ge 3$). |
| **R-6** | **High Crowd Congestion (Occlusions)**: Crowded events cause YOLO and ByteTrack to drop tracks. | Medium | High | Rely on Kalman filter trajectory estimation in `ByteTrack` to maintain track continuity through brief occlusions. |
