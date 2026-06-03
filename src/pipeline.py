"""
pipeline.py – Main video processing orchestrator.

Ties together: Scanner → Detector → ByteTracker → OSNetReID →
SessionManager → EventEmitter → POSCorrelator

Processes each discovered video, emitting events to a JSONL output file
and optionally ingesting them into the FastAPI endpoint.

Usage
-----
  python src/pipeline.py --data "C:\\CCTV Footage" --output output/events.jsonl
  python src/pipeline.py --video path/to/single.mp4 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TimeElapsedColumn

console = Console()


def _group_by_store(videos) -> dict[str, list]:
    """Group VideoMeta objects by store_id."""
    groups: dict[str, list] = {}
    for v in videos:
        sid = v.store_id
        groups.setdefault(sid, []).append(v)
    return groups


def run_pipeline(
    data_root: str,
    output_path: str = "output/events.jsonl",
    dry_run: bool = False,
    ingest_url: str | None = None,
    single_video: str | None = None,
    skip_frames: int = 1,
) -> None:
    from .scanner import scan, VideoMeta
    from .detector import PersonDetector
    from .tracker import ByteTracker
    from .reid import OSNetReID
    from .session_manager import SessionManager
    from .event_emitter import EventEmitter
    from .pos_correlator import POSCorrelator
    from .tracker_lifecycle import TrackLifecycleManager
    from .config import TRACK_LOST_TIMEOUT, OCCLUSION_TIMEOUT


    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # ── 1. Scan dataset ──────────────────────────────────────────────────────
    if single_video:
        from .scanner import VideoMeta, _validate_video
        report = type("R", (), {
            "videos": [_validate_video(Path(single_video))[0]],
            "store_layout": {},
            "is_clean": True,
            "warnings": [],
        })()
        pos_csv = None
    else:
        report = scan(data_root)
        if not report.is_clean:
            console.print(
                "[yellow][WARN] Scan report has issues - proceeding with valid files only[/]"
            )
        pos_csv = next(
            (Path(data_root) / f for f in Path(data_root).rglob("pos_transactions.csv")),
            None,
        )

    valid_videos = [v for v in report.videos if v.valid]
    if not valid_videos:
        console.print("[red]No valid videos found. Exiting.[/]")
        sys.exit(1)

    # ── 2. Shared components ─────────────────────────────────────────────────
    detector = PersonDetector(
        model_path=os.environ.get("YOLO_MODEL", "yolov8s.pt"),
        conf_threshold=float(os.environ.get("YOLO_CONF", "0.25")),
        device=os.environ.get("YOLO_DEVICE", "cpu"),
    )

    all_events: list[dict] = []

    # ── 3. Process each store ────────────────────────────────────────────────
    store_groups = _group_by_store(valid_videos)

    for store_id, store_videos in store_groups.items():
        console.rule(f"[bold cyan]Store {store_id}")

        # One ReID gallery per store (cross-camera matching)
        reid = OSNetReID()
        session_mgr = SessionManager(store_id=store_id)

        # Load POS for this store
        if pos_csv:
            try:
                correlator = POSCorrelator(pos_csv, store_id)
            except Exception as e:
                console.print(f"[yellow]POS load warning: {e}[/]")
                correlator = None
        else:
            correlator = None

        store_events: list[dict] = []

        for video_meta in store_videos:
            console.print(
                f"  Processing [bold]{Path(video_meta.path).name}[/]  "
                f"[dim]{video_meta.fps:.1f}fps  {video_meta.frame_count} frames[/]"
            )

            cap = cv2.VideoCapture(video_meta.path)
            tracker = ByteTracker(frame_rate=video_meta.fps)

            # Guess video start time from filename or use now()
            video_start = datetime.now(timezone.utc)

            emitter = EventEmitter(
                store_id=store_id,
                camera_id=video_meta.camera_id,
                store_layout=report.store_layout,
                session_manager=session_mgr,
                reid_gallery=reid,
                fps=video_meta.fps,
                video_start_time=video_start,
                clip_duration=video_meta.duration_s,
                total_video_frames=video_meta.frame_count,
            )


            with Progress(
                SpinnerColumn(),
                "[progress.description]{task.description}",
                BarColumn(),
                "[progress.percentage]{task.percentage:>3.0f}%",
                TimeElapsedColumn(),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task(
                    f"  {Path(video_meta.path).name}",
                    total=video_meta.frame_count
                )

                lifecycle_manager = TrackLifecycleManager(
                    exit_line=emitter.exit_line,
                    lost_timeout=TRACK_LOST_TIMEOUT,
                    occlusion_timeout=OCCLUSION_TIMEOUT,
                )

                frame_idx = 0
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break

                    if skip_frames > 1 and frame_idx % skip_frames != 0:
                        frame_idx += 1
                        progress.advance(task)
                        continue

                    detections = detector.detect(frame)
                    raw_tracks = tracker.update(detections, frame)
                    
                    h, w = frame.shape[:2]
                    frame_time = emitter._frame_time(frame_idx)
                    valid_active_infos, lifecycle_signals = lifecycle_manager.update(
                        raw_tracks, frame_time, w, h
                    )

                    for info in valid_active_infos:
                        if info.visitor_id is None:
                            x1, y1, x2, y2 = map(int, info.xyxy)
                            x1, y1 = max(0, x1), max(0, y1)
                            x2, y2 = min(w, x2), min(h, y2)
                            crop = frame[y1:y2, x1:x2]
                            visitor_id, uncertain = reid.identify(crop, frame_idx)
                            info.visitor_id = visitor_id
                            info.uncertain_reid = uncertain

                    events = emitter.process_frame(
                        frame,
                        valid_active_infos,
                        frame_idx,
                        lifecycle_signals=lifecycle_signals,
                    )

                    if dry_run:
                        for e in events:
                            console.print(
                                f"    [green]{e.event_type}[/]  "
                                f"{e.visitor_id[:8]}  "
                                f"{e.zone_id or ''}"
                            )

                    frame_idx += 1
                    progress.advance(task)


            cap.release()
            tracker.reset()

            video_events = emitter.flush()
            store_events.extend(video_events)
            console.print(f"  → {len(video_events)} events from {Path(video_meta.path).name}")

        # ── 4. POS Correlation ───────────────────────────────────────────────
        if correlator:
            matched = correlator.correlate(session_mgr)
            console.print(f"  [cyan]POS: {matched} transactions correlated[/]")

        all_events.extend(store_events)

    # ── 5. Write output ──────────────────────────────────────────────────────
    if not dry_run:
        with open(output_file, "w") as f:
            for evt in all_events:
                f.write(json.dumps(evt) + "\n")
        console.print(
            f"\n[bold green][OK] {len(all_events)} events written to {output_file}[/]"
        )

    # ── 6. Optionally ingest into API ────────────────────────────────────────
    if ingest_url and not dry_run:
        _ingest_events(all_events, ingest_url)


def _ingest_events(events: list[dict], base_url: str) -> None:
    import requests

    url = base_url.rstrip("/") + "/events/ingest"
    batch_size = 500
    total_accepted = 0

    for i in range(0, len(events), batch_size):
        batch = events[i : i + batch_size]
        try:
            resp = requests.post(url, json=batch, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            total_accepted += data.get("accepted", 0)
        except Exception as e:
            console.print(f"[red]Ingest error batch {i//batch_size}: {e}[/]")

    console.print(f"[cyan]API ingested {total_accepted}/{len(events)} events[/]")


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CCTV Store Intelligence Pipeline")
    parser.add_argument(
        "--data",
        default=os.environ.get(
            "DATA_ROOT", r"C:\Users\BIT\OneDrive\Documents\CCTV\CCTV Footage"
        ),
        help="Root directory with CCTV footage",
    )
    parser.add_argument("--video", default=None, help="Process a single video file")
    parser.add_argument(
        "--output", default="output/events.jsonl", help="Output JSONL path"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print events; don't write file"
    )
    parser.add_argument(
        "--ingest-url",
        default=None,
        help="POST events to this API base URL (e.g. http://localhost:8000)",
    )
    parser.add_argument(
        "--skip-frames",
        type=int,
        default=1,
        help="Process every Nth frame for performance optimization",
    )
    args = parser.parse_args()

    run_pipeline(
        data_root=args.data,
        output_path=args.output,
        dry_run=args.dry_run,
        ingest_url=args.ingest_url,
        single_video=args.video,
        skip_frames=args.skip_frames,
    )
