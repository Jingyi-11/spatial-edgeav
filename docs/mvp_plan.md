# Spatial EdgeAV MVP Plan

This document defines the first usable MVP for Spatial EdgeAV:

```text
MacBook development baseline
  -> continuous video stream
  -> spatial rule engine
  -> event log and snapshot
  -> model training/export on Windows/WSL
  -> RK3576 edge deployment path
```

The project should not start as a large VLA model project. The MVP should prove
that the system can run like real device software, then add model deployment and
VLA-style instruction-to-action rules.

## 1. Machine Responsibilities

### MacBook

Role: project center and portable development machine.

Use MacBook for:

- Repository management, docs, configs, scripts.
- Continuous video stream baseline.
- Spatial zones, dwell-time rules, event schema, action policy.
- Local OpenCV prototype before C++/RK3576 port.
- SSH control of Windows/WSL and RK3576.

Camera placement:

- For travel/local baseline: plug USB camera into MacBook.
- For real edge validation: leave USB camera plugged into RK3576.

### Windows / WSL

Role: model factory.

Put these data and artifacts on Windows/WSL:

- Raw training videos and images.
- Labeled datasets.
- YOLO dataset YAML and class definitions.
- Train/val/test splits.
- Training runs and checkpoints.
- Calibration images for INT8 quantization.
- ONNX export results.
- Model evaluation reports.

Recommended layout:

```text
~/spatial-edgeav-data/
  raw/
    videos/
    images/
  datasets/
    person_zone_v1/
      images/
        train/
        val/
      labels/
        train/
        val/
      data.yaml
  calib/
    person_zone_v1/
  runs/
    yolo/
  exports/
    onnx/
    rknn/
  reports/
```

Do not put large raw datasets in the main Git repository. Keep only configs,
small sample frames, scripts, and result summaries in Git.

### RK3576

Role: real edge runtime.

Use RK3576 for:

- V4L2 USB camera capture.
- ALSA audio capture later.
- RKNN Runtime inference.
- C++ pipeline latency and FPS validation.
- MQTT/REST/device action tests.
- systemd service, logs, watchdog-style robustness.

## 2. Continuous Video Stream Baseline

The current MacBook baseline should evolve from a quick camera test into a
continuous stream prototype:

```text
camera capture
  -> frame timestamp
  -> frame queue
  -> detector
  -> spatial rule engine
  -> action dispatcher
  -> event log / snapshot / preview
```

### MVP behavior

The stream should keep running until the user presses `q`.

Per frame:

1. Read frame from camera.
2. Assign timestamp and frame id.
3. Run detector.
4. Convert detections to a unified object format.
5. Evaluate spatial rules.
6. Trigger actions when rule conditions are satisfied.
7. Draw preview overlay.
8. Track FPS and dropped frames.

### Unified observation format

The spatial/rule layer should consume this shape, regardless of detector source:

```json
{
  "frame_id": 1024,
  "ts_ms": 1790000000000,
  "width": 1280,
  "height": 720,
  "objects": [
    {
      "track_id": 3,
      "class_name": "person",
      "confidence": 0.86,
      "bbox_xywh": [320, 180, 90, 240]
    }
  ]
}
```

MacBook MVP can fill `objects` from motion boxes. RK3576 later fills the same
format from YOLO/RKNN results.

### Unified event format

```json
{
  "ts_ms": 1790000002500,
  "frame_id": 1088,
  "type": "restricted_zone_dwell",
  "target": "person",
  "zone": "restricted_area",
  "duration_ms": 2000,
  "actions": ["snapshot", "mqtt_publish"],
  "snapshot": "runs/mac_baseline/snapshots/event_1790000002500.jpg"
}
```

### Rule example

```yaml
rules:
  - id: restricted_person_dwell
    instruction: "If a person enters the restricted area for more than 2 seconds, track and report."
    target:
      class_name: person
    condition:
      zone: restricted_area
      relation: intersects
      duration_ms: 2000
    actions:
      - snapshot
      - event_log
      - mqtt_publish
    cooldown_ms: 3000
```

## 3. Model Part

The first model path should be simple and credible:

```text
Windows/WSL
  -> collect/label data
  -> train YOLO
  -> evaluate
  -> export ONNX
  -> prepare calibration set
  -> convert to RKNN

RK3576
  -> load .rknn
  -> run inference on V4L2 frames
  -> postprocess YOLO
  -> feed objects into same spatial rule engine
```

### Model MVP target

Start with one class:

```text
person
```

Do not start with a large multi-class dataset. The first demo should prove:

```text
person detected
  -> inside restricted zone
  -> dwell over threshold
  -> snapshot/event/MQTT
```

### Training flow on Windows/WSL

1. Collect raw videos/images.
2. Label `person` boxes.
3. Export YOLO format.
4. Train a small model:

```bash
yolo detect train data=data.yaml model=yolov8n.pt imgsz=640 epochs=50
```

5. Evaluate:

```bash
yolo detect val model=runs/detect/train/weights/best.pt data=data.yaml
```

6. Export ONNX:

```bash
yolo export model=runs/detect/train/weights/best.pt format=onnx imgsz=640 opset=12
```

7. Prepare 100 to 300 calibration images for INT8 conversion.
8. Convert ONNX to RKNN using RKNN Toolkit2.

### Model artifacts to keep

Keep in Git only:

