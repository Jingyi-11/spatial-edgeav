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

## Phase 5H: Continuous Per-Frame RKNN Runtime

The C/C++ runtime now supports a real continuous inference baseline:

```text
V4L2 YUYV frame callback
  -> YUYV resize/convert to RGB 640x640
  -> persistent RKNN detector context
  -> rknn_inputs_set / rknn_run / rknn_outputs_get
  -> C++ YOLOv8 optimized-head postprocess
  -> per-frame detections + latency JSON
  -> heartbeat + final report
```

Run after deploying the latest C/C++ runtime:

```bash
make deploy-cpp-runtime-board
make run-cpp-continuous-yuyv-board
make annotate-cpp-continuous-yuyv
```

Implemented pieces:

```text
include/rknn_detector.h
src/rknn_detector.cpp
src/edgeav_runtime.cpp
scripts/annotate_rknn_detections.py
Makefile
```

Key runtime changes:

- `rknn_detector_create()` initializes the RKNN runtime once and caches tensor
  attributes and input buffers.
- `rknn_detector_run()` performs one frame of input set, NPU inference, output
  fetch, YOLOv8 postprocess, and detection copy-out.
- `rknn_detector_destroy()` releases the RKNN context and dynamic library.
- `edgeav_runtime --rknn-every-frame` runs preprocess + RKNN + postprocess in
  the V4L2 frame callback.
- `--frames-json` records per-frame latency and top detections.

Verified continuous YUYV result:

```text
frames processed: 30
rknn frames: 30
rknn failures: 0
detections total: 64
measured capture FPS: 9.972
preprocess mean: 12.102 ms
inference mean: 37.717 ms
postprocess mean: 17.951 ms
RKNN end-to-end mean: 69.470 ms
first frame: chair 0.8482
last frame: chair 0.8242, bottle 0.3706
artifacts:
  runs/rk3576_cpp_runtime/edgeav_runtime_continuous_yuyv_report.json
  runs/rk3576_cpp_runtime/edgeav_runtime_continuous_yuyv_frames.json
  runs/rk3576_cpp_runtime/edgeav_runtime_continuous_yuyv_input.ppm
  runs/rk3576_cpp_runtime/edgeav_runtime_continuous_yuyv_annotated.ppm
```

This is the first C/C++ runtime baseline that is directly comparable in shape
to the Python camera loop: it performs per-frame capture, preprocess, NPU
inference, postprocess, and artifact generation. It is still intentionally
simple: inference runs synchronously inside the capture callback and YUYV resize
is CPU-based. The next optimization step is to split capture/inference into a
producer-consumer loop and add MJPEG/GStreamer/RGA preprocessing so camera
capture can run closer to the requested 30 FPS.

## Phase 5I: Latest-Frame Producer-Consumer Runtime

The runtime now has a second continuous mode:

```text
capture callback
  -> copy raw YUYV/MJPEG into one latest-frame buffer
  -> signal worker
  -> immediately return buffer to V4L2

inference worker
  -> copy latest raw frame
  -> YUYV convert or MJPEG decode
  -> resize to RGB 640x640
  -> RKNN inference
  -> YOLOv8 postprocess
  -> per-frame JSON + heartbeat
```

Run:

```bash
make deploy-cpp-runtime-board
make run-cpp-latest-yuyv-board
make annotate-cpp-latest-yuyv
```

The key flag is:

```text
--rknn-latest-frame
```

This flag enables `--rknn-every-frame` and changes the runtime shape from
`synchronous_callback` to `latest_frame_worker`.

Verified latest-frame YUYV result:

```text
frames processed: 30
rknn frames: 30
rknn failures: 0
skipped frames: 0
detections total: 68
measured capture FPS: 9.973
preprocess mean: 11.814 ms
inference mean: 36.768 ms
postprocess mean: 21.232 ms
RKNN end-to-end mean: 71.375 ms
first frame: chair 0.8345, bottle 0.3922
last frame: chair 0.8276, bottle 0.4078
artifacts:
  runs/rk3576_cpp_runtime/edgeav_runtime_latest_yuyv_report.json
  runs/rk3576_cpp_runtime/edgeav_runtime_latest_yuyv_frames.json
  runs/rk3576_cpp_runtime/edgeav_runtime_latest_yuyv_input.ppm
  runs/rk3576_cpp_runtime/edgeav_runtime_latest_yuyv_annotated.ppm
```

