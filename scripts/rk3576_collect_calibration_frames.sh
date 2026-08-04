#!/usr/bin/env bash
set -euo pipefail

HOST="${1:-rk3576}"
DEVICE="${2:-/dev/video73}"
COUNT="${3:-100}"
WIDTH="${4:-1280}"
HEIGHT="${5:-720}"
FPS="${6:-10}"
OUT_DIR="${7:-runs/model_exports/yolov8n/calib}"
REMOTE_DIR="/tmp/edgeav_rknn_calib"

mkdir -p "${OUT_DIR}/images"

echo "Capturing ${COUNT} calibration frame(s) from ${HOST}:${DEVICE}..."
ssh -o BatchMode=yes -o ConnectTimeout=8 "${HOST}" \
  "rm -rf '${REMOTE_DIR}' && mkdir -p '${REMOTE_DIR}' && \
   gst-launch-1.0 -q -e \
     v4l2src device='${DEVICE}' num-buffers='${COUNT}' \
     ! image/jpeg,width=${WIDTH},height=${HEIGHT},framerate=${FPS}/1 \
     ! multifilesink location='${REMOTE_DIR}/calib_%04d.jpg'"

echo "Copying calibration frames back to Mac..."
scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${HOST}:${REMOTE_DIR}/calib_*.jpg" \
  "${OUT_DIR}/images/"

find "${OUT_DIR}/images" -type f -name 'calib_*.jpg' | sort > "${OUT_DIR}/dataset.txt"

echo "Wrote:"
echo "  ${OUT_DIR}/images/"
echo "  ${OUT_DIR}/dataset.txt"
