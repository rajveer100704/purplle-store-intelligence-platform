import os
import cv2
import sys
from pathlib import Path

# Add root to python path
sys.path.append(str(Path(__file__).parent))

from src.detector import PersonDetector
from src.tracker import ByteTracker

video_path = r"C:\Users\BIT\OneDrive\Documents\CCTV\CCTV Footage\CAM 1.mp4"
if not os.path.exists(video_path):
    print("Video file not found:", video_path)
    sys.exit(1)

detector = PersonDetector(model_path="yolov8s.pt", conf_threshold=0.25, device="cpu")
tracker = ByteTracker(frame_rate=30.0)

cap = cv2.VideoCapture(video_path)
frame_idx = 0
track_history = {}

print("Starting track coordinate inspection for CAM 1.mp4 (first 300 frames)...")
while frame_idx < 300:
    ret, frame = cap.read()
    if not ret:
        break
    
    detections = detector.detect(frame)
    tracks = tracker.update(detections, frame)
    
    for t in tracks:
        tid = t.track_id
        x1, y1, x2, y2 = t.xyxy
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        if tid not in track_history:
            track_history[tid] = []
        track_history[tid].append((frame_idx, cx, cy))
        
    frame_idx += 1

cap.release()

print(f"Processed {frame_idx} frames. Found {len(track_history)} tracks.")
for tid, history in sorted(track_history.items()):
    start_frame, start_x, start_y = history[0]
    end_frame, end_x, end_y = history[-1]
    xs = [pt[1] for pt in history]
    ys = [pt[2] for pt in history]
    print(f"Track {tid}: length={len(history)} frames, frames={start_frame}-{end_frame}")
    print(f"  Start: ({start_x:.1f}, {start_y:.1f}), End: ({end_x:.1f}, {end_y:.1f})")
    print(f"  X-range: [{min(xs):.1f}, {max(xs):.1f}], Y-range: [{min(ys):.1f}, {max(ys):.1f}]")