The latest-frame YUYV run did not skip frames because the current YUYV camera
mode is already delivering about 10 FPS, and the worker can keep up with that
rate. The benefit of this architecture becomes more important when capture
moves to a higher-FPS MJPEG/GStreamer/RGA path: old frames can be dropped
instead of building latency in a queue, keeping inference aligned with the
newest scene.

Related preprocessing concepts:

- MJPEG can raise camera FPS because the USB camera sends compressed JPEG
  frames instead of raw YUYV bytes. In the verified 720p scene, YUYV was about
  1.84 MB/frame while MJPEG was about 190 KB/frame.
- GStreamer can improve a production pipeline because it already has mature
  media elements for V4L2 capture, JPEG parse/decode, buffering, and appsink
  handoff. It is often easier to build robust streaming pipelines with
  GStreamer than by hand-rolling every buffer transition.
- RGA can improve preprocessing because Rockchip's raster accelerator can do
  resize/color-convert style work outside the CPU. The NPU should be reserved
  for neural network inference; it does not decode JPEG or perform general
  camera format conversion.
- Current C/C++ YUYV preprocessing is CPU-based, and current C/C++ MJPEG
  preprocessing uses CPU `libjpeg`. A later optimization can replace resize
  and color conversion with RGA while leaving RKNN on the NPU.

## Phase 5K: Capture-Only YUYV vs MJPEG Input Benchmark

Before adding MJPEG decode to the inference path, the runtime now measures
camera input throughput without RKNN:

```bash
make run-cpp-capture-yuyv-board
make run-cpp-capture-mjpeg-board
```

These targets run the same C/C++ V4L2 capture loop for 120 frames and do not run
preprocess, RKNN inference, or postprocess. This isolates the USB/camera input
rate from model compute.

Verified RK3576 capture-only result:

```text
YUYV 1280x720, 120 frames:
  measured FPS: 9.980
  bytes processed: 221184000
  bytes per frame: 1843200

MJPEG 1280x720, 120 frames:
  measured FPS: 29.900
  bytes processed: 22786752
  bytes per frame: 189890
```

This confirms that the C920/RK3576 input bottleneck is format-dependent. YUYV is
uncompressed and moves about 1.84 MB per 720p frame, so the camera effectively
delivers around 10 FPS in this mode. MJPEG compresses each frame to roughly
190 KB in the tested scene and reaches the requested 30 FPS capture rate.

The next step is not to send MJPEG directly to the NPU. The RKNN model still
expects an RGB/NHWC 640x640 tensor. The needed runtime path is:

```text
V4L2 MJPEG frame
  -> JPEG decode through GStreamer/libjpeg/hardware plugin
  -> resize/color convert through CPU or RGA
  -> RKNN NPU inference
  -> C++ YOLOv8 postprocess
```

The capture-only benchmark proves that MJPEG is worth integrating because it
fixes the input-rate side of the pipeline. Decode and RGA work will decide how
much of that 30 FPS can be preserved after preprocessing and inference.

## Phase 5L: MJPEG Decode + Latest-Frame RKNN Runtime

The C/C++ runtime now supports real MJPEG camera input in the RKNN path when
built with `JPEG=1`. The board deployment script enables this build mode and
links `libjpeg`:

```bash
make deploy-cpp-runtime-board
make run-cpp-latest-mjpeg-board
make annotate-cpp-latest-mjpeg
```

Runtime path:

```text
USB camera /dev/video73
  -> V4L2 MJPEG compressed frame
  -> latest-frame buffer
  -> CPU libjpeg decode to RGB
  -> CPU resize to 640x640 RGB
  -> RKNN NPU inference
  -> C++ YOLOv8 postprocess
  -> JSON report + annotated PPM
```

Why the runtime resizes to 640x640:

- The deployed YOLOv8n/RKNN model was exported and compiled with a static
  640x640 input tensor. RKNN static-shape models expect the runtime input buffer
  to match that compiled shape.
- YOLOv8 postprocess is also tied to that image size through feature-map grids,
  strides, and DFL box decoding. In this runtime `kYoloImageSize` is 640, so
  decoded boxes are expressed in the model's 640x640 coordinate system.
