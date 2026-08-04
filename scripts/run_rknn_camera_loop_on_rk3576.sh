#!/usr/bin/env bash
set -euo pipefail

BOARD_HOST="${BOARD_HOST:-rk3576}"
LOCAL_MODEL="${1:-runs/model_exports/rockchip_yolov8n/yolov8n_rockchip_rk3576_i8.rknn}"
DEVICE="${2:-/dev/video73}"
FRAMES="${3:-60}"
WIDTH="${WIDTH:-1280}"
HEIGHT="${HEIGHT:-720}"
FPS="${FPS:-30}"
REMOTE_ROOT="${REMOTE_ROOT:-/home/kickpi/spatial-edgeav}"
REMOTE_MODEL_DIR="${REMOTE_ROOT}/models/yolov8n"
REMOTE_BIN_DIR="${REMOTE_ROOT}/bin"
REMOTE_RUN_DIR="${REMOTE_ROOT}/runs/rknn_camera_loop"
MODEL_BASENAME="$(basename "${LOCAL_MODEL}")"
REPORT_NAME="${MODEL_BASENAME%.rknn}_camera_report.json"
FRAMES_NAME="${MODEL_BASENAME%.rknn}_camera_frames.json"
ANNOTATED_NAME="${MODEL_BASENAME%.rknn}_camera_last.jpg"
LOCAL_REPORT_DIR="runs/rk3576_camera_rknn"
SSH_RETRIES="${SSH_RETRIES:-3}"
SSH_RETRY_DELAY_SEC="${SSH_RETRY_DELAY_SEC:-3}"

retry_command() {
  local attempt=1
  while true; do
    if "$@"; then
      return 0
    fi
    if (( attempt >= SSH_RETRIES )); then
      return 1
    fi
    echo "Command failed; retrying in ${SSH_RETRY_DELAY_SEC}s (${attempt}/${SSH_RETRIES})..." >&2
    sleep "${SSH_RETRY_DELAY_SEC}"
    attempt=$((attempt + 1))
  done
}

if [[ ! -f "${LOCAL_MODEL}" ]]; then
  echo "Missing local RKNN model: ${LOCAL_MODEL}" >&2
  echo "Run make convert-rockchip-yolov8n-i8-board first." >&2
  exit 2
fi

mkdir -p "${LOCAL_REPORT_DIR}"

echo "Preparing RK3576 camera inference workspace..."
retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "mkdir -p '${REMOTE_MODEL_DIR}' '${REMOTE_BIN_DIR}' '${REMOTE_RUN_DIR}'"

echo "Copying RKNN model and camera-loop helpers..."
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${LOCAL_MODEL}" \
  "${BOARD_HOST}:${REMOTE_MODEL_DIR}/${MODEL_BASENAME}"
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  scripts/rk3576_rknn_smoke_test.py \
  scripts/rk3576_rknn_camera_loop.py \
  "${BOARD_HOST}:${REMOTE_BIN_DIR}/"

echo "Running RK3576 continuous camera RKNN inference..."
retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "cd '${REMOTE_BIN_DIR}' && \
   python3 rk3576_rknn_camera_loop.py \
     --model '${REMOTE_MODEL_DIR}/${MODEL_BASENAME}' \
     --device '${DEVICE}' \
     --width '${WIDTH}' \
     --height '${HEIGHT}' \
     --fps '${FPS}' \
     --frames '${FRAMES}' \
     --report '${REMOTE_RUN_DIR}/${REPORT_NAME}' \
     --frames-json '${REMOTE_RUN_DIR}/${FRAMES_NAME}' \
     --annotated '${REMOTE_RUN_DIR}/${ANNOTATED_NAME}'"

echo "Copying camera inference artifacts back to Mac..."
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${BOARD_HOST}:${REMOTE_RUN_DIR}/${REPORT_NAME}" \
  "${BOARD_HOST}:${REMOTE_RUN_DIR}/${FRAMES_NAME}" \
  "${BOARD_HOST}:${REMOTE_RUN_DIR}/${ANNOTATED_NAME}" \
  "${LOCAL_REPORT_DIR}/"

echo "Wrote:"
echo "  ${LOCAL_REPORT_DIR}/${REPORT_NAME}"
echo "  ${LOCAL_REPORT_DIR}/${FRAMES_NAME}"
echo "  ${LOCAL_REPORT_DIR}/${ANNOTATED_NAME}"
