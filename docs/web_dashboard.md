# Spatial EdgeAV Web Dashboard

## Why Web Dashboard First

The project can expose visual/event outputs in several ways:

| Option | Main purpose | Fit for this project |
| --- | --- | --- |
| Web dashboard | Human-facing UI for video, health, and events | Implemented demo path |
| HTTP MJPEG | Browser-friendly live video stream | Implemented |
| SSE | Push one-way events to browser instantly | Implemented for spatial events |
| WebSocket | Bidirectional browser/device messages | Future upgrade if live control is needed |
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
  -> canvas overlays zones, detections, and event bboxes
```

This is simpler than RTSP and fits the current C920 MJPEG camera path.

## Current Action Layer

Before the dashboard, a spatial rule trigger only wrote `events.jsonl`.

Current action chain:

```text
spatial rule triggered
  -> append event to events.jsonl
  -> dashboard pushes event list through /events.sse
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
/home/kickpi/spatial-edgeav/runs/cpp_service/edgeav_runtime_frames.json
/home/kickpi/spatial-edgeav/configs/spatial_rules.json
```

`heartbeat.json` drives runtime cards:

- service status
- camera FPS
- RKNN frames/failures
- spatial events/failures
- end-to-end latency

`events.jsonl` drives the recent-event list, popup action, and sound action.

`latest_frame.jpg` drives the live video stream.

`edgeav_runtime_frames.json` drives the latest detection boxes. The dashboard
uses `bbox_original_xyxy` when available so the overlay aligns with the
1280x720 camera image rather than the model's 640x640 input.

`spatial_rules.json` drives the zone overlay. The dashboard converts
`polygon_norm` coordinates into original-frame pixels using the camera width and
height reported in `heartbeat.json`.

## Dashboard API

```text
/stream.mjpg             HTTP MJPEG live video stream
/events.sse              Server-Sent Events stream for recent spatial events
/api/heartbeat           service health and latency counters
/api/events?limit=20     polling fallback for spatial events
/api/spatial-config      zones/rules converted for overlay drawing
/api/latest-detections   latest C++ runtime detections for bbox overlay
/api/zone-status         live per-zone idle/active/alert state
POST /api/spatial-config save edited zone polygons
/snapshot.jpg            current frame still image
```

## Zone Editor

The dashboard now behaves more like a small Frigate-style NVR UI. It keeps the
live video on the left and adds a browser-side Zone Editor on the right:

```text
select a zone
  -> Edit
  -> drag polygon vertices on the live frame
  -> Save
  -> restart spatial-edgeav-cpp.service for rule-engine reload
```

The Save action updates only `zones` in `spatial_rules.json`; existing rules,
thresholds, dwell settings, and messages are preserved. The overlay refreshes
immediately after saving. The C++ runtime is intentionally restarted separately
because it treats spatial rules as runtime configuration loaded at process
startup.

The Zone Monitor is separate from rule events. It continuously reads the latest
detections and marks each zone as:

| State | Meaning |
| --- | --- |
| `idle` | no current detection anchor is inside the zone |
| `active` | at least one current detection anchor is inside the zone |
| `alert` | a recent rule event belongs to the zone |

The monitor uses the bottom-center point of each bbox for zone membership,
matching a common NVR convention for ground-plane zones. This is more stable
than full bbox overlap for people, because the bottom of the box better
approximates where the person is standing.

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

## GStreamer/RGA Preprocessing Gate

The current live runtime still uses the stable C/C++ path:

```text
V4L2 MJPEG -> libjpeg decode -> CPU letterbox resize -> RKNN NPU
```

The repo now includes a board-side benchmark gate for the next hardware
preprocessing step:

```bash
make benchmark-gst-rga-preprocess-board
```

It records:

- software GStreamer decode/scale throughput
- Rockchip hardware GStreamer element candidates such as MPP/RGA plugins
- `/dev/rga` and `librga` availability
- a JSON report under `runs/rk3576_media_accel/`

This keeps the production runtime honest: hardware preprocessing is only
promoted into the hot path after the board proves the needed plugins/devices are
present and faster than the CPU reference.

## Future Upgrades

- Add MQTT publish for external IoT actions.
- Add RTSP if integration with VLC/NVR/video monitoring systems is required.
- Export Prometheus metrics and build a Grafana dashboard for long-duration
  performance monitoring.
- Promote RGA/GStreamer preprocessing from benchmark gate into the C/C++ runtime
  after board-side plugin validation.