- The camera can capture 1280x720, but that is the sensor/frame format, not the
  model tensor format. The bridge between them is preprocessing: decode,
  resize/color convert, then feed RKNN.
- The current runtime uses direct resize for the performance baseline. A more
  detection-quality-preserving production path should use letterbox resize:
  preserve the original 16:9 aspect ratio, pad to 640x640, and map detections
  back through the same scale/pad metadata.
- Dynamic shape is possible in principle, but it is a larger deployment change:
  the ONNX/RKNN export must support dynamic shapes, the runtime must select or
  configure the active tensor shape, and YOLOv8 grid/stride/bbox mapping plus
  the benchmark matrix must be validated per shape. For this stage, the 640
  static-shape path is the better optimization target because it keeps RKNN
  deployment and performance measurements stable.

Initial RK3576 MJPEG latest-frame result:

```text
frames processed: 30
measured capture FPS: 30.218
rknn frames: 15
skipped frames: 15
rknn failures: 0
detections total: 36
preprocess mean: 17.425 ms
inference mean: 33.937 ms
postprocess mean: 16.381 ms
RKNN end-to-end mean: 69.199 ms
last-frame detections: chair 0.8516, bottle 0.4588
artifacts:
  runs/rk3576_cpp_runtime/edgeav_runtime_latest_mjpeg_report.json
  runs/rk3576_cpp_runtime/edgeav_runtime_latest_mjpeg_frames.json
  runs/rk3576_cpp_runtime/edgeav_runtime_latest_mjpeg_input.ppm
  runs/rk3576_cpp_runtime/edgeav_runtime_latest_mjpeg_annotated.ppm
```

This is an important behavior change from YUYV. MJPEG lets the camera deliver
around 30 FPS, while the current CPU decode + resize + RKNN + postprocess path
processes around 15 frames during the same 30-frame capture window. In
latest-frame mode this is acceptable for real-time perception: the system drops
stale frames instead of building a long queue and increasing visual latency.
The next optimization target is preprocessing acceleration, especially
replacing CPU resize/color conversion with RGA or moving capture and decode
into a GStreamer pipeline.

## Phase 5M: CPU Preprocess/Postprocess Profiling and Optimization

The first MJPEG runtime proved that camera capture could reach 30 FPS, but the
worker only processed 15 frames out of 30. That did not mean the pipeline was
broken. It meant the real-time input side was faster than the CPU/NPU worker
side, and latest-frame mode correctly skipped stale frames.

To locate the worker bottleneck, the runtime now splits preprocessing into:

```json
"preprocess_detail_ms": {
  "decode_mean": "...",
  "resize_or_convert_mean": "..."
}
```

Profiling before optimization showed:

```text
frames processed: 30
rknn frames: 15
skipped frames: 15
preprocess mean: 17.394 ms
  JPEG decode mean: 15.292 ms
  resize/convert mean: 2.079 ms
inference mean: 33.471 ms
postprocess mean: 16.831 ms
RKNN end-to-end mean: 69.046 ms
```

This showed two CPU hot spots:

- JPEG decode was the main preprocessing cost.
- YOLOv8 postprocess was still expensive because it scanned all 80 class scores
  before applying the single-channel `score_sum` candidate filter.

Optimizations added:

- Postprocess now checks `score_sum` before scanning 80 class channels. Most
  low-confidence grid positions are rejected with one scalar read instead of 80
  class reads.
- MJPEG decode uses libjpeg DCT scaling when the input is large enough. For
  1280x720 camera frames and 640x640 model input, libjpeg decodes at half scale
  before the runtime resizes to the final tensor size.

Verified optimized MJPEG latest-frame result:

```text
frames processed: 30
measured capture FPS: 30.215
rknn frames: 19
skipped frames: 11
rknn failures: 0
detections total: 63
preprocess mean: 14.238 ms
  JPEG decode mean: 9.853 ms
  resize/convert mean: 4.372 ms
inference mean: 36.506 ms
postprocess mean: 1.523 ms
RKNN end-to-end mean: 54.141 ms
last-frame detections: chair 0.8379, banana 0.3235, bottle 0.3137, bottle 0.3000
```

Comparison:

