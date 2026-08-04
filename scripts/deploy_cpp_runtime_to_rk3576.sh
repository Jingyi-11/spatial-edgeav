#!/usr/bin/env bash
set -euo pipefail

BOARD_HOST="${BOARD_HOST:-rk3576}"
REMOTE_ROOT="${REMOTE_ROOT:-/home/kickpi/spatial-edgeav}"
REMOTE_SRC_DIR="${REMOTE_ROOT}/cpp_runtime_src"
REMOTE_RUN_DIR="${REMOTE_ROOT}/runs/cpp_runtime"
REMOTE_RKNN_MODEL="${REMOTE_RKNN_MODEL:-${REMOTE_ROOT}/models/yolov8n/yolov8n_rockchip_rk3576_i8.rknn}"
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

echo "Preparing RK3576 C++ runtime workspace..."
retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "mkdir -p '${REMOTE_SRC_DIR}/src' '${REMOTE_SRC_DIR}/include' '${REMOTE_RUN_DIR}'"

echo "Copying C++ runtime sources..."
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  Makefile \
  "${BOARD_HOST}:${REMOTE_SRC_DIR}/"
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  src/edgeav_runtime.cpp \
  src/rknn_detector.cpp \
  src/camera_capture.cpp \
  src/pipeline.cpp \
  src/yuv.cpp \
  src/main.cpp \
  "${BOARD_HOST}:${REMOTE_SRC_DIR}/src/"
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  include/camera_capture.h \
  include/pipeline.h \
  include/rknn_api_compat.h \
  include/rknn_detector.h \
  include/yuv.h \
  "${BOARD_HOST}:${REMOTE_SRC_DIR}/include/"

echo "Building edgeav_runtime on RK3576..."
retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "cd '${REMOTE_SRC_DIR}' && make edgeav-runtime"

echo "Running non-camera simulated runtime smoke test..."
retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "cd '${REMOTE_SRC_DIR}' && ./build/edgeav_runtime \
    --simulate \
    --width 1280 \
    --height 720 \
    --fps 30 \
    --frames 30 \
    --format MJPEG \
    --report '${REMOTE_RUN_DIR}/edgeav_runtime_sim_report.json' \
    --heartbeat '${REMOTE_RUN_DIR}/edgeav_runtime_sim_heartbeat.json'"

if retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" "test -f '${REMOTE_RKNN_MODEL}'"; then
  echo "Running RKNN C API smoke test..."
  retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
    "cd '${REMOTE_SRC_DIR}' && ./build/edgeav_runtime \
      --simulate \
      --width 1280 \
      --height 720 \
      --fps 30 \
      --frames 1 \
      --format MJPEG \
      --report '${REMOTE_RUN_DIR}/edgeav_runtime_rknn_host_report.json' \
      --heartbeat '${REMOTE_RUN_DIR}/edgeav_runtime_rknn_host_heartbeat.json' \
      --rknn-model '${REMOTE_RKNN_MODEL}' \
      --rknn-report '${REMOTE_RUN_DIR}/edgeav_runtime_rknn_report.json' \
      --rknn-runs 10 \
      --rknn-warmup 3"
else
  echo "Skipping RKNN C API smoke test; model not found: ${REMOTE_RKNN_MODEL}" >&2
fi

echo "Copying RK3576 C++ runtime report back to Mac..."
LOCAL_OUT_DIR="runs/rk3576_cpp_runtime"
mkdir -p "${LOCAL_OUT_DIR}"
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${BOARD_HOST}:${REMOTE_RUN_DIR}/edgeav_runtime_sim_report.json" \
  "${LOCAL_OUT_DIR}/edgeav_runtime_sim_report.json"
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${BOARD_HOST}:${REMOTE_RUN_DIR}/edgeav_runtime_sim_heartbeat.json" \
  "${LOCAL_OUT_DIR}/edgeav_runtime_sim_heartbeat.json"
if retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" "test -f '${REMOTE_RUN_DIR}/edgeav_runtime_rknn_report.json'"; then
  retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
    "${BOARD_HOST}:${REMOTE_RUN_DIR}/edgeav_runtime_rknn_report.json" \
    "${LOCAL_OUT_DIR}/edgeav_runtime_rknn_report.json"
fi

echo "Wrote:"
echo "  ${LOCAL_OUT_DIR}/edgeav_runtime_sim_report.json"
echo "  ${LOCAL_OUT_DIR}/edgeav_runtime_sim_heartbeat.json"
echo "  ${LOCAL_OUT_DIR}/edgeav_runtime_rknn_report.json (when RKNN model is available)"
