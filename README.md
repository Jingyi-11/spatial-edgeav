# Linux Camera EdgeAV Pipeline

面向 Rockchip RK3567/RK3576 边缘设备的 Linux 音视频 AI pipeline 项目。项目目标不是只跑一个 camera demo，而是把真实智能相机/边缘 AI 设备里的链路拆开：摄像头采集、格式处理、硬件编码、RTSP/MP4 输出、后续 RKNN 推理和远程部署。

```text
MIPI CSI / USB Camera
        |
rkcif / rkisp / uvcvideo
        |
V4L2 / Media Controller
        |
NV12 / YUYV Raw Frames
        |
RGA / RKNN / MPP
        |
AI Inference + H.264/H.265 Encode
        |
RTSP / MP4 / WebRTC / Event Upload
```

## Highlights

- V4L2 MMAP camera capture skeleton in C
- NV12/YUYV raw frame capture for Linux camera devices
- PPM preview generation from captured YUYV frames
- RK3567/RK3576 media graph probing scripts
- GStreamer preview and H.264 RTSP publish scripts
- FFmpeg audio/video MP4 recording scripts
- macOS fallback simulation path for local development without V4L2
- MacBook remote development setup for Windows/WSL/RK3576 workflows

## Target Hardware

| Role | Device | Purpose |
|---|---|---|
| Development | MacBook M1 | Code editing, GitHub, SSH control, local simulation |
| Conversion/Training | Windows + WSL2 Ubuntu | PyTorch/ONNX/RKNN conversion workflow |
| Edge Runtime | RK3567/RK3576 board | V4L2 capture, RKNN Runtime, streaming and benchmark |
| Input | USB/MIPI camera | Real-time video source |

## Project Structure

```text
.
├── Makefile
├── README.md
├── configs/
│   └── camera.conf
├── docs/
│   ├── macbook_remote_setup.md
│   └── pipeline_walkthrough.md
├── include/
│   ├── camera_capture.h
│   ├── pipeline.h
│   └── yuv.h
├── scripts/
│   ├── 00_rk3567_install_tools.sh
│   ├── 01_probe_camera.sh
│   ├── 01_rk3567_probe_media.sh
│   ├── 02_capture_raw_yuyv.sh
│   ├── 02_rk3567_capture_nv12.sh
│   ├── 03_ffmpeg_record_mp4.sh
│   ├── 04_gstreamer_preview.sh
│   ├── 05_gstreamer_rtsp_h264.sh
│   ├── 06_ffmpeg_rtsp_publish.sh
│   ├── 07_rk3567_gst_preview_nv12.sh
│   ├── 08_rk3567_gst_rtsp_mpp.sh
│   ├── 09_rk3567_ffmpeg_record_nv12.sh
│   ├── 10_rk3567_rknn_notes.sh
│   ├── configure_mac_ssh_hosts.sh
│   └── macbook_remote_check.sh
└── src/
    ├── camera_capture.c
    ├── main.c
    ├── pipeline.c
    └── yuv.c
```

## Module Overview

| Path | Responsibility |
|---|---|
| `src/camera_capture.c` | Opens V4L2 devices, configures format/FPS, allocates MMAP buffers, streams frames |
| `src/yuv.c` | YUYV/NV12 frame utilities and YUYV-to-PPM preview generation |
| `src/pipeline.c` | Capture pipeline orchestration |
| `src/main.c` | CLI entrypoint for `probe` and `capture` commands |
| `configs/camera.conf` | Default RK3567 camera parameters |
| `scripts/01_rk3567_probe_media.sh` | Probes `/dev/video*`, `/dev/media*`, V4L2 formats, controls, encoder plugins |
| `scripts/02_rk3567_capture_nv12.sh` | Captures common RK ISP NV12 raw frames |
| `scripts/08_rk3567_gst_rtsp_mpp.sh` | Publishes H.264 stream with `mpph264enc`, `v4l2h264enc`, or `x264enc` |
| `docs/macbook_remote_setup.md` | MacBook-to-Windows/WSL/RK3576 remote development setup |

## Build on MacBook or Linux

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

On non-Linux hosts, the program uses simulated frames because V4L2 is not available. Real camera capture should run on Linux or the RK board.

## Prepare RK3567/RK3576

```bash
./scripts/00_rk3567_install_tools.sh
```

If apt cannot find Rockchip-specific packages, use the board vendor SDK/image. Rockchip media stacks are often shipped as preinstalled runtime libraries or GStreamer plugins.

Important platform keywords:

