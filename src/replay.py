"""
replay.py – Event replay mode.

Reads the generated events.jsonl file and POSTs events to the API at
a wall-clock-proportional rate, simulating a live camera feed.
This enables the Streamlit dashboard to show real-time updates during demos.

Usage
-----
  python src/replay.py --events output/events.jsonl --speed 1x
  python src/replay.py --events output/events.jsonl --speed 10x --url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from rich.console import Console
from rich.live import Live
from rich.table import Table

console = Console()

BATCH_SIZE = 50


def replay(
    events_path: str,
    speed: float = 1.0,
    api_url: str = "http://localhost:8000",
    dry_run: bool = False,
) -> None:
    events_file = Path(events_path)
    if not events_file.exists():
        console.print(f"[red]Events file not found: {events_file}[/]")
        sys.exit(1)

    # Load and sort events by timestamp
    with open(events_file) as f:
        raw = [json.loads(line) for line in f if line.strip()]

    if not raw:
        console.print("[yellow]No events to replay.[/]")
        return

    events = sorted(raw, key=lambda e: e.get("timestamp", ""))
    console.print(
        f"[bold cyan]Replay:[/] {len(events)} events at {speed}x speed → {api_url}"
    )

    # Parse timestamps to epoch
    def to_epoch(ts_str: str) -> float:
        try:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    event_epochs = [to_epoch(e.get("timestamp", "")) for e in events]
    first_epoch = event_epochs[0]
    replay_start = time.time()

    stats = {"sent": 0, "accepted": 0, "rejected": 0}
    table = Table(title="Replay Progress", show_header=True)
    table.add_column("Metric")
    table.add_column("Value", justify="right")

    ingest_url = api_url.rstrip("/") + "/events/ingest"
    batch: list[dict] = []
    batch_epoch: float = first_epoch

    for i, (evt, epoch) in enumerate(zip(events, event_epochs)):
        # Compute wall-clock delay
        simulated_elapsed = (epoch - first_epoch) / speed
        wall_elapsed = time.time() - replay_start
        wait = simulated_elapsed - wall_elapsed
        if wait > 0:
            time.sleep(wait)

        batch.append(evt)

        # Send when batch is full OR timestamp jumps by >1s (real-time-ish)
        if len(batch) >= BATCH_SIZE or (epoch - batch_epoch > 1.0 / speed):
            if not dry_run:
                _send_batch(batch, ingest_url, stats)
            else:
                console.print(
                    f"  [dim][DRY RUN] Would send {len(batch)} events[/]"
                )
            batch = []
            batch_epoch = epoch

        if i % 100 == 0:
            console.print(
                f"  [{i}/{len(events)}] sent={stats['sent']} "
                f"accepted={stats['accepted']} rejected={stats['rejected']}"
            )

    # Flush remaining
    if batch and not dry_run:
        _send_batch(batch, ingest_url, stats)

    console.print(
        f"\n[bold green]Replay complete:[/] "
        f"{stats['sent']} sent, {stats['accepted']} accepted, "
        f"{stats['rejected']} rejected"
    )


def _send_batch(
    batch: list[dict],
    url: str,
    stats: dict,
) -> None:
    try:
        resp = requests.post(url, json=batch, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        stats["sent"] += len(batch)
        stats["accepted"] += data.get("accepted", 0)
        stats["rejected"] += len(data.get("rejected", []))
    except requests.RequestException as e:
        console.print(f"[red]Batch send error: {e}[/]")
        stats["sent"] += len(batch)


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CCTV Event Replay")
    parser.add_argument("--events", default="output/events.jsonl")
    parser.add_argument(
        "--speed",
        type=str,
        default="1x",
        help="Replay speed multiplier, e.g. 1x, 5x, 10x",
    )
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    speed_val = float(args.speed.rstrip("x") or "1")
    replay(args.events, speed=speed_val, api_url=args.url, dry_run=args.dry_run)
