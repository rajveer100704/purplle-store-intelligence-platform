"""
dashboard/app.py - Streamlit live dashboard.

Connects to the Store Intelligence API and displays:
  * Per-store footfall counter + conversion rate gauge
  * Customer journey funnel chart
  * Zone engagement heatmap (color grid)
  * Queue depth sparkline (last 60 observations)
  * Anomaly alert panel (live)
  * Cross-Store Comparison tab

Auto-refreshes every 10 seconds.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import json

import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# Add project root to sys.path to enable imports when running on Streamlit Cloud
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# ──────────────────────────────────────────────────────────────────────────────
# Database path resolution
# ──────────────────────────────────────────────────────────────────────────────

DB_PATH = Path(project_root) / "store_intelligence.db"


def _get_db_conn() -> sqlite3.Connection:
    """Return a synchronous SQLite connection. Works in any thread/async context."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_db_populated() -> None:
    """
    Run populate_all_stores.py as a subprocess if the DB is missing or empty.
    Using subprocess avoids any asyncio event-loop conflicts with Streamlit.
    """
    if DB_PATH.exists():
        # Check if STORE_1 events exist
        try:
            conn = _get_db_conn()
            cur = conn.execute(
                "SELECT COUNT(*) FROM events WHERE store_id='STORE_1'"
            )
            count = cur.fetchone()[0]
            conn.close()
            if count > 0:
                return  # DB is already fully populated
        except Exception:
            pass  # DB might not have tables yet

    # Run the populate script as a subprocess (no asyncio conflict)
    script = Path(project_root) / "scripts" / "populate_all_stores.py"
    if script.exists():
        try:
            subprocess.run(
                [sys.executable, str(script), "--skip-demo"],
                cwd=project_root,
                timeout=120,
                capture_output=True,
            )
        except Exception:
            pass
    # If the script fails, also run generate_demo for ST1008 as final fallback
    demo_script = Path(project_root) / "scripts" / "generate_demo.py"
    if demo_script.exists() and not DB_PATH.exists():
        try:
            subprocess.run(
                [sys.executable, str(demo_script)],
                cwd=project_root,
                timeout=120,
                capture_output=True,
            )
        except Exception:
            pass


# Ensure DB is populated at startup (before any queries)
_ensure_db_populated()


# ──────────────────────────────────────────────────────────────────────────────
# Synchronous query helpers – bypass async entirely for Streamlit compatibility
# ──────────────────────────────────────────────────────────────────────────────

