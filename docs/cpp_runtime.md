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

## Phase 5B: RKNN C API Smoke Test

The C/C++ runtime now has a small `rknn_detector` module:

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
mean inference: about 34-36 ms
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
boundary, NPU execution, output retrieval, SDK/driver version, tensor metadata,
and the C++ YOLOv8 optimized-head postprocess path. Detection quality is still
validated by the Python camera service until Phase 5D feeds real camera frames
through the C++ runtime.

## Phase 5C: C++ YOLOv8 Optimized-Head Decode

The C/C++ runtime now decodes the Rockchip optimized YOLOv8n RKNN output layout
inside `src/rknn_detector.cpp`.

Implemented:

```text
9 RKNN outputs
  -> group tensors into 80x80, 40x40, 20x20 branches
  -> match box distribution, class scores, and optional score_sum tensors
  -> dequantize INT8/UINT8 tensor values using scale and zero point
  -> use class score + score_sum for early candidate filtering
  -> run DFL only on selected candidates
  -> run same-class IoU + containment NMS
  -> write postprocess metadata and detections to RKNN JSON report
```

The implementation intentionally avoids STL containers in this hot path and
uses fixed-size arrays instead. This keeps the board-side build less dependent
on host C++ standard library availability and makes the memory ceiling explicit
for embedded deployment.

Verified RK3576 result:

```text
postprocess status: ok
type: rockchip_yolov8_optimized_head
output groups: 3
candidate grids: 80x80, 40x40, 20x20
mean inference: 34.466 ms
detections after NMS: 0
```

Zero detections are expected for this smoke test because the runtime currently
feeds a zero-filled synthetic input buffer to the model. The value of this phase
is that the C++ runtime can now recognize the RKNN output layout, dequantize
tensor values, execute candidate filtering, DFL, and NMS, and produce the same
kind of JSON detection surface that the live camera service needs.

## Current Boundary

The Phase 5C runtime can load and execute the RKNN model through the C API and
run C++ YOLOv8 optimized-head postprocessing on the returned tensors. The
current full live-camera detection service remains:

```text
scripts/rk3576_rknn_camera_loop.py
systemd/spatial-edgeav-rknn.service
```

## Phase 5D: Real V4L2 Frame Input Path

The C/C++ runtime now has the first real-camera input path for RKNN inference:

```text
V4L2 YUYV frame
  -> nearest-neighbor resize
  -> YUV to RGB conversion
  -> NHWC uint8 640x640 RKNN input tensor
  -> RKNN C API inference
  -> C++ YOLOv8 optimized-head postprocess
  -> RKNN JSON report with input_source=v4l2_yuyv_rgb_resized
```

Implemented files:

```text
include/yuv.h
src/yuv.c
include/rknn_detector.h
src/rknn_detector.cpp
src/edgeav_runtime.cpp
Makefile
```

The runtime still supports the zero-filled synthetic RKNN smoke path. When a
real V4L2 YUYV camera frame is available, it captures a frame, converts it into
the RKNN input tensor, and passes that buffer to the same RKNN/postprocess path.
For debugging, `--rknn-input-dump` can write the resized RGB tensor as a PPM
image so the exact model input can be inspected when detections are missing.

Run after deploying the C/C++ runtime:

```bash
make deploy-cpp-runtime-board
make run-cpp-live-yuyv-board
make annotate-cpp-live-yuyv
```

The live target copies the runtime report, heartbeat, RKNN report, and PPM model
input dump back to `runs/rk3576_cpp_runtime/` after the board run finishes.
The annotation target draws detections on the PPM input dump and works without
third-party Python packages when both input and output are PPM files.

Current validation status:

```text
Mac build: ok
Mac simulated runtime: ok
RK3576 deploy build: ok
RK3576 synthetic RKNN smoke: ok
RK3576 live YUYV camera test: ok after stopping the Python systemd service
```

Verified live YUYV result:

```text
mode: v4l2
camera: /dev/video73, 1280x720, YUYV
frames processed: 3
measured FPS: 9.996
input_source: v4l2_yuyv_rgb_resized
RKNN mean inference: 48.046 ms
postprocess status: ok
detections after NMS: 0
reports:
  runs/rk3576_cpp_runtime/edgeav_runtime_live_yuyv_report.json
  runs/rk3576_cpp_runtime/edgeav_runtime_live_yuyv_rknn_report.json
debug input:
  /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_live_yuyv_input.ppm
```

The dumped model input was converted locally to PNG for inspection. The frame is
a valid ceiling/indoor scene with a warm color cast, not a black frame or an
obvious RGB/BGR channel swap. The zero-detection result is therefore consistent
with the image content, because the captured scene does not contain a person or
another clear COCO object.

Follow-up live detection validation:

```text
frames processed: 3
measured FPS: 9.979
RKNN mean inference: 39.674 ms
candidates before NMS: 20
detections after NMS: 3
detections:
  class 56 chair, confidence 0.8001
  class 39 bottle, confidence 0.4745
  class 39 bottle, confidence 0.3294
annotation:
  runs/rk3576_cpp_runtime/edgeav_runtime_live_yuyv_annotated.ppm
```

This validates the full path from USB camera capture to RKNN NPU inference,
C++ postprocess, JSON detection output, and visual artifact generation.

Before running the live C++ camera test again, stop the Python service that owns
the camera device, then restart it after the test:

```bash
sudo systemctl stop spatial-edgeav-rknn.service
make run-cpp-live-yuyv-board
sudo systemctl start spatial-edgeav-rknn.service
```

The next engineering step is to validate the live C++ YUYV path with the Python
service stopped against richer scenes by inspecting the dumped RKNN input image,
then add MJPEG decode or a GStreamer/RGA preprocessing path so the runtime can
use the same high-FPS camera format as the existing Python service.
