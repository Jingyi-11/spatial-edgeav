# RK3576 Service Deployment

This document tracks Phase 4A of Spatial EdgeAV: package the verified Python
RKNN camera loop as a long-running embedded Linux service.

## Service Shape

The benchmark loop now supports two modes:

```text
--frames 60
  fixed-frame benchmark mode

--frames 0
  long-running service mode, stopped by SIGTERM/SIGINT
```

In service mode the process writes:

```text
/home/kickpi/spatial-edgeav/runs/service/heartbeat.json
/home/kickpi/spatial-edgeav/runs/service/rknn_camera_report.json
/home/kickpi/spatial-edgeav/runs/service/rknn_camera_frames.json
/home/kickpi/spatial-edgeav/runs/service/rknn_camera_last.jpg
```

The heartbeat is a small JSON status file for health checks. The final report is
written on clean shutdown. The in-memory frame record buffer is bounded by
`--max-frame-records` so a long-running service does not grow without limit.

## Files

```text
systemd/spatial-edgeav-rknn.service
configs/spatial-edgeav-rknn.env
scripts/deploy_rknn_service_to_rk3576.sh
scripts/rk3576_install_rknn_service.sh
scripts/rk3576_rknn_camera_loop.py
```

## Stage and Preflight

From the Mac workspace:

```bash
make deploy-rknn-service-board
```

This copies the RKNN model, Python runtime helpers, systemd unit, and env file
to the RK3576 board, then runs a 5-frame service-command preflight without
installing the system service.

Verified preflight:

```text
Frames: 5
Capture mean: 15.618 ms
Preprocess mean: 5.221 ms
Inference mean: 43.112 ms
Postprocess mean: 3.251 ms
End-to-end mean: 67.204 ms
End-to-end FPS: 14.880
Detected classes: person 6, surfboard 1
```

## Install Systemd Service

Installing under `/etc/systemd/system` requires board-side sudo:

```bash
ssh rk3576
ENABLE_SERVICE=1 START_SERVICE=1 bash /home/kickpi/spatial-edgeav/bin/rk3576_install_rknn_service.sh
```

Inspect runtime state:

```bash
sudo systemctl status spatial-edgeav-rknn.service
sudo journalctl -u spatial-edgeav-rknn.service -f
cat /home/kickpi/spatial-edgeav/runs/service/heartbeat.json
```

Restart or stop:

```bash
sudo systemctl restart spatial-edgeav-rknn.service
sudo systemctl stop spatial-edgeav-rknn.service
```

## Why This Matters

The project now has the operational boundary expected from an embedded Linux
edge-AI service:

```text
external env configuration
systemd restart policy
journald logs
heartbeat JSON status
graceful SIGTERM shutdown
bounded retained frame records
```

The remaining Phase 4 work is to add long-run resource profiling, service
health checks, log rotation policy, and eventually migrate the hot capture /
preprocess / RKNN / postprocess path from Python into C/C++.
