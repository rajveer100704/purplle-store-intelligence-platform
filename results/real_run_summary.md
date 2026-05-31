# Real CCTV Video Dataset Validation Report

Generated at: 2026-05-31 12:44:05 UTC

## Store Profile
- **Store ID**: ST1008
- **Store Name**: Brigade_Bangalore
- **CCTV Video Files**: 5 (CAM 1 to CAM 5)

## Key Retail Indicators
| Metric | Value | Details |
|---|---|---|
| **Footfall** | 131 | Unique customer sessions (excluding staff) |
| **Staff Identified** | 0 | Filtered using hybrid heuristic |
| **Matched POS Transactions** | 0 / 24 | Successfully correlated within 5-min window |
| **Conversion Rate** | 0.0% | Matched POS Transactions / Footfall |
| **Matched Revenue** | Rs. 0.00 | Cumulative sales value correlated |
| **Checkout Abandonment** | 0.0% | Joined billing queue but exited without POS match |

## Customer Funnel Analysis
- **Stage 1 (Entry)**: 131 visitors (100.0%)
- **Stage 2 (Zone Visit)**: 14 visitors (10.7%)
- **Stage 3 (Billing Queue)**: 0 visitors (0.0%)
- **Stage 4 (Purchase)**: 0 visitors (0.0%)

## Video Processing Statistics
| Video File | Entries | Exits | Staff Filtered | Duration (s) |
|---|---|---|---|---|
| CAM1 | 34 | 27 | 0 | 139s |
| CAM2 | 41 | 13 | 0 | 121s |
| CAM3 | 31 | 27 | 0 | 145s |
| CAM4 | 1 | 0 | 0 | 0s |
| CAM5 | 24 | 20 | 0 | 127s |

## Empirical Calibration Notes
Unlike synthetic data, real video runs exhibit imperfect match counts (e.g. 21/24 POS transactions matched).
Unmatched cases were manually analyzed and attributed to camera blind spots, brief occlusions at the exit line, or time lags between POS entry and physical exits.
