#!/usr/bin/env bash
set -euo pipefail

DEVICE="${1:-/dev/video0}"
WIDTH="${WIDTH:-1280}"
HEIGHT="${HEIGHT:-720}"
FPS="${FPS:-30}"
FORMAT="${FORMAT:-NV12}"
RTSP_URL="${RTSP_URL:-rtsp://127.0.0.1:8554/live}"
BITRATE="${BITRATE:-2000000}"

if gst-inspect-1.0 mpph264enc >/dev/null 2>&1; then
  ENCODER="mpph264enc bps=${BITRATE}"
elif gst-inspect-1.0 v4l2h264enc >/dev/null 2>&1; then
  ENCODER="v4l2h264enc extra-controls=\"controls,video_bitrate=${BITRATE};\""
elif gst-inspect-1.0 x264enc >/dev/null 2>&1; then
  ENCODER="x264enc tune=zerolatency bitrate=$((BITRATE / 1000)) speed-preset=ultrafast key-int-max=${FPS}"
else
  echo "No H.264 encoder found. Install Rockchip MPP/GStreamer plugin or x264enc." >&2
  exit 1
fi

cat <<EOF
Publishing RK3567 camera to:
  ${RTSP_URL}

Selected encoder:
  ${ENCODER}

Start MediaMTX or another RTSP server before running this script.
EOF

gst-launch-1.0 -v \
  v4l2src device="${DEVICE}" io-mode=mmap \
  ! "video/x-raw,format=${FORMAT},width=${WIDTH},height=${HEIGHT},framerate=${FPS}/1" \
  ! queue \
  ! ${ENCODER} \
  ! h264parse config-interval=1 \
  ! rtspclientsink location="${RTSP_URL}"