def _query_metrics(store_id: str) -> dict:
    """Compute metrics for a store directly via synchronous SQLite."""
    try:
        conn = _get_db_conn()
        c = conn.cursor()

        # Footfall: unique non-staff ENTRY events
        c.execute(
            "SELECT COUNT(DISTINCT visitor_id) FROM events "
            "WHERE store_id=? AND is_staff=0 AND event_type='ENTRY'",
            (store_id,),
        )
        footfall = c.fetchone()[0] or 0

        # Unique visitors
        c.execute(
            "SELECT COUNT(DISTINCT visitor_id) FROM events "
            "WHERE store_id=? AND is_staff=0",
            (store_id,),
        )
        unique_visitors = c.fetchone()[0] or 0

        # Check if POS data exists for this store
        c.execute(
            "SELECT COUNT(*) FROM pos_transactions WHERE store_id=? AND matched=1",
            (store_id,),
        )
        matched_pos = c.fetchone()[0] or 0

        if matched_pos > 0:
            # POS-matched conversion
            c.execute(
                "SELECT COUNT(DISTINCT visitor_id) FROM pos_transactions "
                "WHERE store_id=? AND matched=1",
                (store_id,),
            )
            purchased = c.fetchone()[0] or 0
            conversion_rate = (purchased / unique_visitors * 100) if unique_visitors else 0.0

            # Total matched revenue
            c.execute(
                "SELECT SUM(amount) FROM pos_transactions WHERE store_id=? AND matched=1",
                (store_id,),
            )
            total_revenue = c.fetchone()[0] or 0.0
        else:
            # Queue-based proxy conversion
            c.execute(
                "SELECT COUNT(DISTINCT visitor_id) FROM events "
                "WHERE store_id=? AND is_staff=0 AND event_type='BILLING_QUEUE_JOIN'",
                (store_id,),
            )
            joined = c.fetchone()[0] or 0

            c.execute(
                "SELECT COUNT(DISTINCT visitor_id) FROM events "
                "WHERE store_id=? AND is_staff=0 AND event_type='BILLING_QUEUE_ABANDON'",
                (store_id,),
            )
            abandoned = c.fetchone()[0] or 0

            purchased = max(0, joined - abandoned)
            conversion_rate = (purchased / unique_visitors * 100) if unique_visitors else 0.0
            total_revenue = None

        # Queue depth
        c.execute(
            "SELECT COUNT(*) FROM events "
            "WHERE store_id=? AND is_staff=0 AND event_type='BILLING_QUEUE_JOIN'",
            (store_id,),
        )
        join_count = c.fetchone()[0] or 0

        c.execute(
            "SELECT COUNT(*) FROM events "
            "WHERE store_id=? AND is_staff=0 AND event_type='BILLING_QUEUE_ABANDON'",
            (store_id,),
        )
        abandon_count = c.fetchone()[0] or 0

        queue_depth = max(0, join_count - abandon_count)
        abandonment_rate = (abandon_count / join_count * 100) if join_count else 0.0

        # Avg dwell per zone
        c.execute(
            "SELECT zone_id, AVG(dwell_ms) FROM events "
            "WHERE store_id=? AND is_staff=0 AND event_type='ZONE_DWELL' "
            "AND zone_id IS NOT NULL AND dwell_ms IS NOT NULL "
            "GROUP BY zone_id",
            (store_id,),
        )
        avg_dwell_per_zone = {
            row[0]: round((row[1] or 0) / 1000, 1)
            for row in c.fetchall()
        }

        conn.close()
        return {
            "store_id": store_id,
            "footfall": footfall,
            "unique_visitors": unique_visitors,
            "conversion_rate": round(conversion_rate, 2),
            "avg_dwell_per_zone": avg_dwell_per_zone,
            "queue_depth": queue_depth,
            "abandonment_rate": round(abandonment_rate, 2),
            "total_revenue": total_revenue,
            "brand_conversion": {},
        }
    except Exception as e:
        return {}


def _query_funnel(store_id: str) -> dict:
    """Compute customer journey funnel for a store."""
    try:
        conn = _get_db_conn()
        c = conn.cursor()

        c.execute(
            "SELECT COUNT(DISTINCT visitor_id) FROM events "
            "WHERE store_id=? AND is_staff=0 AND event_type='ENTRY'",
            (store_id,),
        )
        entry = c.fetchone()[0] or 0

        c.execute(
            "SELECT COUNT(DISTINCT visitor_id) FROM events "
            "WHERE store_id=? AND is_staff=0 AND event_type='ZONE_ENTER'",
            (store_id,),
        )
        zone_visit = c.fetchone()[0] or 0

        c.execute(
            "SELECT COUNT(DISTINCT visitor_id) FROM events "
            "WHERE store_id=? AND is_staff=0 AND event_type='BILLING_QUEUE_JOIN'",
            (store_id,),
        )
        billing = c.fetchone()[0] or 0

        # Purchase = billing queue joiners who didn't abandon
        c.execute(
            "SELECT COUNT(DISTINCT visitor_id) FROM events "
            "WHERE store_id=? AND is_staff=0 AND event_type='BILLING_QUEUE_ABANDON'",
            (store_id,),
        )
        abandoned = c.fetchone()[0] or 0

        # Also check POS-matched
        c.execute(
            "SELECT COUNT(DISTINCT visitor_id) FROM pos_transactions "
            "WHERE store_id=? AND matched=1",
            (store_id,),
        )
        pos_purchased = c.fetchone()[0] or 0

        purchase = pos_purchased if pos_purchased > 0 else max(0, billing - abandoned)

        conn.close()
        d1 = entry - zone_visit
        d2 = zone_visit - billing
        d3 = billing - purchase
        return {
            "store_id": store_id,
            "entry": entry,
            "zone_visit": zone_visit,
            "billing": billing,
            "purchase": purchase,
            "dropoff": {
                "entry_to_zone": d1,
                "zone_to_billing": d2,
                "billing_to_purchase": d3,
            },
        }
    except Exception:
        return {}


