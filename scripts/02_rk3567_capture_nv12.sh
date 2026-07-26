#!/usr/bin/env bash
set -euo pipefail

DEVICE="${1:-/dev/video0}"
WIDTH="${WIDTH:-1280}"
HEIGHT="${HEIGHT:-720}"
FPS="${FPS:-30}"
FRAMES="${FRAMES:-90}"
OUT="${OUT:-out/rk3567_capture_nv12.yuv}"

mkdir -p out
make

./build/embedded_camera capture \
  --device "${DEVICE}" \
  --width "${WIDTH}" \
  --height "${HEIGHT}" \
  --fps "${FPS}" \
  --frames "${FRAMES}" \
  --format NV12 \
  --output "${OUT}"

echo
echo "Play raw NV12 with:"
echo "ffplay -f rawvideo -pixel_format nv12 -video_size ${WIDTH}x${HEIGHT} -framerate ${FPS} ${OUT}"
