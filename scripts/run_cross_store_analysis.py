"""
scripts/run_cross_store_analysis.py – Cross-store analytics runner.

Reads per-store event_statistics.json files from evaluation/
and generates cross-store comparison and coverage reports.

Usage
-----
    python scripts/run_cross_store_analysis.py

    # Custom config or eval directory
    python scripts/run_cross_store_analysis.py \\
        --config src/layout/store_config.json \\
        --eval-dir evaluation
"""

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from src.analytics.cross_store import (
    build_cross_store_report,
    write_json,
    write_validation_md,
    write_coverage_report,
)


def main() -> None:
    workspace_root = Path(__file__).parent.parent

    parser = argparse.ArgumentParser(description="Cross-Store Analytics Runner")
    parser.add_argument(
        "--config",
        default=str(workspace_root / "src" / "layout" / "store_config.json"),
        help="Path to store_config.json",
    )
    parser.add_argument(
        "--eval-dir",
        default=str(workspace_root / "evaluation"),
        help="Directory containing per-store event_statistics.json files",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    eval_dir = Path(args.eval_dir)
    eval_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("CROSS-STORE ANALYTICS")
    print("=" * 60)
    print(f"Config:   {config_path}")
    print(f"Eval dir: {eval_dir}")

    # Build aggregated report from all per-store stats
    report = build_cross_store_report(eval_dir, config_path)

    print(f"\n[OK] Loaded data for {len(report.stores)} store(s):")
    for s in report.stores:
        status = f"{s.visitors} visitors" if s.visitors else "pending (no events yet)"
        print(f"  - {s.store_id}: {status}")

    # Write all outputs
    write_json(report, eval_dir / "cross_store_comparison.json")
    write_validation_md(report, eval_dir / "cross_store_validation.md")
    write_coverage_report(report, eval_dir / "store_coverage_report.md")

    # Copy generated reports to submission/ directory
    submission_dir = workspace_root / "submission"
    submission_dir.mkdir(parents=True, exist_ok=True)
    import shutil
    try:
        shutil.copy2(eval_dir / "cross_store_validation.md", submission_dir / "cross_store_validation.md")
        shutil.copy2(eval_dir / "store_coverage_report.md", submission_dir / "store_coverage_report.md")
        print(f"[OK] Copied reports to {submission_dir}")
    except Exception as e:
        print(f"[WARN] Failed to copy cross-store reports: {e}")

    print("\n[DONE] All cross-store reports written:")
    print(f"  - {eval_dir}/cross_store_comparison.json")
    print(f"  - {eval_dir}/cross_store_validation.md")
    print(f"  - {eval_dir}/store_coverage_report.md")
    print(f"  - {submission_dir}/cross_store_validation.md")
    print(f"  - {submission_dir}/store_coverage_report.md")
    print("=" * 60)


if __name__ == "__main__":
    main()
