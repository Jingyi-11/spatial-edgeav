# Spatial EdgeAV Web Dashboard

## Why Web Dashboard First

The project can expose visual/event outputs in several ways:

| Option | Main purpose | Fit for this project |
| --- | --- | --- |
| Web dashboard | Human-facing UI for video, health, and events | Best MVP/demo path |
| HTTP MJPEG | Browser-friendly live video stream | Implemented |
| WebSocket | Push events to browser instantly | Future upgrade; current page polls every second |
| RTSP | Standard video stream for VLC/NVR systems | Useful later, not required for browser dashboard |
| MQTT | IoT/event bus for device-to-device actions | Future integration for external systems |
| Grafana | Long-term metrics and operations dashboard | Future integration for 24h/7d monitoring |
| Local monitor | HDMI display connected to RK3576 | Use the same web page in a local browser/kiosk |

RTSP is not required to see video in a browser. The current dashboard uses HTTP
MJPEG:

```text
C++ service writes latest_frame.jpg
  -> Python dashboard reads latest_frame.jpg
  -> /stream.mjpg sends multipart JPEG frames
  -> browser <img> shows live video
```

This is simpler than RTSP and fits the current C920 MJPEG camera path.

## Current Action Layer

Before the dashboard, a spatial rule trigger only wrote `events.jsonl`.

Current action chain:

```text
spatial rule triggered
  -> append event to events.jsonl
  -> dashboard polls /api/events
  -> browser popup toast
  -> optional browser beep sound
  -> event remains in the recent-events list
```

This is intentionally browser-side audio. It does not require a speaker on the
RK3576 board. The user must click `Enable Alert Sound` once because browsers
block autoplaying sound before user interaction.

## Runtime Artifacts

The dashboard reads the C++ service run directory:

```text
/home/kickpi/spatial-edgeav/runs/cpp_service/heartbeat.json
/home/kickpi/spatial-edgeav/runs/cpp_service/events.jsonl
/home/kickpi/spatial-edgeav/runs/cpp_service/latest_frame.jpg
```

`heartbeat.json` drives runtime cards:

- service status
- camera FPS
- RKNN frames/failures
- spatial events/failures
- end-to-end latency

`events.jsonl` drives the recent-event list, popup action, and sound action.

`latest_frame.jpg` drives the live video stream.

## Security Model

The dashboard contains live camera imagery, so it is bound to localhost on the
RK3576 board by default:

```text
EDGEAV_DASHBOARD_HOST=127.0.0.1
EDGEAV_DASHBOARD_PORT=8080
```

Open it from Mac with an SSH tunnel:

```bash
ssh -N -L 8080:127.0.0.1:8080 rk3576
```

Then open:

```text
http://127.0.0.1:8080
```

If a monitor is connected directly to the RK3576, open the same local URL in a
browser on the board:

```text
http://127.0.0.1:8080
```

## Deployment

The C++ service must use a runtime binary that includes `--latest-jpeg-dump`.
Install/restart the C++ service first:

```bash
ENABLE_SERVICE=1 START_SERVICE=1 make deploy-cpp-runtime-service-board
```

Install/start the dashboard service:

```bash
ENABLE_SERVICE=1 START_SERVICE=1 make deploy-dashboard-board
```

Both installation targets write to `/etc/systemd/system`, so the board will ask
for the `kickpi` sudo password.

## Future Upgrades

- Add WebSocket or Server-Sent Events to push event notifications without
  polling.
- Draw live bbox/zone overlays in the browser by pairing detections with the
  latest frame timestamp.
- Add MQTT publish for external IoT actions.
- Add RTSP if integration with VLC/NVR/video monitoring systems is required.
- Export Prometheus metrics and build a Grafana dashboard for long-duration
  performance monitoring.
