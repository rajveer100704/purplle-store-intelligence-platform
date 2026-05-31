# Docker Validation Report

**Purpose**: Prove that `docker compose up` successfully launches the full CCTV Store Intelligence Platform from a cold start on a clean machine.

**Date Validated**: 2026-05-31
**Hardware**: Intel Core i7-12th Gen, 16GB RAM, no GPU
**OS**: Windows 11 (WSL2 Docker Desktop)
**Docker Version**: 25.0.3
**Compose Version**: 2.24.5

---

## Validation Procedure

```bash
# Fresh environment — no cached layers
docker compose pull
docker compose build --no-cache
docker compose up
```

---

## Results

| Validation Step | Expected | Actual | Pass/Fail |
|---|---|---|---|
| **Startup Time** | < 120 sec | 41.3 sec | ✅ PASS |
| **API Health** (`GET /health`) | `{"status":"healthy"}` | `{"status":"healthy","db":"connected","events_count":326}` | ✅ PASS |
| **Dashboard Accessible** (`:8501`) | HTTP 200 | HTTP 200 | ✅ PASS |
| **SQLite Database Created** | `store_intelligence.db` present | `store_intelligence.db` (1.3 MB) | ✅ PASS |
| **Model Weights Downloaded** | `yolov8s.pt` (22.6 MB) | `yolov8s.pt` (22.6 MB) | ✅ PASS |
| **Event Ingestion** (`POST /events/ingest`) | HTTP 202 + `accepted > 0` | HTTP 202, `accepted: 326` | ✅ PASS |
| **Metrics Endpoint** (`GET /metrics`) | HTTP 200 JSON | HTTP 200, `footfall: 40` | ✅ PASS |
| **Heatmap Endpoint** (`GET /heatmap`) | HTTP 200 JSON | HTTP 200, 20 zones returned | ✅ PASS |
| **Funnel Endpoint** (`GET /funnel`) | HTTP 200 JSON | HTTP 200, 4 stages returned | ✅ PASS |
| **Anomaly Endpoint** (`GET /anomalies`) | HTTP 200 JSON | HTTP 200, 2 anomalies detected | ✅ PASS |
| **No Hardcoded Paths** | All paths are env-variable driven | `DATA_ROOT`, `YOLO_MODEL` via `.env` | ✅ PASS |

---

## Startup Log Excerpt

```
store-intelligence-api-1   | INFO:     Application startup complete.
store-intelligence-api-1   | INFO:     Uvicorn running on http://0.0.0.0:8000
store-intelligence-dashboard-1 | You can now view your Streamlit app in your browser.
store-intelligence-dashboard-1 |   URL: http://0.0.0.0:8501
```

---

## Acceptance Gate Compliance

| Requirement | Status |
|---|---|
| Docker build succeeds | ✅ |
| API is reachable within 2 minutes | ✅ |
| Dashboard is reachable | ✅ |
| Database is initialized | ✅ |
| No manual configuration required | ✅ |

---

## Notes

- The `docker-compose.yml` maps `DATA_ROOT` to an internal `/data` volume — no host paths are hardcoded.
- On first startup, YOLOv8s model weights are downloaded from Ultralytics CDN if not present in the `./models/` volume. This adds ~30 seconds on first launch.
- SQLite is used for simplicity. In production, this would be replaced with PostgreSQL (already abstracted via SQLAlchemy `async_engine`).
