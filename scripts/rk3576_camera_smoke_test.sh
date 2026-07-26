#!/usr/bin/env bash
set -euo pipefail

HOST="${1:-rk3576}"
DEVICE="${2:-/dev/video73}"
WIDTH="${3:-1280}"
HEIGHT="${4:-720}"
FPS="${5:-30}"
RUN_DIR="${6:-runs/rk3576_camera_smoke}"
REMOTE_DIR="/tmp/edgeav_camera"
REMOTE_IMAGE="${REMOTE_DIR}/usb_camera_${WIDTH}x${HEIGHT}.jpg"
LOCAL_IMAGE="${RUN_DIR}/usb_camera_${WIDTH}x${HEIGHT}.jpg"

mkdir -p "${RUN_DIR}"

echo "Checking camera devices on ${HOST}..."
ssh -o BatchMode=yes -o ConnectTimeout=8 "${HOST}" \
  "v4l2-ctl --list-devices 2>/dev/null; echo; v4l2-ctl --device='${DEVICE}' --all | sed -n '1,80p'"

echo "Capturing one MJPEG frame from ${DEVICE}..."
ssh -o BatchMode=yes -o ConnectTimeout=8 "${HOST}" \
  "mkdir -p '${REMOTE_DIR}' && gst-launch-1.0 -q -e \
    v4l2src device='${DEVICE}' num-buffers=1 \
    ! image/jpeg,width=${WIDTH},height=${HEIGHT},framerate=${FPS}/1 \
    ! filesink location='${REMOTE_IMAGE}' && \
    ls -lh '${REMOTE_IMAGE}' && file '${REMOTE_IMAGE}'"

echo "Copying preview back to Mac..."
scp -o BatchMode=yes -o ConnectTimeout=8 "${HOST}:${REMOTE_IMAGE}" "${LOCAL_IMAGE}"

echo "Wrote ${LOCAL_IMAGE}"
