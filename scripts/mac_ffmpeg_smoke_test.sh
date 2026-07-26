#!/usr/bin/env bash
set -euo pipefail

DEVICE="${1:-0}"
RUN_DIR="${2:-runs/mac_ffmpeg_smoke}"
mkdir -p "${RUN_DIR}"

echo "Listing AVFoundation devices..."
/opt/homebrew/bin/ffmpeg -hide_banner -f avfoundation -list_devices true -i "" || true

echo "Capturing 5 seconds from video device ${DEVICE}..."
/opt/homebrew/bin/ffmpeg -y \
  -f avfoundation \
  -framerate 30 \
  -video_size 1280x720 \
  -i "${DEVICE}:none" \
  -t 5 \
  -pix_fmt yuv420p \
  "${RUN_DIR}/camera_smoke.mp4"

echo "Extracting preview frame..."
/opt/homebrew/bin/ffmpeg -y \
  -i "${RUN_DIR}/camera_smoke.mp4" \
  -frames:v 1 \
  -update 1 \
  "${RUN_DIR}/preview.jpg"

echo "Wrote:"
echo "  ${RUN_DIR}/camera_smoke.mp4"
echo "  ${RUN_DIR}/preview.jpg"
