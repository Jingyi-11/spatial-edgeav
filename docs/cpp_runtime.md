# C++ Runtime Migration

Phase 5 starts the migration from the Python RKNN camera loop to a C++
runtime. The goal is not to delete Python tooling. Python remains useful for
training, export, conversion, benchmarking, and report generation. The C++
runtime owns the board-side real-time hot path.

## Target Runtime Shape

```text
V4L2 or GStreamer camera capture
  -> image preprocess
  -> RKNN C API inference
  -> YOLOv8 decode, DFL, NMS
  -> spatial event generation
  -> heartbeat/report/event JSON output
  -> systemd service
```

## Phase 5A Status

Implemented:

```text
src/edgeav_runtime.cpp
src/camera_capture.cpp
src/pipeline.cpp
src/yuv.cpp
scripts/deploy_cpp_runtime_to_rk3576.sh
make edgeav-runtime
make run-edgeav-runtime-sim
make deploy-cpp-runtime-board
```

The first C++ executable is `build/edgeav_runtime`. It currently provides the
runtime shell:

- command-line configuration
- V4L2 capture path through the existing C camera module
- simulated frame path for Mac and non-camera board validation
- `heartbeat.json` output
- `report.json` output
- frame count, bytes processed, elapsed time, and measured FPS

This is intentionally a migration scaffold. It proves the C++ service loop,
build target, board deployment, and JSON observability before moving the RKNN
hot path.

## Local Smoke Test

```bash
make edgeav-runtime
make run-edgeav-runtime-sim
cat out/edgeav_runtime_report.json
```

The simulation path avoids camera-device conflicts and can run on macOS, WSL,
and RK3576.

## RK3576 Smoke Test

```bash
make deploy-cpp-runtime-board
```

The deploy target copies the C++ sources to:

```text
/home/kickpi/spatial-edgeav/cpp_runtime_src/
```

Then it builds `build/edgeav_runtime` on RK3576 and runs a non-camera simulated
smoke test. Reports are copied back to:

```text
runs/rk3576_cpp_runtime/edgeav_runtime_sim_report.json
runs/rk3576_cpp_runtime/edgeav_runtime_sim_heartbeat.json
```

Verified RK3576 simulated runtime result:

```text
status: ok
runtime: edgeav_cpp_runtime
mode: simulate
frames_processed: 30
bytes_processed: 3456000
measured_fps: 29.457
elapsed_ms: 1018.450
error: null
```

The deploy step intentionally uses `--simulate` because the Python RKNN
systemd service may already own the real camera device. This keeps Phase 5A
validation independent from the live Phase 4 service.

## Linux C Build Notes

Two portability fixes were needed when compiling on RK3576 with strict C11:

- `clock_gettime` and `CLOCK_MONOTONIC` require `_POSIX_C_SOURCE=200809L`.
- `linux/videodev2.h` references `struct timespec`, so `<time.h>` must be
  visible before the V4L2 declarations are compiled.

These are normal embedded Linux C portability details: system headers often
expose different declarations depending on feature macros and include order.

## Why Start With a Runtime Shell

The Python baseline has already proven the AI pipeline. Moving everything to
C++ at once would make debugging harder because capture, preprocess, RKNN
API calls, output decoding, and service behavior could all fail together.

The staged migration keeps each boundary testable:

```text
Phase 5A: C++ runtime shell + capture/heartbeat/report
Phase 5B: RKNN C API model load and single-image inference
Phase 5C: YOLOv8 output decode, DFL, and NMS in C++
Phase 5D: live V4L2 camera -> RKNN -> detections loop
Phase 5E: spatial rules and JSONL events in C++
Phase 5F: systemd service replacement for Python loop
```

## Current Boundary

## Phase 5B: RKNN C API Smoke Test

The C++ runtime now has a small `rknn_detector` module:

```text
include/rknn_api_compat.h
include/rknn_detector.h
src/rknn_detector.cpp
```

It dynamically loads `librknnrt.so` with `dlopen`, then calls the RKNN C API
boundary:

```text
rknn_init
rknn_query
rknn_inputs_set
rknn_run
rknn_outputs_get
rknn_outputs_release
rknn_destroy
```

The repo intentionally keeps a minimal compatibility header instead of requiring
`rknn_api.h` to exist on the Mac. The RK3576 board currently has
`/usr/lib/librknnrt.so`, but no system-wide `rknn_api.h`.

Run through the existing deploy target:

```bash
make deploy-cpp-runtime-board
```

Verified RK3576 C API smoke result:

```text
status: ok
model: /home/kickpi/spatial-edgeav/models/yolov8n/yolov8n_rockchip_rk3576_i8.rknn
library: /usr/lib/librknnrt.so
RKNN API: 2.3.2
RKNN driver: 0.9.7
inputs: 1
outputs: 9
mean inference: 34.568 ms
```

The generated report is:

```text
runs/rk3576_cpp_runtime/edgeav_runtime_rknn_report.json
```

The tensor metadata confirms the accepted Rockchip optimized YOLOv8n RKNN
layout:

```text
input:  [1, 640, 640, 3], NHWC, INT8
output: 9 tensors across 80x80, 40x40, and 20x20 branches
```

This test uses a zero-filled synthetic input buffer. It validates the RKNN C API
boundary, NPU execution, output retrieval, SDK/driver version, and tensor
metadata. It does not yet validate detection quality because YOLOv8 DFL/NMS
postprocessing is still in Python.

## Current Boundary

The Phase 5B runtime can load and execute the RKNN model through the C API. The
current full detection service remains:

```text
scripts/rk3576_rknn_camera_loop.py
systemd/spatial-edgeav-rknn.service
```

The next engineering step is Phase 5C: port YOLOv8 output decoding, DFL,
candidate filtering, and NMS from Python to C++.
