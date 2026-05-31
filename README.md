# Store Intelligence API & Dashboard

Real-time retail analytics powered by CCTV video processing.

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

### Step 4 – Run the detection pipeline
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

### Step 5 – Query the API
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
├── scanner.py           # Dataset validator
├── detector.py          # YOLOv8s person detection
├── tracker.py           # ByteTrack multi-object tracking
├── reid.py              # OSNet ReID cross-camera identity
├── state_machine.py     # VisitorStateMachine (6 states)
├── session_manager.py   # Visitor session lifecycle
├── event_emitter.py     # Event generation (8 types)
├── pos_correlator.py    # POS ↔ session correlation
├── anomaly_engine.py    # 3-type anomaly detection
├── pipeline.py          # Main orchestrator
├── replay.py            # Live replay mode
├── api/                 # FastAPI endpoints
└── db/                  # SQLAlchemy ORM

dashboard/app.py         # Streamlit dashboard
tests/                   # pytest test suite
DESIGN.md                # Architecture & data flow
CHOICES.md               # Key technical decisions
```

---

## Requirements

- Python 3.11+
- Docker & Docker Compose (for containerised deployment)
- GPU optional (CPU mode supported via `YOLO_DEVICE=cpu` in `.env`)
