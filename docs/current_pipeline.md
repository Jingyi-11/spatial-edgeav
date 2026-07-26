# Current Verified Pipeline

This document records the end-to-end baseline that has already been verified.
It is the foundation for the later industrial version of Spatial EdgeAV:
continuous video, training, ONNX export, RKNN quantization, and RK3576 runtime
deployment.

## 1. Devices

```text
MacBook M1
  Role: project controller, Git workspace, SSH entry point.

Windows PC
  Role: remote x86 workstation reachable over Tailscale.

WSL2 Ubuntu 22.04
  Role: model validation environment.

RK3576 Ubuntu 24.04 ARM board
  Role: embedded Linux camera capture target.

Logitech C920 USB camera
  Role: current video input device.
```

Current SSH aliases from the Mac:

```bash
ssh rk3576
ssh winbox
ssh wslbox
```

## 2. Camera Capture on RK3576

The USB camera is plugged into the RK3576 board and appears as a V4L2 device.
The current verified capture device is:

```text
/dev/video73
```

Single-frame smoke test:

```bash
bash scripts/rk3576_camera_smoke_test.sh
```

Indoor camera tuning profile:

```bash
bash scripts/rk3576_camera_tune.sh rk3576 /dev/video73 indoor
```

Continuous capture baseline:

```bash
bash scripts/rk3576_stream_baseline.sh rk3576 /dev/video73 15 1280 720 30
```

The continuous capture script records MJPEG frames through GStreamer:

```text
v4l2src
  -> image/jpeg caps
  -> jpegparse
  -> matroskamux
  -> .mkv file
  -> preview JPEG
```

Runtime outputs are stored under:

```text
runs/rk3576_stream_baseline/
```

The `runs/` directory is ignored by Git because it may contain private images,
videos, and logs.

## 3. Sample Transfer to Windows

After a preview frame is captured on the Mac workspace, it is copied to the
Windows machine with:

```bash
bash scripts/send_sample_to_windows.sh
```

Default Windows path:

```text
C:\Users\HP\edgeav_data\rk3576_preview.jpg
```

Equivalent WSL path:

```text
/mnt/c/Users/HP/edgeav_data/rk3576_preview.jpg
```

## 4. WSL Model Validation

WSL is reachable directly from the Mac:

```bash
ssh wslbox
```

The direct WSL SSH path is preferred over first entering Windows and then
running `wsl.exe`, because it behaves like a normal Linux SSH login session and
is easier to automate.

The model smoke test is:

```bash
bash scripts/wsl_yolo_smoke_test.sh
```

The script performs:

```text
1. Verify the RK3576 sample frame exists in WSL.
2. Bootstrap pip if WSL is minimal.
3. Install CPU-only PyTorch, Ultralytics YOLO, and OpenCV in user scope.
4. Run YOLOv8n on the RK3576 frame.
5. Copy the annotated result back to the Mac workspace.
```

Verified environment:

```text
Ubuntu: 22.04.5 LTS in WSL2
Python: 3.10.12
PyTorch: 2.13.0+cpu
Ultralytics: 8.4.106
OpenCV: 5.0.0
```

Verified inference result on the first RK3576 sample:

```text
Model: YOLOv8n
Input: RK3576 C920 1280x720 JPEG frame
Detections: 1 person, 1 cup, 1 tv
CPU inference: about 26-31 ms
Output: runs/wsl_yolo_rk3576_preview.jpg
```

## 5. What This Proves

The current baseline proves that the distributed development setup works:

```text
MacBook orchestration
  -> RK3576 embedded camera capture
  -> SSH/SCP artifact movement
  -> WSL model inference
  -> reproducible command-line smoke test
```

This is a useful resume baseline because it touches real embedded development
work instead of only a notebook demo:

- remote Linux board access
- V4L2/GStreamer camera debugging
- camera image-quality tuning
- cross-machine data movement
- WSL model environment setup
- repeatable shell scripts
- privacy-aware artifact handling

## 6. Next Engineering Steps

Near-term:

```text
continuous RK3576 capture
  -> frame sampling
  -> WSL batch inference
  -> JSONL event log
  -> spatial rule evaluation
```

Deployment path:

```text
custom YOLO training on WSL
  -> ONNX export
  -> RKNN Toolkit2 conversion
  -> INT8 calibration
  -> RK3576 RKNN runtime
  -> C++ service with systemd
```

Spatial/VLA-style path:

```text
natural-language rule
  -> structured spatial policy
  -> object detections
  -> zone/dwell/line-crossing logic
  -> device action
```
