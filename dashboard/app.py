"""
dashboard/app.py – Streamlit live dashboard.

Connects to the Store Intelligence API and displays:
  • Per-store footfall counter + conversion rate gauge
  • Customer journey funnel chart
  • Zone engagement heatmap (color grid)
  • Queue depth sparkline (last 60 observations)
  • Anomaly alert panel (live)

Auto-refreshes every 10 seconds.
"""

from __future__ import annotations

import os
import time
from datetime import datetime

import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

import sys
from pathlib import Path
import asyncio
import json

# Add project root to sys.path to enable imports when running on Streamlit Cloud
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

# Try importing the local API logic for direct database fallback
try:
    from src.db.database import AsyncSessionLocal
    from src.api.metrics import get_metrics
    from src.api.funnel import get_funnel
    from src.api.heatmap import get_heatmap
    from src.api.anomalies import get_anomalies
    from src.api.health import health_check
    LOCAL_DB_AVAILABLE = True
except Exception as e:
    LOCAL_DB_AVAILABLE = False

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")
REFRESH_SECONDS = 10

st.set_page_config(
    page_title="Store Intelligence Dashboard",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# API helpers
# ──────────────────────────────────────────────────────────────────────────────

def api_get(path: str) -> dict | None:
    # First attempt: HTTP request to FastAPI backend
    try:
        r = requests.get(f"{API_BASE}{path}", timeout=2)
        r.raise_for_status()
        return r.json()
    except Exception as http_err:
        # Second attempt: Direct SQLite DB queries via imports (Standalone Mode)
        if LOCAL_DB_AVAILABLE:
            try:
                async def run_query():
                    async with AsyncSessionLocal() as db:
                        if path == "/health":
                            res = await health_check(db)
                            return json.loads(res.model_dump_json())
                        elif path.startswith("/stores/") and path.endswith("/metrics"):
                            store_id = path.split("/")[2]
                            res = await get_metrics(store_id, db)
                            return json.loads(res.model_dump_json())
                        elif path.startswith("/stores/") and path.endswith("/funnel"):
                            store_id = path.split("/")[2]
                            res = await get_funnel(store_id, db)
                            return json.loads(res.model_dump_json())
                        elif path.startswith("/stores/") and path.endswith("/heatmap"):
                            store_id = path.split("/")[2]
                            res = await get_heatmap(store_id, db)
                            return json.loads(res.model_dump_json())
                        elif path.startswith("/stores/") and path.endswith("/anomalies"):
                            store_id = path.split("/")[2]
                            res = await get_anomalies(store_id, db)
                            return json.loads(res.model_dump_json())
                return asyncio.run(run_query())
            except Exception as db_err:
                st.sidebar.error(f"Local DB query error: {db_err}")
                return None
        st.sidebar.error(f"API unreachable and no local DB fallback: {http_err}")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar – store selector & health
# ──────────────────────────────────────────────────────────────────────────────

st.sidebar.title("🏪 Store Intelligence")
st.sidebar.markdown("---")

health = api_get("/health") or {}
status = health.get("status", "UNKNOWN")
status_color = "🟢" if status == "OK" else "🔴"
st.sidebar.markdown(f"**API Status:** {status_color} {status}")

last_events = health.get("last_event_per_store", {})
store_ids = sorted(last_events.keys()) if last_events else ["S1", "S2", "S3", "S4", "S5"]

if not store_ids:
    store_ids = ["S1"]

selected_store = st.sidebar.selectbox("Select Store", store_ids)

stale = health.get("stale_feeds", [])
if selected_store in stale:
    st.sidebar.warning(f"⚠️ Feed for {selected_store} is stale (>10 min)")

db_count = health.get("db_event_count", 0)
st.sidebar.metric("Total Events in DB", f"{db_count:,}")
st.sidebar.caption(f"Last refresh: {datetime.now().strftime('%H:%M:%S')}")

# ──────────────────────────────────────────────────────────────────────────────
# Main dashboard
# ──────────────────────────────────────────────────────────────────────────────

st.title(f"📊 Store {selected_store} – Live Analytics")

# ── Row 1: Key metrics ────────────────────────────────────────────────────────
metrics = api_get(f"/stores/{selected_store}/metrics") or {}

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric(
        "👥 Footfall",
        metrics.get("footfall", "--"),
        help="Unique customer entries (excludes staff)",
    )
with col2:
    st.metric(
        "🛒 Conversion Rate",
        f"{metrics.get('conversion_rate', 0):.1f}%",
        help="Customers who reached checkout / total visitors",
    )
with col3:
    st.metric(
        "🕐 Queue Depth",
        metrics.get("queue_depth", "--"),
        help="Current number of people in billing queue",
    )
with col4:
    st.metric(
        "❌ Abandonment Rate",
        f"{metrics.get('abandonment_rate', 0):.1f}%",
        help="Queue join without purchase / total queue joins",
    )
with col5:
    unique = metrics.get("unique_visitors", "--")
    st.metric("🆔 Unique Visitors", unique)

st.markdown("---")

# ── Row 2: Funnel + Heatmap ───────────────────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("🔽 Customer Journey Funnel")
    funnel = api_get(f"/stores/{selected_store}/funnel") or {}

    if funnel:
        stages = ["Entry", "Zone Visit", "Billing", "Purchase"]
        values = [
            funnel.get("entry", 0),
            funnel.get("zone_visit", 0),
            funnel.get("billing", 0),
            funnel.get("purchase", 0),
        ]

        fig_funnel = go.Figure(go.Funnel(
            y=stages,
            x=values,
            textinfo="value+percent initial",
            marker=dict(color=["#4F46E5", "#7C3AED", "#A855F7", "#22C55E"]),
        ))
        fig_funnel.update_layout(
            height=350,
            margin=dict(l=20, r=20, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_funnel, use_container_width=True)

        dropoff = funnel.get("dropoff", {})
        d1 = dropoff.get("entry_to_zone", 0)
        d2 = dropoff.get("zone_to_billing", 0)
        d3 = dropoff.get("billing_to_purchase", 0)
        st.caption(
            f"Dropoff: Entry→Zone **{d1}**  |  Zone→Billing **{d2}**  |  Billing→Purchase **{d3}**"
        )
    else:
        st.info("No funnel data yet. Run the pipeline and ingest events.")

with col_right:
    st.subheader("🗺️ Zone Heatmap")
    heatmap = api_get(f"/stores/{selected_store}/heatmap") or {}
    zones_data = heatmap.get("zones", {})

    if zones_data:
        zone_names = list(zones_data.keys())
        visits = [zones_data[z]["visits"] for z in zone_names]
        dwells = [zones_data[z]["avg_dwell_s"] for z in zone_names]
        scores = [zones_data[z]["score"] for z in zone_names]

        fig_heat = px.bar(
            x=zone_names,
            y=scores,
            color=scores,
            color_continuous_scale="Viridis",
            labels={"x": "Zone", "y": "Engagement Score", "color": "Score"},
            text=[f"{s}/100" for s in scores],
        )
        fig_heat.update_layout(
            height=300,
            margin=dict(l=20, r=20, t=20, b=20),
            coloraxis_showscale=False,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_heat, use_container_width=True)

        # Zone detail table
        zone_table = {
            "Zone": zone_names,
            "Visits": visits,
            "Avg Dwell (s)": dwells,
            "Score": scores,
        }
        st.dataframe(zone_table, use_container_width=True, hide_index=True)
    else:
        st.info("No zone data yet.")

st.markdown("---")

# ── Row 3: Dwell bar chart ────────────────────────────────────────────────────
st.subheader("⏱ Avg Dwell by Zone (seconds)")
dwell_data = metrics.get("avg_dwell_per_zone", {})
if dwell_data:
    fig_dwell = px.bar(
        x=list(dwell_data.keys()),
        y=list(dwell_data.values()),
        labels={"x": "Zone", "y": "Avg Dwell (s)"},
        color=list(dwell_data.values()),
        color_continuous_scale="Blues",
    )
    fig_dwell.update_layout(
        height=250,
        margin=dict(l=20, r=20, t=10, b=20),
        coloraxis_showscale=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_dwell, use_container_width=True)
else:
    st.info("No dwell data yet.")

st.markdown("---")

# ── Row 4: Anomaly panel ──────────────────────────────────────────────────────
st.subheader("🚨 Active Anomalies")
anomalies_data = api_get(f"/stores/{selected_store}/anomalies") or {}
anomaly_list = anomalies_data.get("anomalies", [])

if anomaly_list:
    for a in anomaly_list:
        severity = a.get("severity", "INFO")
        icon = {"INFO": "ℹ️", "WARN": "⚠️", "CRITICAL": "🔴"}.get(severity, "ℹ️")
        color = {"INFO": "blue", "WARN": "orange", "CRITICAL": "red"}.get(severity, "blue")

        with st.container():
            cols = st.columns([0.05, 0.25, 0.7])
            cols[0].markdown(icon)
            cols[1].markdown(f"**{a['type']}**  \n`{severity}`")
            cols[2].markdown(a.get("action", ""))
        st.markdown("")
else:
    st.success("✅ No active anomalies detected.")

# ── Auto-refresh ──────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(f"Auto-refreshing every {REFRESH_SECONDS}s · API: {API_BASE}")

# Use st.rerun after delay for auto-refresh
time.sleep(REFRESH_SECONDS)
st.rerun()