```text
postprocess: 16.831 ms -> 1.523 ms
JPEG decode: 15.292 ms -> 9.853 ms
end-to-end worker latency: 69.046 ms -> 54.141 ms
rknn frames per 30 captured frames: 15 -> 19
skipped frames: 15 -> 11
```

The remaining CPU-heavy part is still JPEG decode/resize. The next production
optimization should move more preprocessing work to a media pipeline or
accelerator, such as GStreamer with hardware decode plugins or Rockchip RGA for
resize/color conversion.

## Phase 5N: Optional Letterbox Preprocessing

The runtime now supports an optional `--letterbox` preprocessing mode. Direct
resize is still the default, so performance baselines remain comparable:

```bash
make run-cpp-latest-mjpeg-board
make run-cpp-latest-mjpeg-letterbox-board
make annotate-cpp-latest-mjpeg
make annotate-cpp-latest-mjpeg-letterbox
```

Direct resize path:

```text
1280x720 camera frame
  -> MJPEG decode
  -> stretch to 640x640
  -> RKNN input
```

Letterbox path:

```text
1280x720 camera frame
  -> MJPEG decode
  -> preserve 16:9 aspect ratio
  -> fit into 640x640 canvas
  -> pad unused area with RGB 114
  -> RKNN input
```

Verified direct resize vs letterbox result on the same RK3576/C920 setup:

```text
direct resize:
  measured capture FPS: 30.212
  rknn frames: 20/30
  skipped frames: 10
  detections total: 61
  preprocess mean: 13.733 ms
    JPEG decode mean: 9.526 ms
    resize/convert mean: 4.195 ms
  inference mean: 35.799 ms
  postprocess mean: 1.353 ms
  RKNN end-to-end mean: 52.497 ms

letterbox:
  measured capture FPS: 30.221
  rknn frames: 20/30
  skipped frames: 10
  detections total: 46
  preprocess mean: 11.870 ms
    JPEG decode mean: 9.303 ms
    resize/convert mean: 2.556 ms
  inference mean: 36.218 ms
  postprocess mean: 1.300 ms
  RKNN end-to-end mean: 50.939 ms
```

Letterbox is mainly a detection-quality correction, not a NPU optimization. It
avoids stretching 16:9 camera frames into a square input. In this run it was
also slightly faster because the DCT-scaled MJPEG frame is about 640x360, so
the runtime writes the valid 16:9 image region and pads the rest instead of
resizing the image content to the full 640x640 square.

## Phase 5O: Original-Frame Bounding Box Mapping

The runtime now records preprocessing geometry and emits both model-input and
original-frame box coordinates. This keeps existing 640x640 debugging intact
while preparing the project for original-frame overlays and spatial rules.

Example letterbox metadata for 1280x720 camera input:

```json
"preprocessing": {
  "image_size": 640,
  "mode": "letterbox",
  "pad_value": 114,
  "content_size": [640, 360],
  "pad_xy": [0.0, 140.0],
  "scale_xy": [0.5, 0.5]
}
```

Example detection output:

```json
{
  "class_id": 56,
  "confidence": 0.7795,
  "bbox_xyxy": [305.51, 378.86, 490.90, 497.31],
  "bbox_original_xyxy": [611.01, 477.73, 981.80, 714.63]
}
```

Coordinate meanings:

- `bbox_xyxy` is the model-input coordinate system after preprocessing. For
  this project that is 640x640.
- `bbox_original_xyxy` is mapped back to the original camera frame. For the
  current C920 test that is 1280x720.
- Direct resize uses separate x/y scales from 640 back to camera width/height.
- Letterbox subtracts pad first, then divides by the content scale, and clips
  the result to the original frame bounds.

The annotation helper now accepts `--bbox-key`, defaulting to `bbox_xyxy`.
Future original-frame overlay can use `--bbox-key bbox_original_xyxy` once the
runtime also dumps or streams the original RGB frame.

## Phase 5P: GStreamer/RGA Availability Probe

V4L2 and GStreamer are related but not equivalent. V4L2 is the Linux kernel
camera/video device API. GStreamer is a user-space media pipeline framework.
When GStreamer captures a USB camera through `v4l2src`, it is still using V4L2
underneath, but GStreamer manages pipeline elements such as decode, colorspace
conversion, scaling, buffering, and appsink handoff.

