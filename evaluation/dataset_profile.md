# CCTV Dataset Profile & Characterization Report

This document characterizes the raw CCTV footage dataset used for development, calibration, and validation of the Store Intelligence Pipeline.

---

## Dataset Inventory Summary

The dataset consists of 5 video files covering different camera views for store `S1` (ST1008):

| Video Filename | Target Camera View | Duration | FPS | Resolution | Bounding Box Count | Crowding Level | Occlusion Level | Lighting Quality |
|---|---|---|---|---|---|---|---|---|
| **CAM 1.mp4** | Entrance / Exit Door | 139.9s | 30.0 | 1920×1080 | High | Moderate | Low (clear path) | Variable (external light) |
| **CAM 2.mp4** | Floor / Lakme display | 125.9s | 30.0 | 1920×1080 | Moderate | Low | Moderate (shelves) | Uniform (LED) |
| **CAM 3.mp4** | Floor / Faces display | 148.0s | 30.0 | 1920×1080 | Moderate | Low | Moderate (shelves) | Uniform (LED) |
| **CAM 4.mp4** | Billing Checkout Queue | 146.0s | 25.0 | 1920×1080 | High | High (queue) | High (self-occlusion)| Uniform (LED) |
| **CAM 5.mp4** | Floor / Rear Displays | 138.7s | 25.0 | 1920×1080 | Low | Low | High (blind spots) | Dimmish |

---

## Profile Characteristics

### 1. Entrance / Exit Flow (CAM 1)
* **Description**: Captures the entry and exit path. This camera is the primary source of truth for overall footfall and customer entry/exit events.
* **Footfall Density**: Average of 3-5 concurrent persons.
* **Occlusion Level**: Low. Individuals are clearly separated except during rapid group arrivals.
* **Lighting**: Specular reflections and high contrast from the street-facing door require a robust detection model (YOLOv8s).

### 2. Billing Queue Area (CAM 4)
* **Description**: Monitors the cash counter queue. Important for measuring billing wait times and abandonment rates.
* **Footfall Density**: High. Regular queue groupings of 3-6 persons standing in close proximity.
* **Occlusion Level**: High. Customers standing behind one another in the queue cause frequent physical overlap, which is resolved using `ByteTrack`'s Kalman trajectory estimation.
* **Lighting**: Uniform overhead LED lighting.
