# Real CCTV Validation Report - STORE_2

Generated at: 2026-06-03 09:53:04 UTC

## Store Profile
- **Store ID**: STORE_2
- **Store Name**: Store_2
- **POS Available**: No (queue-based proxy used)
- **CCTV Cameras Active**: 4 (BILLING_CAM1, ENTRY_CAM1, ENTRY_CAM2, ZONE_CAM1)

## Key Retail Indicators
| Metric | Value | Notes |
|---|---|---|
| **Footfall** | 111 | Unique customers (staff excluded) |
| **Staff Identified** | 0 | Filtered via hybrid heuristic |
| **Conversion Rate** | 0.0% (no billing data) | |
| **Queue Abandonment** | 0.0% | Joined billing but exited without purchase |

## Customer Funnel
- **Stage 1 (Entry)**: 111 visitors (100.0%)
- **Stage 2 (Zone Visit)**: 53 visitors (47.7%)
- **Stage 3 (Billing Queue)**: 0 visitors (0.0%)
- **Stage 4 (Purchase)**: 0 visitors (0.0%)

## Camera-Level Statistics
| Camera | Entries | Exits | Staff Filtered | Duration (s) |
|---|---|---|---|---|
| BILLING_CAM1 | 18 | 9 | 0 | 119s |
| ENTRY_CAM1 | 33 | 28 | 0 | 98s |
| ENTRY_CAM2 | 44 | 42 | 0 | 76s |
| ZONE_CAM1 | 16 | 13 | 0 | 80s |

## Note on POS Data
POS transactions are not available for STORE_2. Conversion rate is estimated using billing queue completion as a proxy. This demonstrates the platform's graceful degradation when POS data is absent.
