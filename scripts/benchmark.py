"""
benchmark.py – Performance and latency benchmarking script.

Processes a sample video segment, measures pipeline throughput (FPS), peak memory,
and FastAPI ingestion latency, then compiles the performance report.
"""

import os
import sys
import time
from pathlib import Path
import psutil
import numpy as np
import cv2
from fastapi.testclient import TestClient

# Add workspace root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from src.scanner import scan
from src.detector import PersonDetector
from src.tracker import ByteTracker
from src.reid import OSNetReID
from src.tracker_lifecycle import TrackLifecycleManager
from src.event_emitter import EventEmitter
from src.session_manager import SessionManager
from src.api.main import app

def get_memory_use_mb() -> float:
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def main():
    print("Initializing components for performance benchmark...")
    start_mem = get_memory_use_mb()
    
    data_root = os.environ.get(
        "DATA_ROOT", r"C:\Users\BIT\OneDrive\Documents\CCTV\CCTV Footage"
    )
    report = scan(data_root)
    valid_videos = [v for v in report.videos if v.valid]
    if not valid_videos:
        print("[ERROR] No valid videos found for benchmarking. Exiting.")
        sys.exit(1)
        
    video_path = valid_videos[0].path
    print(f"Benchmarking with video: {Path(video_path).name}")
    
    # Init components
    detector = PersonDetector(device="cpu")
    tracker = ByteTracker()
    reid = OSNetReID(device="cpu")
    session_mgr = SessionManager(store_id="S1")
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Failed to open video {video_path}")
        sys.exit(1)
        
    emitter = EventEmitter(
        store_id="S1",
        camera_id="CAM1",
        store_layout=report.store_layout,
        session_manager=session_mgr,
        reid_gallery=reid,
        fps=30.0,
    )
    
    lifecycle_manager = TrackLifecycleManager(exit_line=emitter.exit_line)
    
    # 1. Warm up
    print("Warming up models...")
    for _ in range(5):
        ret, frame = cap.read()
        if not ret:
            break
        detections = detector.detect(frame)
        _ = tracker.update(detections, frame)
        
    # Reset video capture to frame 0
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    
    # 2. Run benchmark loop
    print("Running benchmarking loop (100 frames)...")
    num_frames = 100
    frame_times = []
    mem_readings = []
    events_generated = 0
    events_list = []
    
    start_time = time.time()
    
    for idx in range(num_frames):
        f_start = time.time()
        ret, frame = cap.read()
        if not ret:
            break
            
        detections = detector.detect(frame)
        raw_tracks = tracker.update(detections, frame)
        
        h, w = frame.shape[:2]
        frame_time = emitter._frame_time(idx)
        valid_active_infos, lifecycle_signals = lifecycle_manager.update(
            raw_tracks, frame_time, w, h
        )
        
        for info in valid_active_infos:
            if info.visitor_id is None:
                x1, y1, x2, y2 = map(int, info.xyxy)
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)
                crop = frame[y1:y2, x1:x2]
                visitor_id, uncertain = reid.identify(crop, idx)
                info.visitor_id = visitor_id
                info.uncertain_reid = uncertain
                
        events = emitter.process_frame(
            frame,
            valid_active_infos,
            idx,
            lifecycle_signals=lifecycle_signals,
        )
        events_generated += len(events)
        events_list.extend([e.to_dict() for e in events])
        
        f_end = time.time()
        frame_times.append(f_end - f_start)
        mem_readings.append(get_memory_use_mb())
        
    total_pipeline_time = time.time() - start_time
    cap.release()
    
    avg_fps = num_frames / total_pipeline_time
    peak_ram = max(mem_readings)
    ram_overhead = peak_ram - start_mem
    
    print(f"\nPipeline Benchmarking Complete:")
    print(f"  Processed {num_frames} frames in {total_pipeline_time:.2f}s")
    print(f"  Average FPS: {avg_fps:.1f} frames/sec")
    print(f"  Peak RAM: {peak_ram:.1f} MB (Overhead: {ram_overhead:.1f} MB)")
    print(f"  Events generated: {events_generated}")
    
    # 3. Benchmark API Ingestion Latency
    print("\nBenchmarking API Ingestion Latency...")
    client = TestClient(app)
    
    # Ingest batch of events
    api_latencies = []
    if events_list:
        # Measure batch ingestion
        b_start = time.time()
        resp = client.post("/events/ingest", json=events_list)
        b_end = time.time()
        batch_latency_ms = (b_end - b_start) * 1000
        print(f"  Batch ingestion ({len(events_list)} events): {batch_latency_ms:.1f} ms")
        
        # Measure individual event latency
        for evt in events_list[:20]:
            e_start = time.time()
            resp = client.post("/events/ingest", json=[evt])
            e_end = time.time()
            api_latencies.append((e_end - e_start) * 1000)
    else:
        # Fallback if no real events generated in 100 frames
        mock_event = {
            "event_id": "mock-event-id",
            "store_id": "S1",
            "camera_id": "CAM1",
            "visitor_id": "mock-visitor-id",
            "event_type": "ENTRY",
            "timestamp": "2026-05-30T12:00:00Z",
            "confidence": 0.95,
            "is_staff": False,
            "session_seq": 1,
        }
        for _ in range(20):
            e_start = time.time()
            resp = client.post("/events/ingest", json=[mock_event])
            e_end = time.time()
            api_latencies.append((e_end - e_start) * 1000)
            
    avg_api_latency = np.mean(api_latencies) if api_latencies else 0.0
    print(f"  Average Single API Latency: {avg_api_latency:.1f} ms")
    
    # 4. Generate report
    report_lines = []
    report_lines.append("# Pipeline Performance and Latency Report\n")
    report_lines.append("Benchmarked on the target machine with real video inputs.\n")
    report_lines.append("## Core Processing Metrics\n")
    report_lines.append("| Metric | Value | Details |")
    report_lines.append("|---|---|---|")
    report_lines.append(f"| **Average FPS** | {avg_fps:.1f} | Frame processing speed including YOLO & OSNet |")
    report_lines.append(f"| **Peak RAM** | {peak_ram:.1f} MB | Maximum memory usage of the pipeline process |")
    report_lines.append(f"| **Memory Overhead** | {ram_overhead:.1f} MB | Memory consumed above baseline |")
    report_lines.append(f"| **Average API Latency** | {avg_api_latency:.1f} ms | Average response latency of single event POST |")
    report_lines.append(f"| **Events Processed** | {events_generated} | Number of events in 100 frame run |")
    
    report_path = Path(__file__).parent.parent / "evaluation" / "performance_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write("\n".join(report_lines) + "\n")
        
    print(f"\n[OK] Performance report written to {report_path.name}")


if __name__ == "__main__":
    main()
