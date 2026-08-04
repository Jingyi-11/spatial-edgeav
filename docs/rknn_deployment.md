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
bash scripts/collect_rknn_calibration_frames.sh
scp -r runs/model_exports/yolov8n/calib winbox:C:/Users/HP/edgeav_data/exports/yolov8n/
bash scripts/wsl_convert_yolov8_rknn.sh \
  /mnt/c/Users/HP/edgeav_data/exports/yolov8n/yolov8n.onnx \
  i8 \
  rk3576
```

Expected outputs:

```text
runs/model_exports/yolov8n/yolov8n_rk3576_fp.rknn
runs/model_exports/yolov8n/yolov8n_rk3576_fp.report.json
runs/model_exports/yolov8n/yolov8n_rk3576_i8.rknn
runs/model_exports/yolov8n/yolov8n_rk3576_i8.report.json
```

## Board Runtime Work

After RKNN files exist, the next step is board-side inference:

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
