"""
scanner.py – Dataset recursive scanner and validator.

Discovers all CCTV video files, store_layout.json, pos_transactions.csv,
and sample_events.jsonl under DATA_ROOT. Validates each asset and emits
a structured ScanReport.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import pandas as pd
from rich.console import Console
from rich.table import Table

console = Console()

# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class VideoMeta:
    path: str
    store_id: str
    camera_id: str
    fps: float
    width: int
    height: int
    frame_count: int
    duration_s: float
    valid: bool
    error: str = ""


@dataclass
class ScanReport:
    data_root: str
    videos: list[VideoMeta] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    corrupt_videos: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    store_layout: dict[str, Any] = field(default_factory=dict)
    pos_row_count: int = 0
    sample_event_count: int = 0

    @property
    def is_clean(self) -> bool:
        return len(self.missing_files) == 0 and len(self.corrupt_videos) == 0


# ──────────────────────────────────────────────────────────────────────────────
# Discovery & Validation Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _discover_camera_store(
    path: Path,
    layout: dict[str, Any] | None = None,
    width: int = 0,
    height: int = 0,
    duration_s: float = 0.0,
) -> tuple[str, str, str | None]:
    """
    Resolves (store_id, camera_id, warning_message) for a given video file.
    Discovery order:
      1. store_layout.json mapping (if camera config contains video_file or filename matching path.name)
      2. Filename pattern mapping (e.g. S1_CAM1.mp4)
      3. Video metadata heuristics (e.g. aspect ratio, duration mapped to defaults)
      4. Unknown camera fallback
    """
    filename = path.name

    # ── 1. Layout mapping ──
    if layout:
        stores = layout.get("stores", {})
        for store_id, store_data in stores.items():
            for cam in store_data.get("cameras", []):
                for key in ["video_file", "filename", "file"]:
                    val = cam.get(key)
                    if val and str(val).lower() == filename.lower():
                        return store_id.upper(), str(cam.get("camera_id", "")).upper(), None

    # ── 2. Filename mapping ──
    stem = path.stem.upper()
    store_id = "UNKNOWN"
    camera_id = "UNKNOWN"

    for part in stem.replace("-", "_").split("_"):
        if part.startswith("S") and part[1:].isdigit():
            store_id = part
        elif part.startswith("STORE") and part[5:].isdigit():
            store_id = f"S{part[5:]}"
        elif part.startswith("CAM") and part[3:].isdigit():
            camera_id = part
        elif part.startswith("CAMERA") and part[6:].isdigit():
            camera_id = f"CAM{part[6:]}"
        elif part.startswith("ANGLE") and part[5:].isdigit():
            camera_id = f"CAM{part[5:]}"

    if store_id != "UNKNOWN" or camera_id != "UNKNOWN":
        return store_id, camera_id, None

    # ── 3. Heuristics ──
    guessed_store = "S1"
    # Widescreen or billing keyword -> CAM3 (Billing)
    if width >= 1920 or "billing" in filename.lower() or "checkout" in filename.lower():
        guessed_cam = "CAM3"
    elif "floor" in filename.lower() or "main" in filename.lower():
        guessed_cam = "CAM2"
    else:
        # Default to CAM1 (Entry)
        guessed_cam = "CAM1"

    warning_msg = (
        f"{filename}: layout and filename mapping failed. "
        f"Assigned store={guessed_store}, camera={guessed_cam} via heuristics."
    )
    return guessed_store, guessed_cam, warning_msg


def _validate_video(path: Path, layout: dict[str, Any] | None = None) -> tuple[VideoMeta, str | None]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        cap.release()
        return VideoMeta(
            path=str(path), store_id="UNKNOWN", camera_id="UNKNOWN",
            fps=0, width=0, height=0, frame_count=0, duration_s=0,
            valid=False, error="VideoCapture failed to open"
        ), None

    ret, _ = cap.read()
    if not ret:
        cap.release()
        return VideoMeta(
            path=str(path), store_id="UNKNOWN", camera_id="UNKNOWN",
            fps=0, width=0, height=0, frame_count=0, duration_s=0,
            valid=False, error="First frame read failed"
        ), None

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_s = frame_count / fps if fps else 0.0
    cap.release()

    store_id, camera_id, warning_msg = _discover_camera_store(
        path, layout, width, height, duration_s
    )

    meta = VideoMeta(
        path=str(path), store_id=store_id, camera_id=camera_id,
        fps=fps, width=width, height=height,
        frame_count=frame_count, duration_s=duration_s,
        valid=True
    )
    return meta, warning_msg


# ──────────────────────────────────────────────────────────────────────────────
# Main scanner
# ──────────────────────────────────────────────────────────────────────────────

def scan(data_root: str | Path) -> ScanReport:
    """
    Recursively scan *data_root* and return a ScanReport.
    """
    root = Path(data_root)
    report = ScanReport(data_root=str(root))

    if not root.exists():
        report.missing_files.append(str(root))
        console.print(f"[red][ERROR] DATA_ROOT not found:[/] {root}")
        return report

    console.rule("[bold cyan]Dataset Scanner")

    # ── 1. Load layout (store_config.json or store_layout.json) ──
    layout_paths = list(root.rglob("store_config.json"))
    layout_filename = "store_config.json"
    if not layout_paths:
        layout_paths = list(root.rglob("store_layout.json"))
        layout_filename = "store_layout.json"
    if not layout_paths:
        fallback_path = Path(__file__).parent / "layout" / "store_config.json"
        if fallback_path.exists():
            layout_paths = [fallback_path]
            layout_filename = "store_config.json"

    if not layout_paths:
        report.warnings.append("store_config.json or store_layout.json not found under DATA_ROOT or workspace fallback")
        console.print("[yellow][WARN] Layout config file not found - layout discovery bypassed[/]")
    else:
        try:
            with open(layout_paths[0]) as f:
                report.store_layout = json.load(f)
            console.print(f"[green][OK][/] {layout_filename} loaded from {layout_paths[0]}")
        except Exception as exc:
            report.warnings.append(f"{layout_filename} failed to load: {exc}")
            console.print(f"[red][ERROR] {layout_filename} failed to load: {exc}[/]")

    # ── 2. Discover & validate videos ──────────────────────────────────────────
    video_extensions = {".mp4", ".avi", ".mov", ".mkv"}
    video_paths = [
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in video_extensions
    ]

    console.print(f"Found [bold]{len(video_paths)}[/] video file(s) under {root}")

    for vp in sorted(video_paths):
        meta, warn_msg = _validate_video(vp, report.store_layout or None)
        report.videos.append(meta)
        if warn_msg:
            report.warnings.append(warn_msg)

        if meta.valid:
            console.print(
                f"  [green][OK][/] {vp.name} -> Store {meta.store_id}, Cam {meta.camera_id}  "
                f"[dim]{meta.fps:.1f}fps  {meta.width}x{meta.height}  "
                f"{meta.duration_s:.1f}s[/]"
            )
        else:
            report.corrupt_videos.append(str(vp))
            console.print(f"  [red][ERROR][/] {vp.name}  [red]{meta.error}[/]")

    # Cross-check camera IDs if layout is available
    if report.store_layout:
        layout_cameras: set[str] = set()
        for store in report.store_layout.get("stores", {}).values():
            for cam in store.get("cameras", []):
                layout_cameras.add(str(cam.get("camera_id", "")).upper())

        for vm in report.videos:
            if vm.valid and vm.camera_id != "UNKNOWN" and vm.camera_id not in layout_cameras:
                report.warnings.append(
                    f"{Path(vm.path).name}: camera_id '{vm.camera_id}' "
                    f"not in store_layout cameras {layout_cameras}"
                )

    # ── 3. Load pos_transactions.csv ────────────────────────────────────────────
    pos_paths = list(root.rglob("pos_transactions.csv"))
    if not pos_paths:
        report.warnings.append("pos_transactions.csv not found under DATA_ROOT")
        console.print("[yellow][WARN] pos_transactions.csv not found[/]")
    else:
        try:
            df = pd.read_csv(pos_paths[0])
            # Check for real format (order_date + order_time) or generic format (timestamp)
            has_real_cols = {"order_date", "order_time", "store_id"}.issubset(df.columns)
            has_generic_cols = {"timestamp", "store_id"}.issubset(df.columns)

            if not (has_real_cols or has_generic_cols):
                report.warnings.append(
                    "pos_transactions.csv missing required columns. "
                    "Expected either {'timestamp', 'store_id'} or {'order_date', 'order_time', 'store_id'}"
                )
            else:
                if has_real_cols:
                    # Validate datetime parsing for real format
                    dt_series = pd.to_datetime(
                        df["order_date"].astype(str) + " " + df["order_time"].astype(str),
                        format="mixed",
                        dayfirst=True,
                        utc=True,
                        errors="coerce"
                    )
                    bad_ts = dt_series.isna().sum()
                else:
                    # Validate generic format
                    dt_series = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
                    bad_ts = dt_series.isna().sum()

                if bad_ts:
                    report.warnings.append(
                        f"pos_transactions.csv: {bad_ts} unparseable timestamps"
                    )
            report.pos_row_count = len(df)
            console.print(
                f"[green][OK][/] pos_transactions.csv  [dim]{len(df)} rows[/]"
            )
        except Exception as exc:
            report.warnings.append(f"pos_transactions.csv parse error: {exc}")

    # ── 4. Load sample_events.jsonl ─────────────────────────────────────────────
    sample_paths = list(root.rglob("sample_events.jsonl"))
    if sample_paths:
        with open(sample_paths[0]) as f:
            lines = [l for l in f if l.strip()]
        report.sample_event_count = len(lines)
        console.print(
            f"[green][OK][/] sample_events.jsonl  [dim]{len(lines)} events[/]"
        )
    else:
        console.print("[yellow][WARN] sample_events.jsonl not found (optional)[/]")

    # ── Summary ──────────────────────────────────────────────────────────────
    _print_summary(report)
    return report


def _print_summary(report: ScanReport) -> None:
    table = Table(title="Scan Summary", show_header=True)
    table.add_column("Metric", style="bold")
    table.add_column("Value")

    valid_count = sum(1 for v in report.videos if v.valid)
    table.add_row("Total videos found", str(len(report.videos)))
    table.add_row("Valid videos", f"[green]{valid_count}[/]")
    table.add_row(
        "Corrupt videos",
        f"[red]{len(report.corrupt_videos)}[/]" if report.corrupt_videos else "0"
    )
    table.add_row("POS rows", str(report.pos_row_count))
    table.add_row("Sample events", str(report.sample_event_count))
    table.add_row("Warnings", str(len(report.warnings)))
    table.add_row("Clean?", "[green]YES[/]" if report.is_clean else "[yellow]PARTIAL[/]")

    console.print(table)
    for w in report.warnings:
        console.print(f"  [yellow][WARN][/] {w}")


# ──────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys

    parser = argparse.ArgumentParser(description="CCTV Dataset Scanner")
    parser.add_argument(
        "--data",
        default=os.environ.get(
            "DATA_ROOT",
            r"C:\Users\BIT\OneDrive\Documents\CCTV\CCTV Footage"
        ),
        help="Root directory containing CCTV footage and metadata files"
    )
    args = parser.parse_args()

    report = scan(args.data)
    sys.exit(0 if report.is_clean else 1)