The project now has a board-side media acceleration probe:

```bash
make probe-media-accel-board
```

Verified RK3576 probe result:

```text
gstreamer-1.0: 1.24.2
gstreamer-app-1.0: 1.24.2
librga: 2.1.0
headers:
  /usr/include/gstreamer-1.0/gst/gst.h
  /usr/include/gstreamer-1.0/gst/app/gstappsink.h
  /usr/include/rga/im2d.h
  /usr/include/rga/RgaApi.h
devices:
  /dev/rga
  /dev/dri/renderD128
  /dev/dri/renderD129
```

The same probe runs a software GStreamer baseline:

```text
v4l2src
  -> image/jpeg 1280x720@30
  -> jpegparse
  -> jpegdec
  -> videoconvert
  -> videoscale
  -> RGB 640x360
  -> fakesink
```

Measured result: 120 frames in 5230 ms, about `22.945 FPS`.

Interpretation:

- GStreamer is ready as a future capture/decode pipeline replacement for the
  hand-written V4L2 + libjpeg path.
- The tested GStreamer pipeline uses software `jpegdec/videoscale`, so it is
  not automatically faster than the current C++ libjpeg path.
- RGA is available and should be the next optional preprocessing backend for
  resize/color conversion, exposed as a fallback-controlled mode such as
  `--preprocess-backend cpu|rga`.
- The safest next engineering step is to add RGA as an optional backend while
  keeping the current CPU path as the reference implementation.

Before running the live C++ camera test again, stop the Python service that owns
the camera device, then restart it after the test:

```bash
sudo systemctl stop spatial-edgeav-rknn.service
make run-cpp-latest-mjpeg-board
sudo systemctl start spatial-edgeav-rknn.service
```

## Phase 5Q: C++ Spatial Event Engine

The spatial layer has moved from Python-only post-processing into the C/C++
runtime hot path. The runtime now accepts:

```bash
--spatial-rules /home/kickpi/spatial-edgeav/configs/spatial_rules.json
--observations-jsonl /home/kickpi/spatial-edgeav/runs/cpp_runtime/observations.jsonl
--events-jsonl /home/kickpi/spatial-edgeav/runs/cpp_runtime/events.jsonl
```

Current C++ spatial support:

- Parses the project `spatial_rules.json` schema without a large JSON
  dependency.
- Supports `zone_intersection` rules from the current config.
- Supports `zone_dwell`/`dwell_zone` style rules with `dwell_ms` and
  `cooldown_ms` fields for future time-based policies.
- Converts YOLO class ids to COCO class names in C++.
- Uses `bbox_original_xyxy`, not the 640x640 model coordinates, for zone
  intersection.
- Maintains a lightweight IoU tracker so observations/events can contain a
  stable `object_id` across nearby frames.

The new board target is:

```bash
make run-cpp-latest-mjpeg-letterbox-spatial-board
```

Latest verified RK3576/C920 result:

```json
{
  "measured_fps": 30.213,
  "rknn_continuous": {
    "mode": "latest_frame_worker",
    "frames": 19,
    "skipped_frames": 11,
    "detections_total": 66
  },
  "spatial": {
    "observations": 19,
    "events": 1,
    "failures": 0
  },
  "latency_ms": {
    "preprocess_mean": 12.635,
    "inference_mean": 36.684,
    "postprocess_mean": 1.439,
    "rknn_end_to_end_mean": 54.216
  }
}
```

Generated spatial artifacts:

```text
runs/rk3576_cpp_runtime/edgeav_runtime_latest_mjpeg_letterbox_observations.jsonl
runs/rk3576_cpp_runtime/edgeav_runtime_latest_mjpeg_letterbox_events.jsonl
```

Example event:

```json
{
  "type": "spatial_rule_triggered",
  "rule_id": "chair_in_left_work_area",
  "relation": "intersects",
  "object": {
    "object_id": 1,
    "class_name": "chair",
    "confidence": 0.4533,
    "bbox_original_xyxy": [130.86, 480.94, 424.29, 715.27]
  }
}
```

The `chair_in_left_work_area` rule threshold is now `0.3` so the current desk
scene reliably triggers a demonstrable MVP event. This is a product/demo
configuration choice, not a model change.

