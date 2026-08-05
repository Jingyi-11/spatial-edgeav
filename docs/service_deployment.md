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

## Long-Run Profiling

For trend-style profiling, sample the running systemd service over time:

```bash
make profile-rknn-service
```

The default target samples for 300 seconds at a 30-second interval. For a short
validation run:

```bash
python3 scripts/profile_rknn_service.py --duration-sec 60 --interval-sec 15
```

The profiler writes local, git-ignored artifacts under:

```text
runs/rk3576_service_profiles/<timestamp>/
  samples.json
  summary.json
  summary.md
```

Verified 60-second profiling result:

```text
Snapshot: runs/rk3576_service_profiles/20260804T212207Z/
Samples: 5
Active all samples: True
Running all samples: True
Restart count delta: 0
Frames processed delta: 820
Uptime delta: 60.236 sec
End-to-end FPS mean: 14.366
Inference FPS mean: 24.950
Process CPU mean: 79.280%
RSS mean: 315013.6 KB
RSS delta: 23064 KB
NPU temperature mean: 43.276 C
Last-frame errors: []
```

This adds a trend view on top of single snapshots. The important stability
signals are stable systemd state, zero restart increase, frame count increasing,
no last-frame errors, bounded memory growth, and temperatures far below thermal
throttling territory.

## Health Check

Run a threshold-based health check against the live service:

```bash
make check-rknn-service-health
```

The check writes local, git-ignored artifacts under:

```text
runs/rk3576_service_health/<timestamp>/
  health.json
  health.md
```

Default thresholds:

```text
systemd state: active/running
MainPID: nonzero
heartbeat age: <= 30 sec
restart count: <= 0
end-to-end FPS: >= 10
RSS: <= 600000 KB
max thermal-zone temperature: <= 75 C
last-frame error: None
```

Verified health check:

```text
Overall: ok
Checked at: 2026-08-04T21:29:58+00:00
Heartbeat age: 0.774 sec
End-to-end FPS: 14.307
Restart count: 0
RSS: 376812 KB
Max temperature: 46.230 C
Last-frame error: None
```

The health-check script is intended to become the boundary for alerting or a
future systemd timer: it translates raw service state into an explicit
`ok/warn/critical` decision that CI, cron, dashboards, or deployment scripts can
consume.

## Board-Local Health Timer

The Mac-side health check is useful for remote acceptance. The board-local
timer lets the RK3576 check itself periodically without depending on a laptop
being online.

Repository files:

```text
scripts/rk3576_service_health_local.py
systemd/spatial-edgeav-rknn-health.service
systemd/spatial-edgeav-rknn-health.timer
```

After staging the service files with `make deploy-rknn-service-board`, install
and start the timer from the Mac:

```bash
make install-rknn-health-timer-board
```

Equivalent board-side command:

```bash
INSTALL_HEALTH_TIMER=1 ENABLE_HEALTH_TIMER=1 START_HEALTH_TIMER=1 bash /home/kickpi/spatial-edgeav/bin/rk3576_install_rknn_service.sh
```

The timer runs one-shot health checks after boot and then once per minute:

```text
OnBootSec=2min
OnUnitActiveSec=1min
AccuracySec=10s
```

It writes board-local artifacts:

```text
/home/kickpi/spatial-edgeav/runs/service_health/health.json
/home/kickpi/spatial-edgeav/runs/service_health/health.md
```

Useful inspection commands:

```bash
sudo systemctl status spatial-edgeav-rknn-health.timer
sudo systemctl list-timers spatial-edgeav-rknn-health.timer
sudo journalctl -u spatial-edgeav-rknn-health.service -n 50
cat /home/kickpi/spatial-edgeav/runs/service_health/health.json
```

Verified board-local checker before installing the timer:

```text
Overall: ok
Checked at: 2026-08-04T21:51:02+00:00
Heartbeat age: 0.635 sec
End-to-end FPS: 14.236
Restart count: 0
RSS: 364224 KB
Max temperature: 46.230 C
Last-frame error: None
```

Installing the timer writes unit files into `/etc/systemd/system`, so it
requires an interactive `sudo` password on the board. The Makefile target uses
`ssh -t` for that reason.

The local timer intentionally writes the latest health result in place. That
keeps disk usage bounded on a small embedded root filesystem while still giving
CI, SSH checks, or a future dashboard a stable file to read.

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
board-local timer health checks
```

The remaining Phase 4 work is to add a stricter log retention policy and
eventually migrate the hot capture / preprocess / RKNN / postprocess path from
Python into C/C++.

## C++ Runtime Service

The project now has a separate C++ service unit for the optimized runtime path:

```text
systemd/spatial-edgeav-cpp.service
configs/spatial-edgeav-cpp.env
scripts/deploy_cpp_runtime_service_to_rk3576.sh
```

It runs:

```text
V4L2 USB camera MJPEG
  -> libjpeg decode
  -> letterbox to YOLO 640x640
  -> RKNN/NPU inference
  -> C++ YOLO postprocess
  -> original-frame bbox mapping
  -> C++ spatial rules
  -> heartbeat/report/observations/events
```

Install target:

```bash
make deploy-cpp-runtime-service-board
```

By default the deploy script installs the unit and env file but does not enable
or start the service. To enable or start explicitly:

```bash
ENABLE_SERVICE=1 make deploy-cpp-runtime-service-board
START_SERVICE=1 make deploy-cpp-runtime-service-board
```

Only one camera service should own `/dev/video73` at a time. Stop the Python
service before starting the C++ service:

```bash
sudo systemctl stop spatial-edgeav-rknn.service
sudo systemctl start spatial-edgeav-cpp.service
```

Inspect:

```bash
sudo systemctl status spatial-edgeav-cpp.service
sudo journalctl -u spatial-edgeav-cpp.service -f
cat /home/kickpi/spatial-edgeav/runs/cpp_service/heartbeat.json
cat /home/kickpi/spatial-edgeav/runs/cpp_service/events.jsonl
```

`--frames 0` now means continuous capture in the C/C++ runtime. The service
uses `--max-frame-records 300` so the retained per-frame JSON stays bounded
while heartbeat/report counters continue to update.

Installation writes into `/etc/spatial-edgeav` and `/etc/systemd/system`, so
the board prompts for the `kickpi` sudo password. The script uses `ssh -tt`,
which works from a normal terminal but cannot be completed by non-interactive
automation without passwordless sudo or an askpass setup.
