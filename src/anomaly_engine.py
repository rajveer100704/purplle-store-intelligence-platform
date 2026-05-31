"""
anomaly_engine.py – Three-type anomaly detection engine.

Detects the three anomaly types required by the challenge:

  1. BILLING_QUEUE_SPIKE  – queue depth exceeds rolling mean + k·σ
  2. CONVERSION_DROP      – today's conversion < (7-day avg − threshold%)
  3. DEAD_ZONE            – a zone with no activity for the configured window

Returns structured anomaly dicts with severity (INFO/WARN/CRITICAL)
and a suggested remediation action.
"""

from __future__ import annotations

import os
import statistics
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
from .config import QUEUE_SPIKE_SIGMA, CONVERSION_DROP_PCT, DEAD_ZONE_MINUTES



# ──────────────────────────────────────────────────────────────────────────────
# Anomaly engine
# ──────────────────────────────────────────────────────────────────────────────

class AnomalyEngine:
    """
    Stateful anomaly engine for a single store.

    Feed it real-time observations via update_* methods and call
    detect() to get the current list of active anomalies.
    """

    QUEUE_WINDOW_MINUTES = 30   # rolling window for queue spike detection
    HISTORY_DAYS = 7            # days of conversion history to keep

    def __init__(self, store_id: str, zone_ids: list[str]) -> None:
        self.store_id = store_id
        self.zone_ids = zone_ids

        # Queue depth history: list of (unix_epoch, depth)
        self._queue_history: deque[tuple[float, int]] = deque(maxlen=10_000)

        # Conversion rate history: list of (date_str, rate%)
        self._conversion_history: list[tuple[str, float]] = []

        # Zone activity: zone_id → last activity epoch
        self._zone_last_activity: dict[str, float] = {
            z: datetime.now(timezone.utc).timestamp() for z in zone_ids
        }

        # Load store config to get brand mapping
        from .layout.parser import load_store_config
        from .config import STORE_CONFIG_PATH
        config = load_store_config(STORE_CONFIG_PATH, store_id)
        self.brand_map = config.zone_brand_map() if config else {}

    # ── Observation feeds ────────────────────────────────────────────────────

    def update_queue_depth(self, depth: int, ts: float | None = None) -> None:
        """Record a new queue depth observation (unix epoch timestamp)."""
        ts = ts or datetime.now(timezone.utc).timestamp()
        self._queue_history.append((ts, depth))

    def update_conversion_rate(self, rate: float, date_str: str | None = None) -> None:
        """Record today's conversion rate for 7-day baseline computation."""
        date_str = date_str or datetime.now(timezone.utc).date().isoformat()
        # Overwrite if same date already recorded
        self._conversion_history = [
            (d, r) for (d, r) in self._conversion_history if d != date_str
        ]
        self._conversion_history.append((date_str, rate))
        # Keep only last HISTORY_DAYS + 1 days
        self._conversion_history.sort()
        self._conversion_history = self._conversion_history[-(self.HISTORY_DAYS + 1):]

    def update_zone_activity(self, zone_id: str, ts: float | None = None) -> None:
        """Called whenever any event occurs in a zone."""
        ts = ts or datetime.now(timezone.utc).timestamp()
        if zone_id in self._zone_last_activity:
            self._zone_last_activity[zone_id] = ts

    # ── Detection ────────────────────────────────────────────────────────────

    def detect(self) -> list[dict[str, Any]]:
        """Run all anomaly detectors and return active anomaly dicts."""
        anomalies: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).timestamp()

        anomalies.extend(self._detect_queue_spike(now))
        anomalies.extend(self._detect_conversion_drop())
        anomalies.extend(self._detect_dead_zones(now))

        return anomalies

    def _detect_queue_spike(self, now: float) -> list[dict[str, Any]]:
        """BILLING_QUEUE_SPIKE: depth > mean + k·σ over rolling 30-min window."""
        cutoff = now - (self.QUEUE_WINDOW_MINUTES * 60)
        recent = [d for (ts, d) in self._queue_history if ts >= cutoff]

        if len(recent) < 5:
            return []  # not enough data

        mean = statistics.mean(recent)
        try:
            stdev = statistics.stdev(recent)
        except statistics.StatisticsError:
            return []

        threshold = mean + QUEUE_SPIKE_SIGMA * stdev
        current = recent[-1] if recent else 0

        if current <= threshold:
            return []

        # Severity
        severity = "WARN"
        if current > threshold * 1.5:
            severity = "CRITICAL"

        return [{
            "type": "BILLING_QUEUE_SPIKE",
            "severity": severity,
            "store_id": self.store_id,
            "value": current,
            "threshold": round(threshold, 1),
            "mean": round(mean, 1),
            "stddev": round(stdev, 1),
            "action": (
                "Open another register immediately"
                if severity == "CRITICAL"
                else "Consider opening an additional checkout lane"
            ),
        }]

    def _detect_conversion_drop(self) -> list[dict[str, Any]]:
        """CONVERSION_DROP: today's rate < (7-day avg − threshold%)."""
        if len(self._conversion_history) < 2:
            return []

        today_str = datetime.now(timezone.utc).date().isoformat()
        today_entry = next(
            ((d, r) for (d, r) in self._conversion_history if d == today_str), None
        )
        if today_entry is None:
            return []

        today_rate = today_entry[1]
        historical = [r for (d, r) in self._conversion_history if d != today_str]
        if not historical:
            return []

        baseline = statistics.mean(historical)
        drop = baseline - today_rate

        if drop < CONVERSION_DROP_PCT:
            return []

        severity = "CRITICAL" if drop >= CONVERSION_DROP_PCT * 2 else "WARN"

        return [{
            "type": "CONVERSION_DROP",
            "severity": severity,
            "store_id": self.store_id,
            "value": round(today_rate, 1),
            "baseline": round(baseline, 1),
            "drop_pct": round(drop, 1),
            "action": "Check promotions, staff coverage, or product availability",
        }]

    def _detect_dead_zones(self, now: float) -> list[dict[str, Any]]:
        """DEAD_ZONE: no activity in a zone for DEAD_ZONE_MINUTES."""
        threshold_secs = DEAD_ZONE_MINUTES * 60
        anomalies = []

        for zone_id, last_active in self._zone_last_activity.items():
            idle_secs = now - last_active
            if idle_secs >= threshold_secs:
                idle_min = int(idle_secs // 60)
                brand_name = self.brand_map.get(zone_id)
                zone_desc = f"'{brand_name}' ({zone_id})" if brand_name else f"'{zone_id}'"
                anomalies.append({
                    "type": "DEAD_ZONE",
                    "severity": "INFO",
                    "store_id": self.store_id,
                    "zone": zone_id,
                    "idle_minutes": idle_min,
                    "action": (
                        f"Zone {zone_desc} has had no visitors for {idle_min} min. "
                        "Consider repositioning display or signage."
                    ),
                })

        return anomalies