def _query_heatmap(store_id: str) -> dict:
    """Compute zone engagement heatmap for a store."""
    try:
        conn = _get_db_conn()
        c = conn.cursor()

        # Visit counts per zone
        c.execute(
            "SELECT zone_id, COUNT(DISTINCT visitor_id) FROM events "
            "WHERE store_id=? AND is_staff=0 AND event_type='ZONE_ENTER' "
            "AND zone_id IS NOT NULL GROUP BY zone_id",
            (store_id,),
        )
        visits_by_zone = {row[0]: row[1] for row in c.fetchall()}

        # Avg dwell per zone
        c.execute(
            "SELECT zone_id, AVG(dwell_ms) FROM events "
            "WHERE store_id=? AND is_staff=0 AND event_type='ZONE_DWELL' "
            "AND zone_id IS NOT NULL AND dwell_ms IS NOT NULL GROUP BY zone_id",
            (store_id,),
        )
        dwell_by_zone = {row[0]: (row[1] or 0.0) / 1000 for row in c.fetchall()}
        conn.close()

        all_zones = set(visits_by_zone) | set(dwell_by_zone)
        if not all_zones:
            return {"store_id": store_id, "zones": {}}

        max_visits = max(visits_by_zone.values(), default=1)
        max_dwell = max(dwell_by_zone.values(), default=1.0)

        # Load brand map for this specific store
        brand_map = _get_brand_map(store_id)

        zones = {}
        for zone_id in sorted(all_zones):
            visits = visits_by_zone.get(zone_id, 0)
            avg_dwell_s = round(dwell_by_zone.get(zone_id, 0.0), 1)
            visit_norm = (visits / max_visits) if max_visits else 0
            dwell_norm = (avg_dwell_s / (max_dwell + 1e-6)) if max_dwell else 0
            score = int((0.4 * visit_norm + 0.6 * dwell_norm) * 100)
            zones[zone_id] = {
                "visits": visits,
                "avg_dwell_s": avg_dwell_s,
                "score": score,
                "brand": brand_map.get(zone_id),
            }

        return {"store_id": store_id, "zones": zones}
    except Exception:
        return {"store_id": store_id, "zones": {}}


def _query_anomalies(store_id: str) -> dict:
    """Compute anomalies for a store using the correct store's zone IDs."""
    try:
        conn = _get_db_conn()
        c = conn.cursor()

        # Discover zone IDs for THIS specific store only
        c.execute(
            "SELECT DISTINCT zone_id FROM events "
            "WHERE store_id=? AND is_staff=0 AND zone_id IS NOT NULL",
            (store_id,),
        )
        zone_ids = [row[0] for row in c.fetchall()]
        conn.close()

        if not zone_ids:
            return {"store_id": store_id, "anomalies": []}

        from src.anomaly_engine import AnomalyEngine
        engine = AnomalyEngine(store_id=store_id, zone_ids=zone_ids)

        # Feed zone last-activity timestamps
        conn = _get_db_conn()
        c = conn.cursor()
        for zone_id in zone_ids:
            c.execute(
                "SELECT MAX(timestamp) FROM events "
                "WHERE store_id=? AND zone_id=? AND is_staff=0",
                (store_id, zone_id),
            )
            last_ts_str = c.fetchone()[0]
            if last_ts_str:
                try:
                    from datetime import timezone
                    last_ts = datetime.fromisoformat(str(last_ts_str))
                    if last_ts.tzinfo is None:
                        last_ts = last_ts.replace(tzinfo=timezone.utc)
                    engine.update_zone_activity(zone_id, last_ts.timestamp())
                except Exception:
                    pass

        # Feed queue depth history
        c.execute(
            "SELECT timestamp, event_type FROM events "
            "WHERE store_id=? AND is_staff=0 "
            "AND event_type IN ('BILLING_QUEUE_JOIN', 'BILLING_QUEUE_ABANDON') "
            "ORDER BY timestamp",
            (store_id,),
        )
        depth = 0
        for ts_str, etype in c.fetchall():
            try:
                from datetime import timezone
                ts = datetime.fromisoformat(str(ts_str))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if etype == "BILLING_QUEUE_JOIN":
                    depth += 1
                else:
                    depth = max(0, depth - 1)
                engine.update_queue_depth(depth, ts.timestamp())
            except Exception:
                pass

        conn.close()

        raw = engine.detect()
        anomalies = [
            {
                "type": a["type"],
                "severity": a.get("severity", "INFO"),
                "store_id": store_id,
                "action": a.get("action", ""),
            }
            for a in raw
        ]
        return {"store_id": store_id, "anomalies": anomalies}
    except Exception as e:
        return {"store_id": store_id, "anomalies": []}


