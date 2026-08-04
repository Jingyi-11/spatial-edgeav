# Spatial EdgeAV

Spatial EdgeAV is an embedded Linux audio-video AI project for RK3576/RK3567
edge devices. It connects real camera capture, remote model validation,
V4L2/GStreamer debugging, and a path toward RKNN quantization and deployment.

The repository now contains two complementary layers:

- A verified distributed baseline that already runs across MacBook, RK3576,
  Windows, and WSL.
- A C/V4L2 camera pipeline skeleton for the future RK3576/RKNN edge runtime.

## Verified Pipeline

This pipeline has been run successfully on the current setup:

```text
Logitech C920 USB camera
  -> RK3576 Ubuntu 24.04 ARM board
  -> GStreamer/V4L2 JPEG capture
  -> sample frame copied to Windows over SSH/SCP
  -> WSL2 Ubuntu model environment
  -> YOLOv8n CPU inference
  -> annotated result copied back to MacBook
```

Smoke-test result:

```text
Input: RK3576 C920 1280x720 JPEG frame
Model: YOLOv8n
Runtime: WSL2 Ubuntu, torch 2.13.0+cpu, ultralytics 8.4.106
Observed detections: 1 person, 1 cup, 1 tv
CPU inference time: about 26-31 ms on the validation image
```

Detailed walkthrough: [docs/current_pipeline.md](docs/current_pipeline.md).

## Why This Project

This project targets embedded camera, robotics, and edge-AI software roles. It
is designed to demonstrate practical skills instead of a notebook-only demo:

- Linux device development with SSH, shell scripts, system tools, and logs.
- V4L2/media-controller camera debugging on ARM Linux.
- GStreamer/FFmpeg video capture, preview, recording, and streaming.
- C camera pipeline structure with MMAP capture and raw frame handling.
- Windows/WSL model validation workflow for training, ONNX export, and RKNN
  conversion.
- RK3576/RK3567 deployment path with RGA, MPP, RKNN, and systemd service work.
- Spatial perception rules that connect detections to device actions.

## Hardware Topology

```text
MacBook M1
  -> project control, scripts, docs, GitHub, SSH/Tailscale

Windows PC + WSL2 Ubuntu
  -> model validation, training, ONNX export, RKNN conversion path

RK3576 board + USB camera
  -> embedded Linux capture and future RKNN runtime deployment
```

Configured SSH hosts:

```bash
ssh rk3576
ssh winbox
ssh wslbox
```

## Quick Start: Verified Baseline

Run a Mac camera smoke test:

```bash
bash scripts/mac_ffmpeg_smoke_test.sh 0
```

Run the Mac OpenCV motion/spatial-rule prototype:

```bash
python3 -m pip install -r requirements-mac.txt
python3 scripts/mac_camera_baseline.py --config configs/mac_baseline.yaml
```

Run RK3576 USB camera smoke test:

```bash
bash scripts/rk3576_camera_smoke_test.sh
```

Tune the Logitech C920 for indoor lighting:

```bash
bash scripts/rk3576_camera_tune.sh rk3576 /dev/video73 indoor
```

Run RK3576 continuous capture:

```bash
bash scripts/rk3576_stream_baseline.sh rk3576 /dev/video73 15 1280 720 30
```

Send an RK3576 sample frame to Windows:

```bash
bash scripts/send_sample_to_windows.sh
```

Run YOLO inference inside WSL and copy the result back to Mac:

```bash
bash scripts/wsl_yolo_smoke_test.sh
```

Run the full one-command remote pipeline:

```bash
make edgeav-smoke
```

This captures a fresh RK3576 camera frame, copies it to WSL, runs YOLOv8n,
copies the annotated image and JSON outputs back to Mac, evaluates spatial
rules, and records per-step latency under `runs/edgeav_remote_yolo/<timestamp>/`.

The script prefers direct `ssh wslbox`. If WSL port `2222` is unstable after
Windows wakes up, it can fall back to `ssh winbox` plus `wsl.exe` while keeping
the same output format.

Generated runtime artifacts are written under `runs/` and are intentionally not
tracked by Git.

## Quick Start: C/V4L2 Pipeline

Build on MacBook or Linux:

```bash
make clean
make
make rk3567-sim
```

Expected outputs:

```text
build/embedded_camera
out/rk3567_simulated_yuyv.yuv
out/rk3567_preview.ppm
```

On non-Linux hosts, the program uses simulated frames because V4L2 is not
available. Real camera capture should run on Linux or the RK board.

Probe a V4L2 device:

```bash
./build/embedded_camera probe --device /dev/videoX
```

Capture NV12:

```bash
./build/embedded_camera capture \
  --device /dev/videoX \
  --width 1280 \
  --height 720 \
  --fps 30 \
  --frames 90 \
  --format NV12 \
  --output out/rk3567_capture_nv12.yuv
```

