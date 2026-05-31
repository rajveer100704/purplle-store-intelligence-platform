# Reproducibility Report

**Purpose**: Document the exact environment, package versions, and hardware configuration required to reproduce the CCTV Store Intelligence Pipeline results.

---

## Environment

| Component | Value |
|---|---|
| **Python Version (Tested)** | 3.14.0 (CPython) |
| **Python Version (Compatible)** | 3.11, 3.12, 3.13, 3.14 (see compatibility table below) |
| **Operating System** | Windows 11 Home (Build 22631) |
| **CPU** | Intel Core i7-12700H (14 cores, 20 threads) |
| **RAM** | 16 GB DDR5 |
| **GPU** | None (CPU-only inference) |
| **Storage** | SSD NVMe |

### Python Version Compatibility

| Python Version | Status | Notes |
|---|---|---|
| **3.14** | ✅ Tested | Primary development environment |
| **3.13** | ✅ Expected | All dependencies support 3.13+ |
| **3.12** | ✅ Expected | PyTorch 2.3 and Ultralytics 8.x support 3.12 |
| **3.11** | ✅ Expected | Most stable for `torchreid` install via pip |
| **3.10** | ⚠️ Untested | `match` statements used in codebase require ≥3.10 |
| **3.9 or below** | ❌ Not supported | `asyncio` and `match` require ≥3.10 |

> **Reviewer note**: If running on Python 3.11 or 3.12, all core dependencies install without changes. If you encounter `torchreid` install issues, you can disable ReID by setting `REID_ENABLED=false` in `.env` — the pipeline will then assign new IDs per-camera (tracking still works, cross-camera re-identification is disabled).

---

## Core Dependency Versions

| Package | Version | Purpose |
|---|---|---|
| `ultralytics` | 8.3.x | YOLOv8s person detection |
| `torch` | 2.3.0+cpu | PyTorch CPU backend |
| `torchvision` | 0.18.0+cpu | Image transforms for ReID |
| `torchreid` | 1.4.0 | OSNet appearance feature extractor |
| `supervision` | 0.28.0 | ByteTrack implementation |
| `opencv-python` | 4.10.x | Video I/O, frame processing |
| `shapely` | 2.0.6 | Zone polygon geometry |
| `pandas` | 2.2.3 | POS CSV parsing |
| `fastapi` | 0.115.x | REST API framework |
| `uvicorn` | 0.32.x | ASGI server |
| `sqlalchemy` | 2.0.x | ORM + async DB access |
| `aiosqlite` | 0.20.0 | Async SQLite driver |
| `streamlit` | 1.40.x | Dashboard UI |
| `rich` | 13.9.x | Terminal progress output |

**Full pinned requirements**: see `requirements.txt`.

---

## Model Weights

| Model | File | Size | Source |
|---|---|---|---|
| YOLOv8s | `yolov8s.pt` | 22.6 MB | Auto-downloaded from Ultralytics CDN |
| OSNet x0.25 | `osnet_x0_25_imagenet.pth` | ~3.2 MB | Auto-downloaded via `torchreid` |

> **Note**: If `gdown` (required by `torchreid` for checkpoint download) is not installed, the system falls back to random embeddings for ReID. This means cross-camera ReID is disabled — all visitors are assigned fresh IDs per camera. Install `gdown` to enable real ReID: `pip install gdown`.

---

## Random Seeds

| Component | Seed | Location |
|---|---|---|
| Visitor ID generation | UUID4 (non-deterministic) | `src/reid.py` |
| Demo generator | `random.seed(42)` | `scripts/generate_demo.py` |
| ReID calibration | No fixed seed (uses real crops) | `scripts/calibrate_reid.py` |

> **Reproducibility Note**: The demo generator uses `random.seed(42)` to produce stable synthetic visitor journeys. The real pipeline uses UUID4 for visitor IDs, which is non-deterministic by design.

---

## Pipeline Configuration

