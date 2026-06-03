# Real CCTV Validation Report - STORE_1

Generated at: 2026-06-03 09:53:03 UTC

## Store Profile
- **Store ID**: STORE_1
- **Store Name**: Store_1
- **POS Available**: No (queue-based proxy used)
- **CCTV Cameras Active**: 4 (CAM1, CAM2, CAM3, CAM5)

## Key Retail Indicators
| Metric | Value | Notes |
|---|---|---|
| **Footfall** | 130 | Unique customers (staff excluded) |
| **Staff Identified** | 0 | Filtered via hybrid heuristic |
| **Conversion Rate** | 0.0% (no billing data) | |
| **Queue Abandonment** | 0.0% | Joined billing but exited without purchase |

## Customer Funnel
- **Stage 1 (Entry)**: 130 visitors (100.0%)
- **Stage 2 (Zone Visit)**: 101 visitors (77.7%)
- **Stage 3 (Billing Queue)**: 0 visitors (0.0%)
- **Stage 4 (Purchase)**: 0 visitors (0.0%)

## Camera-Level Statistics
| Camera | Entries | Exits | Staff Filtered | Duration (s) |
|---|---|---|---|---|
| CAM1 | 34 | 27 | 0 | 139s |
| CAM2 | 41 | 13 | 0 | 125s |
| CAM3 | 31 | 27 | 0 | 145s |
| CAM5 | 24 | 20 | 0 | 127s |

## Note on POS Data
POS transactions are not available for STORE_1. Conversion rate is estimated using billing queue completion as a proxy. This demonstrates the platform's graceful degradation when POS data is absent.