## RK3567/RK3576 Media Scripts

Prepare tools on the board:

```bash
./scripts/00_rk3567_install_tools.sh
```

Probe camera/media nodes:

```bash
./scripts/01_rk3567_probe_media.sh /dev/video0
```

Capture raw NV12:

```bash
./scripts/02_rk3567_capture_nv12.sh /dev/videoX
```

Preview with GStreamer:

```bash
./scripts/07_rk3567_gst_preview_nv12.sh /dev/videoX
```

Publish H.264 RTSP with Rockchip/GStreamer encoder fallback:

```bash
RTSP_URL=rtsp://127.0.0.1:8554/live ./scripts/08_rk3567_gst_rtsp_mpp.sh /dev/videoX
```

Record audio and video:

```bash
./scripts/09_rk3567_ffmpeg_record_nv12.sh /dev/videoX
```

## RK3576 Model Deployment

Install the RKNN conversion environment in WSL:

```bash
make setup-rknn-wsl
```

Export official YOLOv8n to ONNX on WSL:

```bash
make export-onnx
```

Convert ONNX to RKNN FP model for RK3576:

```bash
make convert-rknn-fp
```

Install the RK3576 board runtime once. This opens an interactive SSH session
because `apt` needs the board user's sudo password:

```bash
make setup-rknn-board
```

Deploy the RKNN model to the RK3576 board and collect a board-side diagnostic
or NPU benchmark report:

```bash
make deploy-rknn-board
```

Verified RK3576 FP baseline:

```text
Model: yolov8n_rk3576_fp.rknn
Runtime: RKNN Toolkit Lite2 2.3.2, librknnrt 2.3.2, driver 0.9.7
Input: RK3576 camera sample image, resized to 640x640 RGB
Output tensor: [1, 84, 8400]
Latency: mean 125.322 ms, median 127.799 ms, p95 147.408 ms over 30 runs
FPS: 7.979
```

Verified outputs are generated locally under `runs/model_exports/yolov8n/`:

```text
yolov8n.onnx
onnx_export_report.json
yolov8n_rk3576_fp.rknn
yolov8n_rk3576_fp.report.json
```

See [docs/rknn_deployment.md](docs/rknn_deployment.md) for the Phase 3
deployment and quantization plan.

## Repository Layout

```text
configs/
  camera.conf                    # C/V4L2 default camera config
  mac_baseline.yaml              # Mac OpenCV baseline config
  spatial_rules.json             # zones and spatial rule config
docs/
  current_pipeline.md            # verified end-to-end pipeline
  macbook_remote_setup.md        # SSH/Tailscale remote development setup
  mvp_plan.md                    # roadmap from baseline to industrial MVP
  pipeline_walkthrough.md        # RK3567/RK3576 camera pipeline notes
  rknn_deployment.md             # ONNX/RKNN conversion and benchmark plan
  windows_wsl_model_setup.md     # WSL model validation workflow
include/
  camera_capture.h
  pipeline.h
  yuv.h
scripts/
  evaluate_spatial_rules.py
  mac_camera_baseline.py
  rk3576_setup_rknn_runtime.sh
  rk3576_camera_smoke_test.sh
  rk3576_camera_tune.sh
  rk3576_stream_baseline.sh
  run_remote_yolo_pipeline.sh
  deploy_rknn_to_rk3576.sh
  rk3576_rknn_smoke_test.py
  wsl_setup_rknn_toolkit2.sh
  wsl_export_yolov8_onnx.sh
  wsl_convert_yolov8_rknn.sh
  convert_yolov8_onnx_to_rknn.py
  collect_rknn_calibration_frames.sh
  wsl_yolo_smoke_test.sh
  wsl_yolo_infer.py
  0*_rk3567_*.sh                 # board-side RK3567/RK3576 helpers
src/
  camera_capture.c
  main.c
  pipeline.c
  yuv.c
```

## Roadmap

1. Add continuous frame extraction and batched inference from RK3576 video.
2. Define a unified observation schema shared by motion, YOLO, and RKNN outputs.
3. Add spatial rules: restricted-zone entry, dwell time, line crossing.
4. Train a small custom person detector on WSL and export ONNX.
5. Convert ONNX to RKNN with calibration images and document quantization impact.
6. Implement RK3576 C/C++ runtime with V4L2/GStreamer capture, RKNN inference,
   postprocessing, JSONL logs, and systemd service deployment.
7. Add audio capture and audio-video event fusion.
8. Add VLA-style instruction-to-spatial-rule mapping for higher-level control.

## Documentation

- [Current Pipeline](docs/current_pipeline.md)
- [MVP Plan](docs/mvp_plan.md)
- [Pipeline Walkthrough](docs/pipeline_walkthrough.md)
- [MacBook Remote Setup](docs/macbook_remote_setup.md)
- [Windows / WSL Model Setup](docs/windows_wsl_model_setup.md)