- `rkcif`: Rockchip Camera Interface
- `rkisp`: Rockchip ISP for exposure, white balance, denoise, and format output
- `V4L2`: Linux userspace camera capture API
- `media-ctl`: media graph inspection tool for MIPI camera pipelines
- `MPP`: Rockchip hardware video encode/decode framework
- `RGA`: Rockchip 2D accelerator for resize/crop/format conversion
- `RKNN`: Rockchip NPU inference runtime

## Probe Camera Nodes

```bash
./scripts/01_rk3567_probe_media.sh /dev/video0
```

The script checks:

- `/dev/video*`, `/dev/media*`, `/dev/v4l-subdev*`
- `v4l2-ctl --list-devices`
- `media-ctl -p`
- selected device formats and controls
- available GStreamer H.264 encoders

For MIPI CSI cameras, the correct capture node is not always `/dev/video0`. Use the media graph to find the `rkisp`/`rkcif` capture node.

## Capture Raw Video

Capture RK3567/RK3576 common NV12 frames:

```bash
./scripts/02_rk3567_capture_nv12.sh /dev/videoX
```

Play raw NV12 output:

```bash
ffplay -f rawvideo -pixel_format nv12 -video_size 1280x720 -framerate 30 out/rk3567_capture_nv12.yuv
```

Capture YUYV and generate a PPM preview:

```bash
./scripts/02_capture_raw_yuyv.sh /dev/videoX
```

## Preview and Stream

Local GStreamer preview:

```bash
./scripts/07_rk3567_gst_preview_nv12.sh /dev/videoX
```

If the camera only supports YUYV:

```bash
FORMAT=YUYV ./scripts/07_rk3567_gst_preview_nv12.sh /dev/videoX
```

Start an RTSP server such as MediaMTX, then publish H.264:

```bash
RTSP_URL=rtsp://127.0.0.1:8554/live ./scripts/08_rk3567_gst_rtsp_mpp.sh /dev/videoX
```

Play the stream:

```bash
ffplay rtsp://127.0.0.1:8554/live
```

The RTSP script chooses encoders in this order:

1. `mpph264enc`
2. `v4l2h264enc`
3. `x264enc`

## Record Audio + Video

```bash
./scripts/09_rk3567_ffmpeg_record_nv12.sh /dev/videoX
```

Change ALSA audio device:

```bash
AUDIO_DEVICE=hw:0,0 ./scripts/09_rk3567_ffmpeg_record_nv12.sh /dev/videoX
```

## CLI Usage

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

Capture YUYV and generate preview:

```bash
./build/embedded_camera capture \
  --device /dev/videoX \
  --width 640 \
  --height 480 \
  --fps 30 \
  --frames 30 \
  --format YUYV \
  --output out/capture_yuyv.yuv \
  --preview out/preview.ppm
```

## Remote Development

This project is designed to support a travel-friendly workflow:

```text
MacBook
  -> SSH/Tailscale
Windows + WSL2 Ubuntu
  -> RKNN conversion / training scripts
RK3576 + USB camera
  -> Linux edge runtime tests
```

Check MacBook readiness:

```bash
./scripts/macbook_remote_check.sh
```

Configure SSH aliases after collecting Windows/RK3576 addresses:

```bash
WIN_HOST=100.x.y.z \
WIN_USER=<windows_user> \
WSL_USER=<wsl_user> \
RK3576_HOST=192.168.1.88 \
./scripts/configure_mac_ssh_hosts.sh
```

Then test:

```bash
ssh winbox hostname
ssh wsl 'uname -a'
ssh rk3576 'uname -a'
ssh rk3576-via-win 'ls /dev/video*'
```

See `docs/macbook_remote_setup.md` for the full setup.

## Roadmap

- Auto-select usable V4L2 capture nodes from media graph output
- Add MJPEG input support and YUYV/NV12 conversion paths
- Move H.264 encode from shell/GStreamer demos into a C/C++ MPP module
- Add ALSA PCM capture with monotonic timestamps
- Add audio/video synchronization and ring-buffer pipeline
- Add RKNN Runtime inference module for YOLO-style object detection
- Add RGA resize/letterbox preprocessing
- Add event engine for restricted-zone/person/vehicle detection
- Add MQTT/REST event reporting
- Add systemd service, structured logging, watchdog, and benchmark reports

## Why This Project Matters

This project is built around the skills used in embedded camera and edge AI roles:

- Linux device programming
- V4L2/media-controller camera debugging
- C/C++ real-time capture pipeline design
- GStreamer/FFmpeg video streaming
- Rockchip MPP/RGA/RKNN deployment path
- Remote development with MacBook, Windows/WSL, and ARM Linux boards
- Performance-oriented edge AI system design

