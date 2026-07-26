# Spatial EdgeAV

Spatial EdgeAV is an embedded Linux audio-video AI project for RK3576-class
edge devices. It demonstrates a practical pipeline from camera capture to
remote model validation, with a clear path toward RKNN deployment,
quantization, spatial rules, and real device serviceization.

The current baseline is intentionally small and reproducible: it proves the
end-to-end system wiring before adding heavier training and RKNN runtime code.

## Why This Project

This project is designed around embedded software job requirements in
camera/robotics/edge-AI teams:

- Linux device development with SSH, shell scripts, system tools, and logs.
- V4L2/GStreamer camera capture on ARM Linux.
- Video stream debugging, camera tuning, and reproducible smoke tests.
- Windows/WSL model validation workflow for training, export, and conversion.
- Edge AI deployment path from YOLO/ONNX to RKNN.
- Spatial perception rules that connect detections to device actions.

## Current Pipeline

Verified on the current hardware setup:

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

See [docs/current_pipeline.md](docs/current_pipeline.md) for the full
step-by-step pipeline.

## Hardware Topology

```text
MacBook M1
  -> project control, scripts, docs, GitHub
  -> SSH/Tailscale access

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

## Quick Start

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

Generated runtime artifacts are written under `runs/` and are intentionally not
tracked by Git.

## Repository Layout

```text
configs/
  mac_baseline.yaml              # Mac OpenCV baseline config
docs/
  current_pipeline.md            # verified end-to-end pipeline
  macbook_remote_setup.md        # SSH/Tailscale remote development setup
  mvp_plan.md                    # roadmap from baseline to industrial MVP
  windows_wsl_model_setup.md     # WSL model validation workflow
scripts/
  mac_camera_baseline.py         # OpenCV motion + spatial-rule prototype
  mac_ffmpeg_smoke_test.sh       # Mac camera capture smoke test
  rk3576_camera_smoke_test.sh    # RK3576 single-frame capture
  rk3576_camera_tune.sh          # V4L2 camera control profiles
  rk3576_stream_baseline.sh      # RK3576 continuous GStreamer capture
  send_sample_to_windows.sh      # SCP sample frame to Windows
  setup_wsl_ssh.sh               # WSL OpenSSH setup helper
  wsl_yolo_smoke_test.sh         # WSL YOLO smoke-test pipeline
```

## Roadmap

1. Add continuous frame extraction and batched inference from RK3576 video.
2. Define a unified observation schema shared by motion, YOLO, and RKNN outputs.
3. Add spatial rules: restricted-zone entry, dwell time, line crossing.
4. Train a small custom person detector on WSL and export ONNX.
5. Convert ONNX to RKNN with calibration images and document quantization impact.
6. Implement RK3576 C++ runtime with V4L2/GStreamer capture, RKNN inference,
   postprocessing, JSONL logs, and systemd service deployment.
7. Add audio capture and audio-video event fusion.
8. Add VLA-style instruction-to-spatial-rule mapping for higher-level control.

## Documentation

- [Current Pipeline](docs/current_pipeline.md)
- [MVP Plan](docs/mvp_plan.md)
- [MacBook Remote Setup](docs/macbook_remote_setup.md)
- [Windows / WSL Model Setup](docs/windows_wsl_model_setup.md)
