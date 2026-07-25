#!/usr/bin/env bash
set -euo pipefail

DEVICE="${1:-/dev/video0}"
WIDTH="${WIDTH:-640}"
HEIGHT="${HEIGHT:-480}"
FPS="${FPS:-30}"
FRAMES="${FRAMES:-90}"
OUT="${OUT:-out/capture.yuv}"
PREVIEW="${PREVIEW:-out/preview.ppm}"

mkdir -p out
make

./build/embedded_camera capture \
  --device "${DEVICE}" \
  --width "${WIDTH}" \
  --height "${HEIGHT}" \
  --fps "${FPS}" \
  --frames "${FRAMES}" \
  --format YUYV \
  --output "${OUT}" \
  --preview "${PREVIEW}"

echo
echo "Play raw YUYV with:"
echo "ffplay -f rawvideo -pixel_format yuyv422 -video_size ${WIDTH}x${HEIGHT} -framerate ${FPS} ${OUT}"
