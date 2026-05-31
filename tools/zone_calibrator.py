"""
tools/zone_calibrator.py – Interactive zone polygon calibration tool.

Opens a video file, displays the first frame, and lets you draw zone
polygons by clicking.  Saves the calibrated polygons into store_config.json
under the correct camera entry.

Usage
-----
    python tools/zone_calibrator.py --video path/to/clip.mp4 --camera CAM1

Controls
--------
    Left-click   : Add a polygon vertex
    Right-click  : Finish current polygon → prompted for zone_id
    'r'          : Reset current polygon
    'q'          : Quit and save
    's'          : Save without quitting

If run without --video, generates reasonable default grid zones from the
store layout brand list (useful for hackathon demo without manual calibration).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Attempt to import cv2 – if unavailable, only grid-generation mode works
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


CONFIG_PATH = Path(__file__).resolve().parent.parent / "src" / "layout" / "store_config.json"


def generate_default_grid(
    config_path: Path = CONFIG_PATH,
    store_id: str = "ST1008",
    frame_w: int = 1920,
    frame_h: int = 1080,
) -> None:
    """
    Generate default grid-based zone polygons from brand_zones metadata.

    Divides zones along the top and bottom walls into equal-width strips.
    This is a reasonable fallback when no manual calibration is performed.
    """
    with open(config_path) as f:
        data = json.load(f)

    store = data["stores"].get(store_id)
    if not store:
        print(f"Store {store_id} not found in config.")
        return

    brand_zones = store.get("brand_zones", [])
    top_zones = sorted(
        [z for z in brand_zones if z.get("wall") == "top"],
        key=lambda z: z.get("position", 0),
    )
    bottom_zones = sorted(
        [z for z in brand_zones if z.get("wall") == "bottom"],
        key=lambda z: z.get("position", 0),
    )

    margin_x = 0.08  # 8% margin from edges
    usable_w = 1.0 - 2 * margin_x

    # Top wall zones: y from 2% to 12%
    if top_zones:
        strip_w = usable_w / len(top_zones)
        for i, z in enumerate(top_zones):
            x0 = margin_x + i * strip_w
            x1 = x0 + strip_w
            z["polygon"] = [
                [round(x0, 4), 0.02],
                [round(x1, 4), 0.02],
                [round(x1, 4), 0.12],
                [round(x0, 4), 0.12],
            ]

    # Bottom wall zones: y from 88% to 98%
    if bottom_zones:
        strip_w = usable_w / len(bottom_zones)
        for i, z in enumerate(bottom_zones):
            x0 = margin_x + i * strip_w
            x1 = x0 + strip_w
            z["polygon"] = [
                [round(x0, 4), 0.88],
                [round(x1, 4), 0.88],
                [round(x1, 4), 0.98],
                [round(x0, 4), 0.98],
            ]

    with open(config_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"[OK] Default grid polygons generated for {store_id}")
    print(f"     Top wall: {len(top_zones)} zones")
    print(f"     Bottom wall: {len(bottom_zones)} zones")
    print(f"     Saved to {config_path}")


def interactive_calibrate(
    video_path: str,
    camera_id: str,
    store_id: str = "ST1008",
    config_path: Path = CONFIG_PATH,
) -> None:
    """
    Open a video, display first frame, and interactively draw zone polygons.
    """
    if not HAS_CV2:
        print("[ERROR] OpenCV (cv2) is required for interactive calibration.")
        print("        Run: pip install opencv-python")
        sys.exit(1)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open video: {video_path}")
        sys.exit(1)

    ret, frame = cap.read()
    cap.release()
    if not ret:
        print("[ERROR] Cannot read first frame.")
        sys.exit(1)

    h, w = frame.shape[:2]
    print(f"[OK] Frame size: {w}x{h}")
    print(f"[INFO] Left-click to add points. Right-click to finish polygon.")
    print(f"[INFO] Press 'r' to reset, 's' to save, 'q' to quit.")

    # Load existing config
    with open(config_path) as f:
        data = json.load(f)

    store = data["stores"].get(store_id, {})
    brand_zones = store.get("brand_zones", [])
    zone_names = [z["zone_id"] for z in brand_zones]

    current_points: list[tuple[int, int]] = []
    calibrated_zones: dict[str, list[list[float]]] = {}
    display = frame.copy()

    def mouse_callback(event: int, x: int, y: int, flags: int, param: object) -> None:
        nonlocal display, current_points

        if event == cv2.EVENT_LBUTTONDOWN:
            current_points.append((x, y))
            cv2.circle(display, (x, y), 4, (0, 255, 0), -1)
            if len(current_points) > 1:
                cv2.line(
                    display,
                    current_points[-2],
                    current_points[-1],
                    (0, 255, 0),
                    2,
                )
            cv2.imshow("Zone Calibrator", display)

        elif event == cv2.EVENT_RBUTTONDOWN and len(current_points) >= 3:
            # Close polygon
            cv2.line(
                display,
                current_points[-1],
                current_points[0],
                (0, 255, 0),
                2,
            )
            cv2.imshow("Zone Calibrator", display)

            # Prompt for zone name
            remaining = [z for z in zone_names if z not in calibrated_zones]
            print(f"\nAvailable zones: {remaining}")
            name = input("Enter zone_id for this polygon: ").strip().upper()
            if not name:
                print("[SKIP] No name entered, polygon discarded.")
                current_points.clear()
                return

            # Convert to normalised coords
            norm = [[round(px / w, 4), round(py / h, 4)] for px, py in current_points]
            calibrated_zones[name] = norm
            print(f"  -> {name}: {len(norm)} points saved")

            current_points.clear()

    cv2.namedWindow("Zone Calibrator", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Zone Calibrator", min(w, 1280), min(h, 720))
    cv2.setMouseCallback("Zone Calibrator", mouse_callback)
    cv2.imshow("Zone Calibrator", display)

    while True:
        key = cv2.waitKey(0) & 0xFF
        if key == ord("r"):
            current_points.clear()
            display = frame.copy()
            # Redraw existing calibrated zones
            for zid, pts in calibrated_zones.items():
                pixel_pts = [(int(x * w), int(y * h)) for x, y in pts]
                for i in range(len(pixel_pts)):
                    cv2.line(
                        display,
                        pixel_pts[i],
                        pixel_pts[(i + 1) % len(pixel_pts)],
                        (255, 0, 0),
                        2,
                    )
            cv2.imshow("Zone Calibrator", display)
            print("[RESET] Current polygon cleared.")

        elif key == ord("s"):
            _save_calibration(data, store_id, calibrated_zones, config_path)
            print(f"[SAVED] {len(calibrated_zones)} zones to {config_path}")

        elif key == ord("q"):
            _save_calibration(data, store_id, calibrated_zones, config_path)
            print(f"[QUIT] {len(calibrated_zones)} zones saved.")
            break

    cv2.destroyAllWindows()


def _save_calibration(
    data: dict,
    store_id: str,
    calibrated: dict[str, list[list[float]]],
    config_path: Path,
) -> None:
    """Write calibrated polygons back into the store config JSON."""
    store = data["stores"].get(store_id, {})
    for zone in store.get("brand_zones", []):
        if zone["zone_id"] in calibrated:
            zone["polygon"] = calibrated[zone["zone_id"]]

    # Also check billing/queue
    for key in ["billing_zone", "queue_zone"]:
        z = store.get(key)
        if z and z.get("zone_id") in calibrated:
            z["polygon"] = calibrated[z["zone_id"]]

    with open(config_path, "w") as f:
        json.dump(data, f, indent=2)


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Zone Calibration Tool")
    parser.add_argument("--video", default=None, help="Path to video file")
    parser.add_argument("--camera", default="CAM1", help="Camera ID")
    parser.add_argument("--store", default="ST1008", help="Store ID")
    parser.add_argument(
        "--config",
        default=str(CONFIG_PATH),
        help="Path to store_config.json",
    )
    parser.add_argument(
        "--generate-defaults",
        action="store_true",
        help="Generate default grid-based zones (no video needed)",
    )
    args = parser.parse_args()

    if args.generate_defaults:
        generate_default_grid(
            config_path=Path(args.config),
            store_id=args.store,
        )
    elif args.video:
        interactive_calibrate(
            video_path=args.video,
            camera_id=args.camera,
            store_id=args.store,
            config_path=Path(args.config),
        )
    else:
        print("[INFO] No --video provided. Generating default grid zones.")
        generate_default_grid(
            config_path=Path(args.config),
            store_id=args.store,
        )
