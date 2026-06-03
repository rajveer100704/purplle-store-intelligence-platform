import os
import cv2
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from src.detector import PersonDetector
from src.tracker import ByteTracker

video_path = r"C:\Users\BIT\OneDrive\Documents\CCTV\CCTV Footage\CAM 1.mp4"
detector = PersonDetector(model_path="yolov8s.pt", conf_threshold=0.25, device="cpu")
tracker = ByteTracker(frame_rate=30.0)

cap = cv2.VideoCapture(video_path)
frame_idx = 0
min_x = 9999
max_x = -9999
all_x_coords = []

print("Scanning CAM 1.mp4 to find all X coordinates...")
while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    # Process every 30th frame for speed
    if frame_idx % 30 == 0:
        detections = detector.detect(frame)
        tracks = tracker.update(detections, frame)
        for t in tracks:
            x1, y1, x2, y2 = t.xyxy
            cx = (x1 + x2) / 2
            all_x_coords.append(cx)
            if cx < min_x:
                min_x = cx
            if cx > max_x:
                max_x = cx
    frame_idx += 1

cap.release()

print(f"Total frames processed: {frame_idx}")
print(f"X coordinate range: min={min_x:.1f}, max={max_x:.1f}")
if all_x_coords:
    all_x_coords.sort()
    percentiles = [5, 10, 25, 50, 75, 90, 95]
    print("X percentiles:")
    for p in percentiles:
        idx = int(len(all_x_coords) * p / 100)
        print(f"  {p}%: {all_x_coords[idx]:.1f}")