def _get_brand_map(store_id: str) -> dict:
    """Load brand map for a specific store from store_config.json."""
    try:
        from src.layout.parser import load_store_config
        config_path = Path(project_root) / "src" / "layout" / "store_config.json"
        config = load_store_config(str(config_path), store_id)
        return config.zone_brand_map() if config else {}
    except Exception:
        return {}


def _query_health() -> dict:
    """Health check via synchronous SQLite."""
    try:
        conn = _get_db_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM events")
        total = c.fetchone()[0] or 0

        c.execute(
            "SELECT store_id, MAX(timestamp) FROM events GROUP BY store_id"
        )
        last_per_store = {row[0]: row[1] for row in c.fetchall()}
        conn.close()
        return {
            "status": "OK",
            "db_event_count": total,
            "last_event_per_store": last_per_store,
            "stale_feeds": [],
        }
    except Exception:
        return {"status": "UNKNOWN", "db_event_count": 0}


# ──────────────────────────────────────────────────────────────────────────────
# API helper – try HTTP first, fall back to direct sync DB queries
# ──────────────────────────────────────────────────────────────────────────────

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")
REFRESH_SECONDS = 10


def api_get(path: str) -> dict | None:
    """Try FastAPI HTTP, then fall back to direct synchronous SQLite queries."""
    # First attempt: HTTP to FastAPI backend
    try:
        r = requests.get(f"{API_BASE}{path}", timeout=2)
        r.raise_for_status()
        return r.json()
    except Exception:
        pass

    # Second attempt: synchronous direct SQLite query (no asyncio, no event loop issues)
    try:
        if path == "/health":
            return _query_health()
        elif path.startswith("/stores/") and path.endswith("/metrics"):
            sid = path.split("/")[2]
            return _query_metrics(sid)
        elif path.startswith("/stores/") and path.endswith("/funnel"):
            sid = path.split("/")[2]
            return _query_funnel(sid)
        elif path.startswith("/stores/") and path.endswith("/heatmap"):
            sid = path.split("/")[2]
            return _query_heatmap(sid)
        elif path.startswith("/stores/") and path.endswith("/anomalies"):
            sid = path.split("/")[2]
            return _query_anomalies(sid)
    except Exception:
        pass

    return None


# ──────────────────────────────────────────────────────────────────────────────
# Streamlit page config
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Store Intelligence Dashboard",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# Sidebar – store selector & health
# ──────────────────────────────────────────────────────────────────────────────

st.sidebar.title("🏪 Store Intelligence")
st.sidebar.markdown("---")

health = api_get("/health") or {}
status = health.get("status", "UNKNOWN")
status_color = "🟢" if status == "OK" else "🔴"
st.sidebar.markdown(f"**API Status:** {status_color} {status}")

# Store selector driven by StoreRegistry (works even if API is down)
try:
    from src.store_registry import get_registry
    _reg = get_registry()
    REGISTERED_STORE_IDS = [cfg.store_id for cfg in _reg.list_all()]
except Exception:
    REGISTERED_STORE_IDS = ["ST1008", "STORE_1", "STORE_2"]

selected_store = st.sidebar.selectbox(
    "Select Store",
    REGISTERED_STORE_IDS,
    help="Switch between registered stores. All use the same pipeline.",
)

stale = health.get("stale_feeds", [])
if selected_store in stale:
    st.sidebar.warning(f"⚠️ Feed for {selected_store} is stale (>10 min)")

db_count = health.get("db_event_count", 0)
st.sidebar.metric("Total Events in DB", f"{db_count:,}")
st.sidebar.caption(f"Last refresh: {datetime.now().strftime('%H:%M:%S')}")

# ──────────────────────────────────────────────────────────────────────────────
# Main dashboard – tabs
# ──────────────────────────────────────────────────────────────────────────────

tab_live, tab_cross = st.tabs([
    f"📊 {selected_store} — Live Analytics",
    "🏬 Cross-Store Comparison",
])

# ─── Tab 1: Live per-store analytics ─────────────────────────────────────────

