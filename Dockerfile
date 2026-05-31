FROM python:3.11-slim

# Install system-level dependencies (OpenCV, ffmpeg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 \
    ffmpeg libgl1 git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ── Pre-download all model weights at build time ──────────────────────────────
# This ensures docker compose up works with NO internet access at runtime.
# YOLOv8s weights (~22 MB)
RUN python -c "from ultralytics import YOLO; YOLO('yolov8s.pt'); print('YOLOv8s weights downloaded')"

# OSNet_x0_25 weights via torchreid (auto-downloaded to ~/.cache/torch)
# Graceful: if torchreid not available, skip (ReID falls back to random embeddings)
RUN python -c "\
try:\
    import torchreid;\
    torchreid.models.build_model(name='osnet_x0_25', num_classes=1000, pretrained=True);\
    print('OSNet weights downloaded');\
except Exception as e:\
    print(f'OSNet download skipped: {e} (fallback mode will be used)');\
" || true

# ── Create required directories ───────────────────────────────────────────────
RUN mkdir -p /app/output /app/data

ENV PYTHONPATH=/app
ENV YOLO_DEVICE=cpu

EXPOSE 8000

# Healthcheck: polls /health every 30s
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