| Parameter | Default Value | Environment Variable |
|---|---|---|
| YOLO model | `yolov8s.pt` | `YOLO_MODEL` |
| YOLO confidence | `0.25` | `YOLO_CONF` |
| YOLO device | `cpu` | `YOLO_DEVICE` |
| ReID match threshold | `0.75` | `REID_MATCH_THRESHOLD` |
| ReID new ID threshold | `0.55` | `REID_NEW_ID_THRESHOLD` |
| Track lost timeout | `5.0s` | `TRACK_LOST_TIMEOUT` |
| Occlusion timeout | `60.0s` | `OCCLUSION_TIMEOUT` |
| POS match window | `300.0s` | `POS_MATCH_WINDOW` |
| Store open hour | `9` | `STORE_OPEN_HOUR` |
| Staff score threshold | `3` | `STAFF_SCORE_THRESHOLD` |
| Database URL | `sqlite+aiosqlite:///store_intelligence.db` | `DATABASE_URL` |

---

## Data Used

| Resource | Location | Description |
|---|---|---|
| CCTV Videos | `C:\Users\BIT\OneDrive\Documents\CCTV\CCTV Footage\` | 5 MP4 files (CAM 1–5), 1920×1080, 25–30fps |
| Store Layout | `src/layout/store_config.json` | Zone polygon definitions, entry/exit lines |
| POS Transactions | `data/pos_transactions.csv` | Transaction timestamps and amounts |

---

## Validation Configuration

The real CCTV run that produced `results/real_events.jsonl` was executed with this exact configuration:

```
python -m src.pipeline \
  --data "C:\Users\BIT\OneDrive\Documents\CCTV\CCTV Footage" \
  --output results/real_events.jsonl \
  --skip-frames 10
```

| Parameter | Value Used | Env Variable |
|---|---|---|
| `--skip-frames` | **10** | N/A (CLI arg) |
| `YOLO_CONF` | **0.25** | `YOLO_CONF` |
| `REID_MATCH_THRESHOLD` | **0.75** | `REID_MATCH_THRESHOLD` |
| `REID_NEW_ID_THRESHOLD` | **0.55** | `REID_NEW_ID_THRESHOLD` |
| `YOLO_DEVICE` | **cpu** | `YOLO_DEVICE` |
| `TRACK_LOST_TIMEOUT` | **5.0s** | `TRACK_LOST_TIMEOUT` |
| `POS_MATCH_WINDOW` | **300.0s** | `POS_MATCH_WINDOW` |
| `STORE_OPEN_HOUR` | **9** | `STORE_OPEN_HOUR` |

> **Important**: If you change `--skip-frames` from 10 to a lower value, event counts will increase (more frames = more detections). The 326-event count and 131-visitor count are specific to `--skip-frames 10`. Reproducibility requires using the same value.

---

## Reproduction Steps

```bash
# 1. Clone / unzip the project
cd Purplle_Hackathon

# 2. Install dependencies
pip install -r requirements.txt
pip install gdown  # optional: enables real ReID

# 3. Place CCTV footage in DATA_ROOT
# Default: C:\Users\BIT\OneDrive\Documents\CCTV\CCTV Footage\

# 4. Run one-command demo
python scripts/run_demo.py

# 5. Or run pipeline directly
python -m src.pipeline --data "C:\Users\BIT\OneDrive\Documents\CCTV\CCTV Footage" --output results/real_events.jsonl --skip-frames 10

# 6. Start API and dashboard
uvicorn src.api.main:app --port 8000 &
streamlit run dashboard/app.py
```

---

## Known Reproducibility Gaps

| Issue | Impact | Mitigation |
|---|---|---|
| `gdown` not installed | ReID disabled; all visitors get new IDs per camera | Install `gdown` |
| Different camera clock offsets | POS correlation window may miss matches | Use NTP-synced hardware in production |
| `ByteTrack` deprecated warning | Functional but uses legacy API | Upgrade to `supervision >= 0.30.0` when released |
| YOLO model download requires internet | First run needs connectivity | Pre-bundle `yolov8s.pt` in Docker image |
