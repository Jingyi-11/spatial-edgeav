#!/usr/bin/env bash
set -euo pipefail

DEVICE="${1:-/dev/video0}"
AUDIO_DEVICE="${AUDIO_DEVICE:-default}"
WIDTH="${WIDTH:-1280}"
HEIGHT="${HEIGHT:-720}"
FPS="${FPS:-30}"
DURATION="${DURATION:-10}"
OUT="${OUT:-out/record_av.mp4}"

mkdir -p out

ffmpeg -y \
  -f v4l2 -framerate "${FPS}" -video_size "${WIDTH}x${HEIGHT}" -input_format yuyv422 -i "${DEVICE}" \
  -f alsa -i "${AUDIO_DEVICE}" \
  -t "${DURATION}" \
  -c:v libx264 -preset veryfast -tune zerolatency -pix_fmt yuv420p \
  -c:a aac -b:a 128k \
  "${OUT}"

echo "Wrote ${OUT}"
