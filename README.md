# Store Intelligence API & Dashboard

Real-time retail analytics powered by CCTV video processing.

---

### 🚀 Generalization Validation Summary
*   **Physical Stores Validated**: 3 distinct retail layout locations
*   **CCTV Camera Streams**: 13 active cameras processed
*   **Code Changes Between Stores**: **0** (completely configured via `StoreRegistry` metadata)

*   **Brigade Road (ST1008)**: 5 cameras, 131 unique visitors (manual brand polygons & POS-matched)
*   **Store 1 (STORE_1)**: 4 cameras, 130 unique visitors (auto-generated zones & queue proxy)
*   **Store 2 (STORE_2)**: 4 cameras, 111 unique visitors (auto-generated zones & queue proxy, dual entry)

---

### 🌐 View Hosted Live Dashboard (No Setup Required)
You can view the fully populated, production-ready dashboard instantly on Streamlit Community Cloud:
👉 **[Live App Link](https://purplle-store-intelligence-platform-auydydswabnuuscjznvlpd.streamlit.app)**
*(Select **`ST1008`** in the left sidebar dropdown to load the Brigade Road store data).*

---

## 5-Step Setup (Local Development)

### Step 1 – Clone the repository
```bash
git clone <your-repo-url>
cd Purplle_Hackathon
```

### Step 2 – Configure environment
```bash
cp .env.example .env
# Edit DATA_ROOT to point to your CCTV footage directory
# Default: C:\Users\BIT\OneDrive\Documents\CCTV\CCTV Footage
```

### Step 3 – Start the API (Docker)
```bash
docker compose up -d
# API: http://localhost:8000
# Dashboard: http://localhost:8501
# Docs: http://localhost:8000/docs
```

Or run locally without Docker:
```bash
pip install -r requirements.txt
uvicorn src.api.main:app --reload --port 8000
```

### Step 4 – Run the E2E Demo Orchestrator & Validator
To quickly validate the entire pipeline, run the master orchestrator script:
```bash
python scripts/run_demo.py
```
This script will automatically:
- Scan the CCTV video dataset and run camera validations.
- Perform ReID threshold empirical sweep calibration.
- **Automatically rebuild the local SQLite database (`store_intelligence.db`)** if it is missing, and populate it with simulated customer journeys matched against real POS transaction logs.
- Run the real CCTV validators for all 3 stores (`ST1008`, `STORE_1`, and `STORE_2`).
- Generate comparative cross-store analytics and compile all validation reports.
- Populate dashboard metrics and copy screenshots.

### Step 5 – Run the manual detection pipeline (Optional)
```bash
# Scan dataset and validate
python -m src.scanner --data "C:\Users\BIT\OneDrive\Documents\CCTV\CCTV Footage"

# Run full pipeline (outputs events.jsonl)
python -m src.pipeline --data "C:\Users\BIT\OneDrive\Documents\CCTV\CCTV Footage" \
                        --output output/events.jsonl \
                        --ingest-url http://localhost:8000

# Or test with a single video
python -m src.pipeline --video path/to/video.mp4 --dry-run
```

### Step 6 – Query the API
```bash
# Check system health
curl http://localhost:8000/health | python -m json.tool

# Store metrics
curl http://localhost:8000/stores/S1/metrics | python -m json.tool

# Customer journey funnel
curl http://localhost:8000/stores/S1/funnel | python -m json.tool

# Zone heatmap
curl http://localhost:8000/stores/S1/heatmap | python -m json.tool

# Active anomalies
curl http://localhost:8000/stores/S1/anomalies | python -m json.tool

# Ingest events manually
curl -X POST http://localhost:8000/events/ingest \
     -H "Content-Type: application/json" \
     -d @output/events.jsonl
```

---

## Bonus: Live Replay Mode
```bash
# Replay generated events into the API at 10x speed
python -m src.replay --events output/events.jsonl --speed 10x --url http://localhost:8000

# Open dashboard to see live updates
# http://localhost:8501
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/events/ingest` | Ingest up to 500 events per call |
| `GET` | `/stores/{id}/metrics` | Footfall, conversion, dwell, queue |
| `GET` | `/stores/{id}/funnel` | Customer journey funnel |
| `GET` | `/stores/{id}/heatmap` | Zone engagement heatmap |
| `GET` | `/stores/{id}/anomalies` | Real-time anomaly detection |
| `GET` | `/health` | System health & stale feed detection |
| `GET` | `/docs` | Interactive Swagger UI |

---

## Event Types

| Event | When Emitted |
|-------|-------------|
| `ENTRY` | Person crosses entry line for first time |
| `EXIT` | Person crosses exit boundary |
| `ZONE_ENTER` | Person enters a named zone polygon |
| `ZONE_EXIT` | Person leaves a named zone polygon |
| `ZONE_DWELL` | 30s of continuous zone presence (repeating) |
| `BILLING_QUEUE_JOIN` | Enters billing zone while queue_depth > 0 |
| `BILLING_QUEUE_ABANDON` | Leaves billing zone without purchase |
| `REENTRY` | Person re-enters after a prior EXIT |

---

## Running Tests
```bash
pytest tests/ -v
```

---

## Project Structure

```
src/
├── api/                 # FastAPI router and endpoints
├── db/                  # SQLAlchemy models and connection
├── layout/              # Polygon layout registry and scaling
├── pos/                 # POS receipt parsing and correlation
├── analytics/           # Cross-store analytics engine
├── detector.py          # YOLOv8s person detector
├── tracker.py           # ByteTrack multi-object tracker
├── reid.py              # OSNet cross-camera re-identification
├── state_machine.py     # Finite State Machine for visitor journey (6 states)
├── session_manager.py   # Session lifecycle and staff filtering
├── event_emitter.py     # Event generator for API ingestion (8 types)
├── anomaly_engine.py    # Anomaly detector (queue spikes, dead zones)
├── pipeline.py          # Main E2E video processing pipeline
└── replay.py            # Event replay utility

dashboard/               # Streamlit evaluation dashboard
scripts/                 # Orchestrators and generator tools
tests/                   # Pytest verification suite (82 checks)
docs/                    # Comprehensive system documentation
assets/                  # Screenshots, layouts, and slides
archive/                 # Development task files and scratch files
```

---

## Requirements

- Python 3.11+
- Docker & Docker Compose (for containerised deployment)
- GPU optional (CPU mode supported via `YOLO_DEVICE=cpu` in `.env`)
