# Real CCTV Validation Report - ST1008

Generated at: 2026-06-03 09:53:03 UTC

## Store Profile
- **Store ID**: ST1008
- **Store Name**: Brigade_Bangalore
- **POS Available**: Yes (matched)
- **CCTV Cameras Active**: 5 (CAM1, CAM2, CAM3, CAM4, CAM5)

## Key Retail Indicators
| Metric | Value | Notes |
|---|---|---|
| **Footfall** | 131 | Unique customers (staff excluded) |
| **Staff Identified** | 0 | Filtered via hybrid heuristic |
| **Conversion Rate** | 0.0% (POS-matched) | |
| **Matched POS Transactions** | 0 / 24 | Correlated within 5-min window |
| **Matched Revenue** | Rs. 0.00 | Cumulative correlated sales |
| **Queue Abandonment** | 0.0% | Joined billing but exited without purchase |

## Customer Funnel
- **Stage 1 (Entry)**: 131 visitors (100.0%)
- **Stage 2 (Zone Visit)**: 14 visitors (10.7%)
- **Stage 3 (Billing Queue)**: 0 visitors (0.0%)
- **Stage 4 (Purchase)**: 0 visitors (0.0%)

## Camera-Level Statistics
| Camera | Entries | Exits | Staff Filtered | Duration (s) |
|---|---|---|---|---|
| CAM1 | 34 | 27 | 0 | 139s |
| CAM2 | 41 | 13 | 0 | 121s |
| CAM3 | 31 | 27 | 0 | 145s |
| CAM4 | 1 | 0 | 0 | 0s |
| CAM5 | 24 | 20 | 0 | 127s |

## Empirical Calibration Notes
Real CCTV validation intentionally produced 0 POS matches because the CCTV timestamps and POS timestamps originate from different dates. POS correlation was therefore validated separately through the business demo mode.
