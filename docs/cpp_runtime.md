# C/C++ Runtime Migration

Phase 5 starts the migration from the Python RKNN camera loop to a C/C++
runtime. The goal is not to delete Python tooling. Python remains useful for
training, export, conversion, benchmarking, and report generation. The C/C++
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

This is intentionally a migration scaffold. It proves the C/C++ service loop,
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

The deploy target copies the C/C++ sources to:

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
C/C++ at once would make debugging harder because capture, preprocess, RKNN
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

The Phase 5A runtime does not yet run the RKNN model. The current RKNN inference
service remains:

```text
scripts/rk3576_rknn_camera_loop.py
systemd/spatial-edgeav-rknn.service
```

The next engineering step is to add a small `rknn_detector` C++ module that
loads the accepted INT8 RKNN model, calls `rknn_init`, `rknn_inputs_set`,
`rknn_run`, and `rknn_outputs_get`, then writes output tensor metadata before
implementing YOLO postprocessing.
