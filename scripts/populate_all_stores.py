"""
scripts/populate_all_stores.py – Import all store JSONL events into SQLite.

Loads events from:
  - results/real_events.jsonl   → ST1008 (real CCTV run)
  - results/store1_events.jsonl → STORE_1 (validation store)
  - results/store2_events.jsonl → STORE_2 (validation store)

Also runs generate_demo.py for ST1008 POS correlation (demo mode).

Usage:
    python scripts/populate_all_stores.py
    python scripts/populate_all_stores.py --skip-demo   # skip POS demo, just load JSONL
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))

from src.db.database import Base, async_engine, AsyncSessionLocal
from src.db.models import EventORM


STORE_JSONL_MAP = {
    "ST1008":  ROOT / "results" / "real_events.jsonl",
    "STORE_1": ROOT / "results" / "store1_events.jsonl",
    "STORE_2": ROOT / "results" / "store2_events.jsonl",
}


async def ensure_tables() -> None:
    """Create all tables if they don't already exist."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[OK] Database tables ensured")


async def count_store_events(store_id: str) -> int:
    """Count existing events in DB for a store."""
    from sqlalchemy import func, select
    async with AsyncSessionLocal() as db:
        q = await db.execute(
            select(func.count()).where(EventORM.store_id == store_id)
        )
        return q.scalar() or 0


async def import_jsonl_events(store_id: str, jsonl_path: Path, force: bool = False) -> int:
    """
    Import events from a JSONL file into the database.
    Skips import if data already exists (unless force=True).
    Returns number of events imported.
    """
    if not jsonl_path.exists():
        print(f"[SKIP] {store_id}: {jsonl_path.name} not found")
        return 0

    existing = await count_store_events(store_id)
    if existing > 0 and not force:
        print(f"[SKIP] {store_id}: {existing} events already in DB (use --force to re-import)")
        return 0

    # Parse JSONL
    events = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    if not events:
        print(f"[WARN] {store_id}: {jsonl_path.name} is empty")
        return 0

    print(f"[...] {store_id}: importing {len(events)} events from {jsonl_path.name}")

    # Batch insert
    inserted = 0
    async with AsyncSessionLocal() as db:
        for e in events:
            try:
                ts_raw = e.get("timestamp", "")
                # Parse ISO timestamp (handle timezone-aware and naive)
                ts = datetime.fromisoformat(ts_raw) if ts_raw else datetime.now(timezone.utc)
                # Convert to naive UTC for SQLite compatibility
                if ts.tzinfo is not None:
                    ts = ts.replace(tzinfo=None)

                db_evt = EventORM(
                    event_id=e.get("event_id", f"evt_{random.randint(100000, 999999)}"),
                    store_id=e.get("store_id", store_id),
                    camera_id=e.get("camera_id", "CAM1"),
                    visitor_id=e.get("visitor_id", "unknown"),
                    event_type=e.get("event_type", "ENTRY"),
                    timestamp=ts,
                    zone_id=e.get("zone_id"),
                    dwell_ms=e.get("dwell_ms"),
                    confidence=float(e.get("confidence", 1.0)),
                    is_staff=bool(e.get("is_staff", False)),
                    session_seq=int(e.get("session_seq", 1)),
                    metadata_=e.get("metadata", {}),
                )
                db.add(db_evt)
                inserted += 1
            except Exception as row_err:
                print(f"  [WARN] Skipping event {e.get('event_id', '?')}: {row_err}")

        await db.commit()

    print(f"[OK]  {store_id}: {inserted} events imported into database")
    return inserted


async def run_all(force: bool = False, skip_demo: bool = False) -> None:
    """Main entry point: ensure tables, import all stores."""
    print("=" * 60)
    print("POPULATING DATABASE WITH ALL STORE EVENTS")
    print("=" * 60)

    await ensure_tables()

    total = 0
    for store_id, jsonl_path in STORE_JSONL_MAP.items():
        n = await import_jsonl_events(store_id, jsonl_path, force=force)
        total += n

    print(f"\n[DONE] Total events imported: {total}")

    # Optionally run the demo to also populate POS correlation for ST1008
    if not skip_demo:
        st1008_events = await count_store_events("ST1008")
        from sqlalchemy import func, select
        from src.db.models import POSTransactionORM
        async with AsyncSessionLocal() as db:
            pos_q = await db.execute(
                select(func.count()).where(POSTransactionORM.store_id == "ST1008")
            )
            pos_count = pos_q.scalar() or 0

        if pos_count == 0:
            print("\n[...] Running demo to populate ST1008 POS correlation data...")
            try:
                from scripts.generate_demo import run_demo
                await run_demo()
                print("[OK]  ST1008 POS demo complete")
            except Exception as demo_err:
                print(f"[WARN] Demo failed (non-fatal): {demo_err}")
        else:
            print(f"\n[SKIP] ST1008 POS already populated ({pos_count} transactions)")

    print("\n" + "=" * 60)
    print("DATABASE POPULATION COMPLETE")
    print("=" * 60)
    
    # Print summary
    print("\nSummary:")
    for store_id in STORE_JSONL_MAP:
        count = await count_store_events(store_id)
        print(f"   {store_id:12s}: {count:4d} events in DB")


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate database with all store events")
    parser.add_argument("--force", action="store_true",
                        help="Re-import even if data already exists")
    parser.add_argument("--skip-demo", action="store_true",
                        help="Skip POS demo generation for ST1008")
    args = parser.parse_args()

    asyncio.run(run_all(force=args.force, skip_demo=args.skip_demo))


if __name__ == "__main__":
    main()
