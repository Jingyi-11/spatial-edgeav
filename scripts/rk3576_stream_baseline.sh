#!/usr/bin/env bash
set -euo pipefail

HOST="${1:-rk3576}"
DEVICE="${2:-/dev/video73}"
DURATION="${3:-15}"
WIDTH="${4:-1280}"
HEIGHT="${5:-720}"
FPS="${6:-30}"
RUN_DIR="${7:-runs/rk3576_stream_baseline}"
REMOTE_DIR="/tmp/edgeav_stream"
STAMP="$(date +%Y%m%d_%H%M%S)"
REMOTE_VIDEO="${REMOTE_DIR}/c920_${WIDTH}x${HEIGHT}_${FPS}fps_${DURATION}s_${STAMP}.mkv"
REMOTE_PREVIEW="${REMOTE_DIR}/preview_${STAMP}.jpg"
LOCAL_VIDEO="${RUN_DIR}/$(basename "${REMOTE_VIDEO}")"
LOCAL_PREVIEW="${RUN_DIR}/$(basename "${REMOTE_PREVIEW}")"
LOCAL_LOG="${RUN_DIR}/capture_${STAMP}.log"

mkdir -p "${RUN_DIR}"

echo "Starting ${DURATION}s RK3576 continuous capture baseline..."
echo "host=${HOST} device=${DEVICE} size=${WIDTH}x${HEIGHT} fps=${FPS}"

ssh -o BatchMode=yes -o ConnectTimeout=8 "${HOST}" \
  "mkdir -p '${REMOTE_DIR}' && \
   timeout '$((DURATION + 5))' gst-launch-1.0 -e \
     v4l2src device='${DEVICE}' num-buffers='$((DURATION * FPS))' \
     ! image/jpeg,width=${WIDTH},height=${HEIGHT},framerate=${FPS}/1 \
     ! queue \
     ! jpegparse \
     ! matroskamux \
     ! filesink location='${REMOTE_VIDEO}'" \
  2>&1 | tee "${LOCAL_LOG}"

ssh -o BatchMode=yes -o ConnectTimeout=8 "${HOST}" \
  "gst-launch-1.0 -q -e filesrc location='${REMOTE_VIDEO}' \
     ! matroskademux \
     ! jpegparse \
     ! jpegdec \
     ! videoconvert \
     ! jpegenc \
     ! multifilesink max-files=1 location='${REMOTE_PREVIEW}' && \
   ls -lh '${REMOTE_VIDEO}' '${REMOTE_PREVIEW}' && \
   file '${REMOTE_VIDEO}' '${REMOTE_PREVIEW}'"

scp -o BatchMode=yes -o ConnectTimeout=8 "${HOST}:${REMOTE_VIDEO}" "${LOCAL_VIDEO}"
scp -o BatchMode=yes -o ConnectTimeout=8 "${HOST}:${REMOTE_PREVIEW}" "${LOCAL_PREVIEW}"

echo "Wrote:"
echo "  ${LOCAL_VIDEO}"
echo "  ${LOCAL_PREVIEW}"
echo "  ${LOCAL_LOG}"
