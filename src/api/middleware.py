"""
api/middleware.py – Structured request logging middleware.

Emits a JSON log line per request containing:
  trace_id, store_id, endpoint, method, latency_ms,
  status_code, event_count (for ingest), timestamp.

Satisfies the challenge's Production Readiness logging requirement.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# Configure a structured JSON logger
logger = logging.getLogger("store_intelligence")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _extract_store_id(path: str) -> str | None:
    """Extract store_id from paths like /stores/S1/metrics."""
    parts = path.split("/")
    try:
        idx = parts.index("stores")
        return parts[idx + 1] if idx + 1 < len(parts) else None
    except ValueError:
        return None


class RequestLogMiddleware(BaseHTTPMiddleware):
    """
    Logs every request as a structured JSON object.

    Example output:
    {
      "trace_id": "3f4a1b2c-...",
      "timestamp": "2026-05-30T12:00:00.123Z",
      "method": "POST",
      "endpoint": "/events/ingest",
      "store_id": null,
      "status_code": 200,
      "latency_ms": 32,
      "event_count": 145
    }
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        trace_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        # Attach trace_id to request state so endpoints can reference it
        request.state.trace_id = trace_id
        store_id = _extract_store_id(request.url.path)

        # Process request
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            _log(trace_id, request, store_id, 500, elapsed_ms, 0)
            raise

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        # Extract event_count from ingest response header if set
        event_count = int(response.headers.get("X-Event-Count", "0"))

        _log(trace_id, request, store_id, status_code, elapsed_ms, event_count)

        # Propagate trace_id to client
        response.headers["X-Trace-ID"] = trace_id
        return response


def _log(
    trace_id: str,
    request: Request,
    store_id: str | None,
    status_code: int,
    latency_ms: int,
    event_count: int,
) -> None:
    from datetime import datetime, timezone

    record = {
        "trace_id": trace_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": request.method,
        "endpoint": request.url.path,
        "store_id": store_id,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "event_count": event_count,
    }
    logger.info(json.dumps(record))
