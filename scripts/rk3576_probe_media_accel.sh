#!/usr/bin/env bash
set -euo pipefail

BOARD_HOST="${BOARD_HOST:-rk3576}"
DEVICE="${DEVICE:-/dev/video73}"
WIDTH="${WIDTH:-1280}"
HEIGHT="${HEIGHT:-720}"
FPS="${FPS:-30}"
FRAMES="${FRAMES:-120}"

ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "DEVICE='${DEVICE}' WIDTH='${WIDTH}' HEIGHT='${HEIGHT}' FPS='${FPS}' FRAMES='${FRAMES}' bash -s" <<'REMOTE'
set -euo pipefail

echo "== pkg-config =="
pkg-config --modversion gstreamer-1.0 2>/dev/null || true
pkg-config --modversion gstreamer-app-1.0 2>/dev/null || true
pkg-config --modversion librga 2>/dev/null || true

echo "== headers =="
ls /usr/include/gstreamer-1.0/gst/gst.h \
   /usr/include/gstreamer-1.0/gst/app/gstappsink.h \
   /usr/include/rga/im2d.h \
   /usr/include/rga/RgaApi.h 2>/dev/null || true

echo "== devices =="
ls -l /dev/rga /dev/dri/renderD* 2>/dev/null || true

echo "== gstreamer decode+scale benchmark =="
if command -v gst-launch-1.0 >/dev/null 2>&1; then
  start_ms="$(date +%s%3N)"
  gst-launch-1.0 -q \
    v4l2src device="${DEVICE}" num-buffers="${FRAMES}" \
    ! "image/jpeg,width=${WIDTH},height=${HEIGHT},framerate=${FPS}/1" \
    ! jpegparse \
    ! jpegdec \
    ! videoconvert \
    ! videoscale \
    ! video/x-raw,format=RGB,width=640,height=360 \
    ! fakesink sync=false
  end_ms="$(date +%s%3N)"
  elapsed_ms="$((end_ms - start_ms))"
  python3 - <<PY
frames = float("${FRAMES}")
elapsed_ms = float("${elapsed_ms}")
fps = frames / (elapsed_ms / 1000.0) if elapsed_ms > 0 else 0.0
print({"frames": int(frames), "elapsed_ms": elapsed_ms, "fps": round(fps, 3)})
PY
else
  echo "gst-launch-1.0 not found"
fi
REMOTE
