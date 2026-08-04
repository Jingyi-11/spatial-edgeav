# RK3576 RKNN Deployment Plan

This document tracks Phase 3 of Spatial EdgeAV: deploy and optimize YOLOv8n on
the RK3576 edge device.

## Source References

- [RKNN-Toolkit2](https://github.com/airockchip/rknn-toolkit2): Rockchip's
  PC-side conversion and simulation toolkit. The official README describes
  conversion from trained models to RKNN, board inference through RKNN Runtime
  or RKNN Toolkit Lite2, RK3576 support, and the `v2.3.2` release.
- [RKNN Model Zoo](https://github.com/airockchip/rknn_model_zoo): Rockchip's
  official deployment examples for model export, RKNN conversion, Python
  inference, and C API inference. Its support matrix includes RK3576.

## Phase 3A: Deploy Official YOLOv8n

Goal:

```text
yolov8n.pt
  -> yolov8n.onnx
  -> yolov8n_rk3576_fp.rknn
  -> yolov8n_rk3576_i8.rknn
  -> RK3576 NPU smoke test
  -> latency/FPS report
```

Why start with official YOLOv8n:

- No dataset labeling is needed to validate the deployment chain.
- YOLOv8n is small enough for edge deployment experiments.
- It gives a stable baseline before custom person-detector fine-tuning.

## Export ONNX on WSL

From Mac:

```bash
bash scripts/wsl_export_yolov8_onnx.sh
```

Expected outputs:

```text
runs/model_exports/yolov8n/yolov8n.onnx
runs/model_exports/yolov8n/onnx_export_report.json
```

WSL-visible output:

```text
/mnt/c/Users/HP/edgeav_data/exports/yolov8n/yolov8n.onnx
```

Verified output on the current workstation:

```json
{
  "size_bytes": 12824062,
  "opset": [12],
  "inputs": ["images"],
  "outputs": ["output0"]
}
```

## Install RKNN-Toolkit2 in WSL

From Mac:

```bash
make setup-rknn-wsl
```

The setup pins `onnx==1.16.1` because RKNN-Toolkit2 `2.3.2` expects the
legacy `onnx.mapping` API. The script installs `rknn-toolkit2` with
`--no-deps` to avoid replacing the CPU WSL environment with large CUDA PyTorch
packages. For a production workspace, keep RKNN conversion in a dedicated WSL
virtual environment.

## Convert ONNX to RKNN

FP model:

```bash
make convert-rknn-fp
```

Verified FP output on the current workstation:

```json
{
  "target": "rk3576",
  "quant": "fp",
  "elapsed_ms": 2436.578
}
```

INT8 model after collecting calibration frames:

```bash
make collect-rknn-calib-board
make convert-rknn-i8
```

`make collect-rknn-calib-board` captures 100 JPEG frames from the RK3576 C920
camera and writes:

```text
runs/model_exports/yolov8n/calib/images/
runs/model_exports/yolov8n/calib/dataset.txt
```

If Windows/WSL SSH is unavailable, run the ARM64 conversion fallback directly
on the RK3576 board:

```bash
make setup-rknn-converter-board
make convert-rknn-i8-board
```

The fallback uses `rknn-toolkit2==2.3.2`, `torch==2.2.0`,
`onnx==1.16.1`, `numpy<=1.26.4`, and `scipy==1.12.0` on the RK3576 board.

Expected outputs:

```text
runs/model_exports/yolov8n/yolov8n_rk3576_fp.rknn
runs/model_exports/yolov8n/yolov8n_rk3576_fp.report.json
runs/model_exports/yolov8n/yolov8n_rk3576_i8.rknn
runs/model_exports/yolov8n/yolov8n_rk3576_i8.report.json
```

## Board Runtime Work

After RKNN files exist, install the board runtime once:

```bash
make setup-rknn-board
```

This command copies `scripts/rk3576_setup_rknn_runtime.sh` to the board and
runs it in an interactive SSH session. It installs:

```text
python3-pip
python3-numpy
python3-opencv
v4l-utils
rknn-toolkit-lite2==2.3.2
```

Then deploy the model and run the board diagnostic:

```bash
make deploy-rknn-board
make deploy-rknn-board-i8
```

The command copies the RKNN model, a sample frame when available, and the
board-side smoke-test helper to:

```text
/home/kickpi/spatial-edgeav/models/yolov8n/
/home/kickpi/spatial-edgeav/bin/
/home/kickpi/spatial-edgeav/runs/rknn_smoke/
```

The board report is copied back to:

```text
runs/rk3576_board/*_rk3576_report.json
runs/rk3576_board/*_detections.json
runs/rk3576_board/*_annotated.jpg
```

The smoke-test helper is diagnostic-first. If RKNN Lite or image dependencies
are missing, it still records model size, board platform, available device
nodes, and missing Python modules. Once RKNN Lite is installed on the board,
the same command becomes a single-image NPU benchmark.

Verified board-side FP baseline:

```json
{
  "status": "ok",
  "runtime": "rknn-toolkit-lite2 2.3.2",
  "librknnrt": "2.3.2",
  "driver": "0.9.7",
  "model_size_bytes": 13396342,
  "input_source": "image_rgb_resized",
  "runs": 30,
  "warmup": 3,
  "latency_ms": {
    "mean": 125.658,
    "median": 124.429,
    "p95": 145.584,
    "min": 102.124,
    "max": 148.637
  },
  "fps": 7.958,
  "output_shapes": [[1, 84, 8400]],
  "output_summary": {
    "box_nonzero": 33600,
    "class_score_max": 0.406006,
    "class_score_nonzero": 672000
  },
  "detections": {
    "count": 3,
    "classes": ["person", "surfboard", "bottle"]
  }
}
```

Verified board-side INT8 baseline:

```json
{
  "status": "ok",
  "calibration_images": 100,
  "conversion_elapsed_ms": 173422.891,
  "model_size_bytes": 10259536,
  "runs": 30,
  "latency_ms": {
    "mean": 62.75,
    "median": 62.708,
    "p95": 67.312,
    "min": 53.334,
    "max": 69.188
  },
  "fps": 15.936,
  "output_shapes": [[1, 84, 8400]],
  "output_summary": {
    "box_nonzero": 33600,
    "class_score_max": 0.0,
    "class_score_nonzero": 0
  },
  "detections": {
    "count": 0
  }
}
```

FP vs INT8 comparison:

```json
{
  "fp": {
    "model_size_bytes": 13396278,
    "latency_mean_ms": 125.658,
    "fps": 7.958
  },
  "i8": {
    "model_size_bytes": 10259536,
    "latency_mean_ms": 62.75,
    "fps": 15.936
  },
  "improvement": {
    "latency_speedup": 2.003,
    "latency_reduction_pct": 50.06,
    "fps_gain_pct": 100.25,
    "model_size_reduction_pct": 23.42
  }
}
```

FP vs INT8 detection comparison:

```json
{
  "fp": {
    "count": 3,
    "by_class": {
      "person": 1,
      "surfboard": 1,
      "bottle": 1
    }
  },
  "i8": {
    "count": 0,
    "by_class": {}
  },
  "status": "mismatch"
}
```

The current INT8 model is therefore a performance-positive but
quality-failing optimization candidate. A direct output inspection showed that
the INT8 model keeps nonzero box coordinates, but its 80 class-score channels
are all zero after runtime output conversion. The next quantization task is to
fix RKNN output dtype/quantization settings and rerun the FP vs INT8 detection
comparison.

## Phase 3C: Rockchip Optimized YOLOv8 INT8

The accepted INT8 path uses the Rockchip model-zoo YOLOv8 ONNX export rather
than the raw Ultralytics one-output export. Rockchip's YOLOv8 example explains
that its ONNX graph is optimized for RKNN deployment and splits the detection
head into three branches per feature scale:

```text
box distribution: [1, 64, H, W]
class scores:     [1, 80, H, W]
score sum:        [1, 1, H, W]
```

For YOLOv8n this produces 9 RKNN outputs across 80x80, 40x40, and 20x20
feature maps. The board smoke-test helper now detects these output groups by
shape, runs NumPy DFL decoding for the 64-channel box distribution, applies
class-wise NMS, and writes the same `detections.json` and `annotated.jpg`
artifacts as the raw-head path.

Reproducible commands:

```bash
make download-rockchip-yolov8n
make convert-rockchip-yolov8n-i8-board
make deploy-rockchip-yolov8n-i8-board
make compare-rockchip-i8-detections
```

Verified RK3576 Rockchip optimized INT8 result:

```json
{
  "status": "ok",
  "model_size_bytes": 6461835,
  "runs": 30,
  "latency_ms": {
    "mean": 62.265,
    "median": 67.365,
    "p95": 77.038,
    "min": 46.35,
    "max": 81.474
  },
  "fps": 16.06,
  "output_shapes": [
    [1, 64, 80, 80],
    [1, 80, 80, 80],
    [1, 1, 80, 80],
    [1, 64, 40, 40],
    [1, 80, 40, 40],
    [1, 1, 40, 40],
    [1, 64, 20, 20],
    [1, 80, 20, 20],
    [1, 1, 20, 20]
  ],
  "class_score_max": 0.415511,
  "detections": {
    "count": 2
  }
}
```

Detection comparison against the FP raw-head reference on the same camera
frame:

```json
{
  "fp": {
    "count": 3,
    "by_class": {
      "person": 1,
      "surfboard": 1,
      "bottle": 1
    }
  },
  "i8": {
    "count": 2,
    "by_class": {
      "person": 1,
      "bottle": 1
    }
  },
  "status": "mismatch"
}
```

This is the first deployable INT8 baseline: it keeps the 2x latency win of
INT8, reduces the model from 13.4 MB FP to 6.46 MB, and preserves meaningful
class scores and bounding boxes. It still needs calibration-set and threshold
tuning because the FP reference's lower-confidence `surfboard` detection is
not recovered at the current `0.25` threshold.

## Phase 3D: Continuous Camera RKNN Inference

The single-image smoke test is now extended into a continuous RK3576 USB-camera
loop. The board-side runner opens the C920 with OpenCV/V4L2, captures MJPEG
frames from `/dev/video73`, resizes each frame to the YOLO input size, runs
RKNN inference, decodes detections, and writes:

```text
runs/rk3576_camera_rknn/yolov8n_rockchip_rk3576_i8_camera_report.json
runs/rk3576_camera_rknn/yolov8n_rockchip_rk3576_i8_camera_frames.json
runs/rk3576_camera_rknn/yolov8n_rockchip_rk3576_i8_camera_last.jpg
```

Reproducible command:

```bash
make run-rknn-camera-board
```

Verified 60-frame RK3576 camera run:

```json
{
  "status": "ok",
  "camera": {
    "device": "/dev/video73",
    "width": 1280,
    "height": 720,
    "fps": 30
  },
  "frames_requested": 60,
  "frames_processed": 60,
  "latency_ms": {
    "capture_mean": 15.54,
    "preprocess_mean": 3.535,
    "inference_mean": 39.685,
    "postprocess_mean": 33.843,
    "end_to_end_mean": 92.605
  },
  "fps": {
    "inference_only": 25.199,
    "end_to_end": 10.798
  },
  "detections_by_class": {
    "chair": 60,
    "surfboard": 55,
    "bottle": 15,
    "umbrella": 3
  }
}
```

The important finding is that RKNN inference is no longer the only bottleneck.
The current Python YOLO postprocess averages `33.843 ms`, close to the NPU
inference cost of `39.685 ms`. The next optimization target is therefore
postprocess reduction:

```text
use score-sum tensor for early candidate filtering
vectorize class filtering before DFL
move DFL/NMS into C++ or optimized NumPy
switch resize/preprocess to RGA or zero-copy buffers
```

## Phase 3E: Candidate-Filtered YOLO Postprocess

The first postprocess optimization keeps the Rockchip 9-output YOLOv8 format
but avoids running DFL on every feature-map position. The decoder now:

```text
flatten class-score tensors
  -> keep positions whose max class score passes the confidence threshold
  -> also require score-sum to pass the same threshold when available
  -> run DFL only for those selected positions
  -> run class-wise NMS on the much smaller candidate set
```

This keeps the decode logic in Python for now, but changes the asymptotic cost
of the expensive DFL step from all `80x80 + 40x40 + 20x20 = 8400` positions to
only the positions that can actually survive thresholding.

Verified 60-frame RK3576 camera run after candidate filtering:

```json
{
  "status": "ok",
  "postprocess": {
    "type": "rockchip_yolov8_optimized_head",
    "candidate_filter": "class_score_and_score_sum",
    "confidence_threshold": 0.25
  },
  "latency_ms": {
    "capture_mean": 19.204,
    "preprocess_mean": 5.07,
    "inference_mean": 41.586,
    "postprocess_mean": 4.153,
    "end_to_end_mean": 70.016
  },
  "fps": {
    "inference_only": 24.046,
    "end_to_end": 14.282
  },
  "detections_by_class": {
    "chair": 162,
    "surfboard": 64,
    "bottle": 97
  }
}
```

Measured improvement against the previous Python full-map DFL baseline:

```text
postprocess latency: 33.843 ms -> 4.153 ms
postprocess reduction: 87.7%
end-to-end latency: 92.605 ms -> 70.016 ms
end-to-end FPS: 10.798 -> 14.282
```

The next step is to reduce duplicate boxes and move the remaining hot path into
C++: candidate filtering, selected DFL, NMS, and JSON event emission should be
implemented inside the RKNN runtime service rather than in Python.

## Phase 3F: Same-Class Containment NMS

Candidate filtering reduced postprocess latency, but the continuous camera
output still contained nested boxes around the same large object. Plain NMS
only suppresses boxes when IoU is high; a small box inside a large box can have
low IoU even when it is clearly a duplicate. The postprocess now suppresses a
same-class box when either:

```text
IoU >= 0.45
or
intersection / smaller_box_area >= 0.85
```

Verified 60-frame RK3576 camera run after containment NMS:

```json
{
  "status": "ok",
  "postprocess": {
    "candidate_filter": "class_score_and_score_sum",
    "iou_threshold": 0.45,
    "containment_threshold": 0.85
  },
  "latency_ms": {
    "capture_mean": 17.565,
    "preprocess_mean": 4.141,
    "inference_mean": 40.341,
    "postprocess_mean": 3.446,
    "end_to_end_mean": 65.496
  },
  "fps": {
    "inference_only": 24.789,
    "end_to_end": 15.268
  },
  "detections_by_class": {
    "chair": 79,
    "bottle": 14,
    "surfboard": 36,
    "umbrella": 8
  }
}
```

Measured improvement from the original full-map DFL baseline:

```text
postprocess latency: 33.843 ms -> 3.446 ms
postprocess reduction: 89.8%
end-to-end latency: 92.605 ms -> 65.496 ms
end-to-end FPS: 10.798 -> 15.268
```

This is still a Python baseline, but it now has a realistic postprocess shape
for the C++ service: threshold candidates early, decode only selected boxes,
then suppress both high-IoU duplicates and contained same-class boxes.

The dynamic range warning printed by RKNN Runtime is expected for this static
shape export:

```text
query RKNN_QUERY_INPUT_DYNAMIC_RANGE error, rknn model is static shape type
```

It does not block inference.

Target runtime path:

```text
RK3576 camera frame
  -> resize/letterbox
  -> RKNN Runtime inference
  -> YOLO postprocess
  -> observation.json-compatible objects
  -> spatial event rules
```

Initial benchmark metrics:

```text
model type: FP / INT8
model size
single-image inference latency
camera capture latency
end-to-end latency
FPS over 30-300 frames
CPU and memory usage
```

## Current Board Finding

The board is reachable over SSH as `rk3576`, runs Ubuntu 24.04 on aarch64, and
has the Logitech C920 exposed as `/dev/video73`. The current user belongs to
the `video` and `render` groups. Python-side runtime packages are installed and
the FP RKNN model runs successfully:

```text
rknn-toolkit-lite2: 2.3.2
rknn-toolkit2: 2.3.2
librknnrt: 2.3.2
rknn driver: 0.9.7
numpy: 1.26.4
cv2: 4.6.0
torch: 2.2.0
onnx: 1.16.1
```

Next optimization step: fix INT8 output quality by adjusting RKNN conversion
settings, then move from single-image benchmarking to continuous camera
inference.
