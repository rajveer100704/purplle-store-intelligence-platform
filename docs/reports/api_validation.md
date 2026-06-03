# API Contract Validation Report

**Purpose**: Validate that every API endpoint meets its contract — correct HTTP status codes, schema compliance, and expected data ranges.

**Date Validated**: 2026-05-31
**API Base URL**: `http://localhost:8000`
**Test Data**: 326 real CCTV events ingested from `results/real_events.jsonl` (5 cameras, Brigade Road ST1008)
**Test Framework**: Manual + `httpx` assertions

> **Consistency Note**: All "Actual" values below are sourced directly from the running API after ingesting `results/real_events.jsonl`. These match the numbers in `evaluation/real_run_report.md`.

---

## Endpoints Under Test

### 1. `POST /events/ingest`

**Purpose**: Batch-ingest visitor events from pipeline output.

| Field | Expected | Actual | Pass/Fail |
|---|---|---|---|
| Status Code | `202 Accepted` | `202` | ✅ |
| Response `accepted` | `> 0` | `326` | ✅ |
| Response `rejected` | `0` (clean data) | `0` | ✅ |
| Schema: `accepted: int` | Required | Present | ✅ |
| Schema: `rejected: int` | Required | Present | ✅ |

**Example Response**:
```json
{"accepted": 326, "rejected": 0}
```

---

### 2. `GET /metrics`

**Purpose**: Return high-level store KPIs (footfall, dwell, conversion, etc.)

| Field | Expected | Actual | Pass/Fail |
|---|---|---|---|
| Status Code | `200 OK` | `200` | ✅ |
| `footfall` | `> 0` integer | `131` | ✅ |
| `unique_visitors` | `> 0` integer | `131` | ✅ |
| `conversion_rate` | `0.0–1.0` float | `0.0`* | ✅ |
| `top_zones` | non-empty list | `["FOH","AQUALOGICA","MINIMALIST"]` | ✅ |
| `abandonment_rate` | `0.0–1.0` float | `0.0` | ✅ |

> *Conversion rate is 0.0 on real CCTV events because POS data timestamps (2026-04-10) do not align with pipeline run timestamps (2026-05-30). See `evaluation/real_run_report.md` for full explanation. POS correlation is validated separately via `scripts/generate_demo.py`.

**Example Response**:
```json
{
  "store_id": "ST1008",
  "footfall": 131,
  "unique_visitors": 131,
  "conversion_rate": 0.0,
  "abandonment_rate": 0.0,
  "top_zones": ["FOH", "AQUALOGICA", "MINIMALIST"]
}
```

---

### 3. `GET /funnel`

**Purpose**: Return the visitor conversion funnel by stage.

| Field | Expected | Actual | Pass/Fail |
|---|---|---|---|
| Status Code | `200 OK` | `200` | ✅ |
| `entry` | `> 0` integer | `131` | ✅ |
| `zone_visit` | `≤ entry` integer | `54` (41.2%) | ✅ |
| `billing` | `≤ zone_visit` integer | `0`* | ✅ |
| `purchase` | `≤ billing` integer | `0`* | ✅ |

> *Billing and purchase are 0 on real CCTV run due to camera angle not covering the billing polygon boundary. See `evaluation/real_run_report.md`.

**Example Response**:
```json
{
  "store_id": "ST1008",
  "entry": 131,
  "zone_visit": 54,
  "billing": 0,
  "purchase": 0,
  "dropoff": {"entry_to_zone": 77, "zone_to_billing": 54, "billing_to_purchase": 0}
}
```

---

### 4. `GET /heatmap`

**Purpose**: Return zone-level visitor count data for spatial heatmap visualization.

| Field | Expected | Actual | Pass/Fail |
|---|---|---|---|
| Status Code | `200 OK` | `200` | ✅ |
| Response `zones` | Non-empty list | 20 zones returned | ✅ |
| Each zone `zone_id` | Non-empty string | Present | ✅ |
| Each zone `visit_count` | `>= 0` integer | All non-negative | ✅ |
| Each zone `avg_dwell_s` | `>= 0.0` float | All non-negative | ✅ |

**Example Response** (real pipeline output, top 3 zones):
```json
{
  "zones": [
    {"zone_id": "FOH", "visit_count": 35, "avg_dwell_s": 30.0},
    {"zone_id": "AQUALOGICA", "visit_count": 7, "avg_dwell_s": 0.0},
    {"zone_id": "MINIMALIST", "visit_count": 6, "avg_dwell_s": 0.0}
  ]
}
```

---

### 5. `GET /anomalies`

**Purpose**: Return detected operational anomalies (queue spikes, conversion drops, dead zones).

| Field | Expected | Actual | Pass/Fail |
|---|---|---|---|
| Status Code | `200 OK` | `200` | ✅ |
| Response `anomalies` | list (may be empty) | 2 anomalies | ✅ |
| Each anomaly `type` | One of `QUEUE_SPIKE`, `CONVERSION_DROP`, `DEAD_ZONE` | Correct types | ✅ |
| Each anomaly `severity` | One of `LOW`, `MEDIUM`, `HIGH` | Present | ✅ |
| Each anomaly `description` | Non-empty string | Present | ✅ |

**Example Response**:
```json
{
  "anomalies": [
    {
      "type": "DEAD_ZONE",
      "zone_id": "ALPS_GOODNESS",
      "severity": "MEDIUM",
      "description": "No visitor activity in ALPS_GOODNESS for 87 minutes."
    },
    {
      "type": "QUEUE_SPIKE",
      "zone_id": "CASH_COUNTER",
      "severity": "HIGH",
      "description": "Queue depth reached 5 at 14:32 UTC — 2.1σ above baseline."
    }
  ]
}
```

---

### 6. `GET /health`

**Purpose**: Liveness probe for deployment monitoring.

| Field | Expected | Actual | Pass/Fail |
|---|---|---|---|
| Status Code | `200 OK` | `200` | ✅ |
| `status` | `"healthy"` | `"healthy"` | ✅ |
| `db` | `"connected"` | `"connected"` | ✅ |

---

## Summary

| Endpoint | Status Code | Schema Valid | Data Valid | Result |
|---|---|---|---|---|
| `POST /events/ingest` | ✅ 202 | ✅ | ✅ | **PASS** |
| `GET /metrics` | ✅ 200 | ✅ | ✅ | **PASS** |
| `GET /funnel` | ✅ 200 | ✅ | ✅ | **PASS** |
| `GET /heatmap` | ✅ 200 | ✅ | ✅ | **PASS** |
| `GET /anomalies` | ✅ 200 | ✅ | ✅ | **PASS** |
| `GET /health` | ✅ 200 | ✅ | ✅ | **PASS** |

**Overall: 6/6 endpoints PASS — API contract fully validated.**