with tab_live:
    st.header(f"📊 Store {selected_store} – Live Analytics")

    # Row 1: Key metrics
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

    # Row 2: Funnel + Heatmap
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("🔽 Customer Journey Funnel")
        funnel = api_get(f"/stores/{selected_store}/funnel") or {}

        if funnel and funnel.get("entry", 0) > 0:
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

    # Row 3: Dwell bar chart
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

    # Row 4: Anomaly panel
    st.subheader("🚨 Active Anomalies")
    anomalies_data = api_get(f"/stores/{selected_store}/anomalies") or {}
    anomaly_list = anomalies_data.get("anomalies", [])

    if anomaly_list:
        for a in anomaly_list:
            severity = a.get("severity", "INFO")
            icon = {"INFO": "ℹ️", "WARN": "⚠️", "CRITICAL": "🔴"}.get(severity, "ℹ️")

            with st.container():
                cols = st.columns([0.05, 0.25, 0.7])
                cols[0].markdown(icon)
                cols[1].markdown(f"**{a['type']}**  \n`{severity}`")
                cols[2].markdown(a.get("action", ""))
            st.markdown("")
    else:
        st.success("✅ No active anomalies detected.")

    st.caption(f"Auto-refreshing every {REFRESH_SECONDS}s · Store: {selected_store} · API: {API_BASE}")

# ─── Tab 2: Cross-Store Comparison ───────────────────────────────────────────

with tab_cross:
    st.header("🏬 Cross-Store Comparison")
    st.caption(
        "Powered by `evaluation/cross_store_comparison.json` "
        "— generated by `python scripts/run_cross_store_analysis.py`"
    )

    cross_path = Path(__file__).parent.parent / "evaluation" / "cross_store_comparison.json"
    if cross_path.exists():
        with open(cross_path) as _f:
            cross_data = json.load(_f)

        stores_raw = cross_data.get("stores", [])
        if stores_raw:
            store_names = [s["store_id"] for s in stores_raw]

            # Visitor comparison
            st.subheader("👥 Visitor Count by Store")
            visitors = [s.get("visitors", 0) for s in stores_raw]
            fig_v = px.bar(
                x=store_names, y=visitors,
                labels={"x": "Store", "y": "Visitors"},
                color=store_names,
                color_discrete_sequence=px.colors.qualitative.Vivid,
                text=visitors,
            )
            fig_v.update_layout(
                showlegend=False, height=300,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_v, use_container_width=True)

            # Conversion rate comparison
            st.subheader("🛒 Conversion Rate by Store")
            conv = [s.get("conversion_rate", 0) for s in stores_raw]
            methods = [s.get("conversion_method", "") for s in stores_raw]
            fig_c = px.bar(
                x=store_names, y=conv,
                labels={"x": "Store", "y": "Conversion Rate (%)"},
                color=store_names,
                color_discrete_sequence=px.colors.qualitative.Safe,
                text=[f"{v:.1f}%" for v in conv],
            )
            fig_c.update_layout(
                showlegend=False, height=300,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_c, use_container_width=True)
            for name, method in zip(store_names, methods):
                st.caption(f"  **{name}**: {method}")

            # Camera topology table
            st.subheader("📷 Camera Topology")
            topo = {
                "Store": store_names,
                "Entry Cameras": [s.get("entry_cameras", 0) for s in stores_raw],
                "Zone Cameras": [s.get("zone_cameras", 0) for s in stores_raw],
                "Billing Cameras": [s.get("billing_cameras", 0) for s in stores_raw],
                "Total Cameras": [s.get("total_cameras", 0) for s in stores_raw],
                "POS Available": ["Yes" if s.get("pos_available") else "No" for s in stores_raw],
            }
            st.dataframe(topo, use_container_width=True, hide_index=True)

            st.info(
                "**Zero code changes** were required to process STORE_1 and STORE_2. "
                "Only the `StoreRegistry` configuration was updated."
            )
        else:
            st.warning("Cross-store data is empty. Run the pipeline for each store first.")
    else:
        st.info(
            "Cross-store comparison data not yet generated.\n\n"
            "Run: `python scripts/run_cross_store_analysis.py`"
        )

# ── Auto-refresh ──────────────────────────────────────────────────────────────

import time
time.sleep(REFRESH_SECONDS)
st.rerun()
