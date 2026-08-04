# Benchmark Matrix

This file is generated from local JSON reports by:

```bash
make benchmark-matrix
```

Generated at: `2026-08-04T18:04:07+00:00`

## Summary

| Path | Status | Device | Precision | Workload | Mean latency | FPS | Detections | Quality |
|---|---|---|---|---|---:|---:|---:|---|
| RK3576 NPU single image FP | measured | RK3576 RKNPU | FP | single image, 30 timed runs | 125.658 ms | 7.958 | 3 | accepted baseline |
| RK3576 NPU single image INT8 raw head | measured | RK3576 RKNPU | INT8 | single image, 30 timed runs | 62.75 ms | 15.936 | 0 | rejected |
| RK3576 NPU single image INT8 optimized head | measured | RK3576 RKNPU | INT8 | single image, 30 timed runs | 62.265 ms | 16.06 | 2 | accepted deployable baseline |
| RK3576 CPU single image ONNX | measured | RK3576 ARM CPU | FP32 CPU | single image, 30 timed runs | 379.994 ms | 2.632 | 4 | CPU fallback baseline |
| RK3576 NPU continuous camera INT8 | measured | RK3576 C920 + RKNPU | INT8 | 60 camera frames | 66.37 ms | 15.067 | 115 | accepted runtime baseline |
| WSL CPU YOLO core inference | measured | Windows WSL2 x86 CPU | FP32 CPU | single image from 20260804T000722Z | 71.515 ms | 13.983 | 2 | validation baseline |
| Mac -> RK3576 -> WSL remote pipeline | measured | Distributed Mac/RK3576/Windows | FP32 CPU | single end-to-end smoke run from 20260804T000722Z | 16196 ms | 0.062 | 2 | connectivity baseline |
| MacBook M1 CPU/ANE reference | pending | MacBook M1 | FP32/FP16 depending backend | single image validation | - | - | - | pending |

## Notes

- **RK3576 NPU single image FP**: Reference RKNN path; slower but class scores and detections are valid.
- **RK3576 NPU single image INT8 raw head**: Fast, but class-score channels quantize to zero, so detection quality fails.
- **RK3576 NPU single image INT8 optimized head**: Uses 9-output box/class/score-sum head; preserves meaningful detections.
- **RK3576 CPU single image ONNX**: Board-local CPU fallback for comparing NPU acceleration against plain ARM CPU.
- **RK3576 NPU continuous camera INT8**: Includes capture, preprocess, NPU inference, candidate-filtered DFL/NMS, JSON frame output.
  Breakdown: capture=18.209 ms, preprocess=4.303 ms, inference=40.214 ms, postprocess=3.641 ms, end_to_end=66.37 ms.
- **WSL CPU YOLO core inference**: Pure Ultralytics inference time; excludes SSH/SCP orchestration.
  Breakdown: preprocess=1.453 ms, inference=71.515 ms, postprocess=9.255 ms.
- **Mac -> RK3576 -> WSL remote pipeline**: Measures orchestration overhead, not only model compute.
  Breakdown: capture_rk3576_ms=1556 ms, pull_frame_to_mac_ms=575 ms, prepare_wsl_bridge_ms=7657 ms, prepare_model_workspace_ms=1125 ms, infer_wsl_ms=3518 ms, pull_results_to_mac_ms=1532 ms, evaluate_spatial_rules_ms=82 ms.
- **MacBook M1 CPU/ANE reference**: Optional host-side reference; not required for RK3576 deployment.

## Interpretation

- The RK3576 NPU INT8 optimized-head path is the current deployable edge baseline.
- The raw Ultralytics INT8 RKNN is kept as a documented failed optimization because its class-score branch collapses to zero.
- The WSL CPU number is useful for model validation, while the remote pipeline number measures SSH/SCP orchestration overhead.
- On the RK3576 board, optimized INT8 RKNN NPU inference is 6.103x faster than ONNX Runtime CPU on the same single-image benchmark.
- Phase 3 now includes a board-local CPU fallback measurement; optional remaining coverage is MacBook M1 host reference and longer CPU/memory profiling.
