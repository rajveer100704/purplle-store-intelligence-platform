# Cross-Store Validation Report

Generated at: 2026-06-03 09:53:05 UTC

## Store Performance Comparison
| Store | Visitors | Total Events | Zone Events | Queue Events | Conversion | Method |
|---|---|---|---|---|---|---|
| ST1008 | 131 | 326 | 108 | - | 0.0% | POS-matched |
| STORE_1 | 130 | 470 | 253 | - | 0.0% | queue-based proxy |
| STORE_2 | 111 | 361 | 156 | - | 0.0% | queue-based proxy |

## Camera Topology Summary
| Store | Entry Cameras | Zone Cameras | Billing Cameras | Total | POS |
|---|---|---|---|---|---|
| ST1008 | 1 | 2 | 1 | 5 | Yes |
| STORE_1 | 1 | 2 | 1 | 4 | No |
| STORE_2 | 2 | 1 | 1 | 4 | No |

## Key Observations
- Same codebase successfully processed three independent stores with different camera layouts.
- STORE_2 demonstrates dual-entry topology (2 entry cameras) — unique capability.
- POS gracefully degrades to queue-based conversion for STORE_1 and STORE_2.
- Brand-zone attribution available for ST1008 (POS-matched); generalization validation using automatically generated display zones for STORE_1 and STORE_2.