```text
training/video/README.md
conversion/export_onnx.py
conversion/onnx_to_rknn.py
configs/model.yaml
docs/model_pipeline.md
docs/rknn_deployment.md
```

Keep outside Git or in release artifacts:

```text
*.pt
*.onnx
*.rknn
raw videos
large datasets
training runs
```

## 4. Project Parts

### Part 0: Travel Readiness

Goal: prove MacBook-only work is possible.

Flow:

```text
USB camera on MacBook
  -> ffmpeg smoke test
  -> OpenCV baseline
  -> event log and snapshot
```

Done when:

- `camera_smoke.mp4` is created.
- `preview.jpg` is created.
- `events.jsonl` records at least one restricted-zone event.
- Snapshot is saved for that event.

### Part 1: Continuous Stream Baseline

Goal: turn the one-file Mac baseline into a stable continuous video stream.

Flow:

```text
capture loop
  -> frame metadata
  -> detector abstraction
  -> observation object
  -> rule engine
  -> actions
```

Deliverables:

- `configs/camera.yaml`
- `configs/zones.yaml`
- `configs/rules.yaml`
- `scripts/mac_stream_baseline.py`
- `runs/mac_stream/events.jsonl`
- `runs/mac_stream/snapshots/`

### Part 2: Spatial Rule Engine

Goal: make the spatial logic independent of camera and detector.

Flow:

```text
observation JSON
  -> zone geometry
  -> per-object state
  -> dwell/inside/line conditions
  -> event JSON
```

Deliverables:

- `src/spatial/` later in C++.
- Python prototype first.
- Unit tests for zone intersection, dwell time, cooldown.
- Rule examples in YAML.

### Part 3: Action Dispatcher

Goal: turn events into device actions.

Flow:

```text
event
  -> action policy
  -> snapshot
  -> event log
  -> optional MQTT
  -> optional REST
```

Deliverables:

- JSONL event log.
- Snapshot directory.
- MQTT payload schema.
- REST payload schema.

### Part 4: Model Factory on Windows/WSL

Goal: produce a deployable object detector.

Flow:

```text
raw data
  -> labeling
  -> YOLO dataset
  -> training
  -> evaluation
  -> ONNX export
  -> calibration set
```

Deliverables:

- `best.pt`
- `best.onnx`
- validation metrics
- calibration images
- model report

### Part 5: RKNN Conversion

Goal: convert ONNX model to RKNN INT8.

Flow:

```text
ONNX model
  -> RKNN Toolkit2 config
  -> INT8 calibration
  -> .rknn export
  -> simulator/basic accuracy check
```

Deliverables:

- `person_yolo_int8.rknn`
- conversion log
- input/output tensor metadata
- quantization notes

### Part 6: RK3576 Runtime

Goal: run the real edge pipeline.

Flow:

```text
V4L2 capture
  -> preprocess
  -> RKNN inference
  -> YOLO postprocess/NMS
  -> tracking
  -> spatial rule engine
  -> actions
```

Deliverables:

- C++17 runtime.
- CMake build.
- RKNN model loading.
- V4L2 camera capture.
- JSONL event output.
- Snapshot output.

### Part 7: Service and Benchmark

Goal: make it look and behave like deployable device software.

Flow:

```text
edgeav binary
  -> config files
  -> systemd service
  -> logging
  -> benchmark report
```

Deliverables:

- `deploy/edgeav.service`
- `deploy/install.sh`
- `docs/benchmark.md`
- FPS, latency, CPU, memory, NPU, temperature results.

## 5. MVP Definition

The MVP is complete when the system can demonstrate this:

```text
Person enters restricted area for more than 2 seconds.
System detects event.
System saves snapshot.
System writes structured JSONL event.
System can run either on MacBook baseline or RK3576 edge runtime.
```

### MVP Scope

Required:

- MacBook continuous video baseline.
- YAML zones and rules.
- Event JSONL.
- Snapshot action.
- One-class YOLO training path.
- ONNX export path.
- RKNN conversion plan.
- RK3576 camera discovery and runtime skeleton.

Optional after MVP:

- ALSA audio.
- MQTT publish.
- REST endpoint.
- Recording clips.
- Multi-object tracking.
- Line crossing.
- Homography.
- PTZ.
- QAT and pruning.

### MVP Demo Script

MacBook demo:

```bash
bash scripts/mac_ffmpeg_smoke_test.sh 0
python3 scripts/mac_camera_baseline.py --config configs/mac_baseline.yaml --camera 0
```

RK3576 camera check:

```bash
ssh rk3576
v4l2-ctl --list-devices
v4l2-ctl --stream-mmap=3 --stream-count=120 -d /dev/video-camera0
```

Final RK3576 demo target:

```bash
./edgeav_runtime --config configs/service.yaml
```

## 6. Recommended Build Order

Build in this order:

1. MacBook camera smoke test.
2. MacBook continuous stream baseline.
3. YAML zone/rule config split.
4. Rule engine and event schema.
5. Snapshot/event actions.
6. Windows/WSL dataset and YOLO training.
7. ONNX export.
8. RKNN conversion.
9. RK3576 V4L2 capture.
10. RK3576 RKNN inference.
11. C++ spatial/action runtime.
12. systemd and benchmark.

The first public-facing MVP should emphasize the complete edge-system workflow,
not just detection accuracy.