## Phase 5R: Original-Frame Visualization

The runtime can now dump the first original-size RGB frame:

```bash
--original-frame-dump /home/kickpi/spatial-edgeav/runs/cpp_runtime/original.ppm
```

For the C920 MJPEG path this decodes the first 1280x720 JPEG frame into RGB PPM
without letterbox padding. The normal RKNN input dump is still 640x640 and is
used for model-input debugging.

The original-frame annotation target is:

```bash
make annotate-cpp-latest-mjpeg-letterbox-original
```

It draws detections using:

```bash
--bbox-key bbox_original_xyxy
```

Verified artifacts:

```text
runs/rk3576_cpp_runtime/edgeav_runtime_latest_mjpeg_letterbox_original.ppm
runs/rk3576_cpp_runtime/edgeav_runtime_latest_mjpeg_letterbox_original_annotated.ppm
```

Why this matters:

- Spatial rules and visualization now use the same original camera coordinate
  system.
- Letterbox padding no longer makes overlays look shifted or stretched.
- The runtime has a complete evidence chain: camera frame, detections,
  observations, events, report, and heartbeat.

## Phase 5S: C++ Service Unit

The project now includes a separate C++ service unit:

```text
systemd/spatial-edgeav-cpp.service
configs/spatial-edgeav-cpp.env
scripts/deploy_cpp_runtime_service_to_rk3576.sh
```

Install target:

```bash
make deploy-cpp-runtime-service-board
```

The unit runs the C++ MJPEG + letterbox + latest-frame + RKNN + spatial path
with `--frames 0`, which now means continuous capture. To keep JSON memory and
disk usage bounded, the runtime also supports:

```bash
--max-frame-records 300
```

The service was staged, but installing it into `/etc/systemd/system` requires
the board's interactive `sudo` password. The script uses `ssh -tt`; run the
target from a terminal where the password prompt can be answered. The C++
service is intentionally separate from the existing Python
`spatial-edgeav-rknn.service` so the two services do not silently fight over
`/dev/video73`.

## Phase 5T: Long-Run Service Test and Graceful Stop

The C++ service passed a long-run board test driven by a one-shot systemd
timer:

```bash
sudo systemd-run --on-active=3h --unit=stop-spatial-edgeav-cpp /bin/systemctl stop spatial-edgeav-cpp.service
```

The timer stopped the service successfully. Verified service result:

```text
Active: inactive (dead)
Duration: 3h 5min 36.965s
Main PID: code=killed, signal=TERM
```

Last heartbeat from that run:

```json
{
  "frames_processed": 331960,
  "measured_fps": 29.809,
  "rknn_continuous": {
    "frames": 189982,
    "failures": 0,
    "detections_total": 20794
  },
  "spatial": {
    "observations": 189982,
    "events": 963,
    "failures": 0
  },
  "latency_ms": {
    "preprocess_mean": 19.341,
    "inference_mean": 35.963,
    "postprocess_mean": 1.200,
    "rknn_end_to_end_mean": 57.732
  }
}
```

This is the strongest validation so far: camera capture stayed close to 30 FPS,
RKNN failures stayed at zero, spatial failures stayed at zero, and the service
ran for multiple hours under systemd.

The test also exposed an operational polish issue: because systemd stopped the
runtime with SIGTERM, the previous binary could terminate before writing a final
`stopped` heartbeat/report. The runtime now installs SIGTERM/SIGINT handlers
and asks the V4L2 capture loop to exit cleanly. `--frames 0` continuous mode
therefore supports graceful shutdown.

Short verification after the fix:

```text
timeout -s TERM 20s ./build/edgeav_runtime --frames 0 ...
edgeav_runtime status=stopped frames=573 fps=29.935
```

Verified final JSON:

```json
{
  "status": "stopped",
  "frames_processed": 573,
  "measured_fps": 29.935,
  "elapsed_ms": 20249.753,
  "rknn_continuous": {
    "frames": 331,
    "failures": 0,
    "skipped_frames": 242
  },
  "spatial": {
    "observations": 331,
    "events": 20,
    "failures": 0
  }
}
```

`elapsed_ms` now also updates correctly in live heartbeat files: while the
process is running it uses the current monotonic time, and after shutdown it
uses the final end timestamp.
