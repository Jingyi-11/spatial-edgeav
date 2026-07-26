#!/usr/bin/env bash
set -euo pipefail

DEVICE="${1:-/dev/video0}"
WIDTH="${WIDTH:-1280}"
HEIGHT="${HEIGHT:-720}"
FPS="${FPS:-30}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8554}"
PATH_NAME="${PATH_NAME:-live}"

cat <<EOF
This script needs a running RTSP server that accepts RTP/H264 publishing.
For a quick lab, run MediaMTX separately, then publish with this pipeline.

Client URL:
  rtsp://${HOST}:${PORT}/${PATH_NAME}
EOF

gst-launch-1.0 -v \
  v4l2src device="${DEVICE}" \
  ! "video/x-raw,width=${WIDTH},height=${HEIGHT},framerate=${FPS}/1" \
  ! videoconvert \
  ! x264enc tune=zerolatency bitrate=2000 speed-preset=ultrafast key-int-max="${FPS}" \
  ! h264parse config-interval=1 \
  ! rtspclientsink location="rtsp://${HOST}:${PORT}/${PATH_NAME}"
