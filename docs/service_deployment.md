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

Verified installed service state:

```text
Loaded: enabled
Active: active (running)
Main process: python3 rk3576_rknn_camera_loop.py
Runtime mode: --frames 0 long-running service
```

Inspect runtime state:

```bash
sudo systemctl status spatial-edgeav-rknn.service
sudo journalctl -u spatial-edgeav-rknn.service -f
cat /home/kickpi/spatial-edgeav/runs/service/heartbeat.json
```

Collect a local long-run snapshot from the Mac workspace:

```bash
make collect-rknn-service-snapshot
```

The snapshot target writes local, git-ignored evidence under:

```text
runs/rk3576_service_snapshots/<timestamp>/
  heartbeat.json
  journal_tail.txt
  resource_snapshot.json
  systemctl_show.env
  systemctl_status.txt
  summary.json
  summary.md
```

The summary separates service health from model performance:

```text
systemd state: active/running, MainPID, restart count
heartbeat: frames processed, uptime, latest FPS, last-frame error
resources: process CPU/RSS/VSZ, memory, disk, thermal zones
journal: recent service logs for warnings or crashes
```

Verified service snapshot after installation:

```text
Snapshot: runs/rk3576_service_snapshots/20260804T211353Z/
ActiveState: active / running
MainPID: 38860
Frames processed: 2680
Uptime: 191.678 sec
Inference FPS: 24.940
End-to-end FPS: 14.370
Last frame error: None
Process RSS: 295856 KB
NPU thermal zone: 41.615 C
```

This confirms that the service is not only installable but actually running
under systemd, updating heartbeat state, and maintaining expected RKNN
camera-loop throughput over a multi-minute window.

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
