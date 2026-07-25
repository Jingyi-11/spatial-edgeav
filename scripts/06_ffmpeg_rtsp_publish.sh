#!/usr/bin/env bash
set -euo pipefail

DEVICE="${1:-/dev/video0}"
AUDIO_DEVICE="${AUDIO_DEVICE:-default}"
WIDTH="${WIDTH:-1280}"
HEIGHT="${HEIGHT:-720}"
FPS="${FPS:-30}"
RTSP_URL="${RTSP_URL:-rtsp://127.0.0.1:8554/live}"

ffmpeg -re \
  -f v4l2 -framerate "${FPS}" -video_size "${WIDTH}x${HEIGHT}" -input_format yuyv422 -i "${DEVICE}" \
  -f alsa -i "${AUDIO_DEVICE}" \
  -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p \
  -c:a aac -b:a 128k \
  -f rtsp -rtsp_transport tcp \
  "${RTSP_URL}"
