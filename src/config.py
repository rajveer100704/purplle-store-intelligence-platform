"""
config.py – Centralized configuration settings and thresholds.
"""

import os

# ── ReID settings ─────────────────────────────────────────────────────────────
REID_MATCH_THRESHOLD = float(os.environ.get("REID_MATCH_THRESHOLD", "0.75"))
REID_NEW_ID_THRESHOLD = float(os.environ.get("REID_NEW_ID_THRESHOLD", "0.55"))
REID_MODEL_NAME = os.environ.get("REID_MODEL", "osnet_x0_25")

# ── Tracker & Lifecycle settings ──────────────────────────────────────────────
TRACK_LOST_TIMEOUT = float(os.environ.get("TRACK_LOST_TIMEOUT", "5.0"))
OCCLUSION_TIMEOUT = float(os.environ.get("OCCLUSION_TIMEOUT", "60.0"))

# ── Staff Heuristics ──────────────────────────────────────────────────────────
STAFF_SCORE_THRESHOLD = int(os.environ.get("STAFF_SCORE_THRESHOLD", "3"))
STAFF_HUE_RANGE = (100, 140)  # blue-ish uniform (HSV hue range)
STAFF_PRESENCE_RATIO_SINGLE = 0.70
STAFF_PRESENCE_RATIO_MULTI = 0.20
STORE_OPEN_HOUR = int(os.environ.get("STORE_OPEN_HOUR", "9"))

# ── Anomaly Detection ─────────────────────────────────────────────────────────
QUEUE_SPIKE_SIGMA = float(os.environ.get("QUEUE_SPIKE_SIGMA", "2.0"))
CONVERSION_DROP_PCT = float(os.environ.get("CONVERSION_DROP_PCT", "15.0"))
DEAD_ZONE_MINUTES = float(os.environ.get("DEAD_ZONE_MINUTES", "60.0"))

# ── Store Configuration and POS Settings ──────────────────────────────────────
STORE_CONFIG_PATH = os.environ.get("STORE_CONFIG_PATH", "src/layout/store_config.json")
POS_CSV_PATH = os.environ.get("POS_CSV_PATH", "data/pos_transactions.csv")
POS_MATCH_WINDOW = float(os.environ.get("POS_MATCH_WINDOW", "300.0"))  # 5 minutes in seconds

