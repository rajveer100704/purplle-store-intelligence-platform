"""
api/main.py – FastAPI application entry point.

Mounts all routers, configures CORS, structured logging middleware,
and initialises the database on startup.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..db.database import create_tables
from .ingestion import router as ingest_router
from .metrics import router as metrics_router
from .funnel import router as funnel_router
from .heatmap import router as heatmap_router
from .anomalies import router as anomalies_router
from .health import router as health_router
from .debug import router as debug_router
from .middleware import RequestLogMiddleware

# Configure root logger for JSON output
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup."""
    await create_tables()
    yield


app = FastAPI(
    title="Store Intelligence API",
    description=(
        "Real-time retail analytics powered by CCTV video processing.\n\n"
        "**Endpoints:**\n"
        "- `POST /events/ingest` – ingest event batches (up to 500)\n"
        "- `GET /stores/{id}/metrics` – footfall, conversion, dwell, queue\n"
        "- `GET /stores/{id}/funnel` – customer journey funnel\n"
        "- `GET /stores/{id}/heatmap` – zone engagement heatmap\n"
        "- `GET /stores/{id}/anomalies` – real-time anomaly detection\n"
        "- `GET /health` – system health & stale feed detection\n"
        "- `GET /debug/session/{visitor_id}` – session inspector (DEBUG=true only)\n"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── Middleware (order matters: outermost = first to run) ──────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLogMiddleware)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(ingest_router, tags=["Ingest"])
app.include_router(metrics_router, tags=["Analytics"])
app.include_router(funnel_router, tags=["Analytics"])
app.include_router(heatmap_router, tags=["Analytics"])
app.include_router(anomalies_router, tags=["Analytics"])
app.include_router(health_router, tags=["System"])
app.include_router(debug_router, tags=["Debug"])


@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "Store Intelligence API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "debug_enabled": os.environ.get("DEBUG", "false").lower() == "true",
    }
