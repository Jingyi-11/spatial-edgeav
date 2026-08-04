#!/usr/bin/env bash
set -euo pipefail

BOARD_HOST="${BOARD_HOST:-rk3576}"
REMOTE_ROOT="${REMOTE_ROOT:-/home/kickpi/spatial-edgeav}"
REMOTE_SRC_DIR="${REMOTE_ROOT}/cpp_runtime_src"
REMOTE_RUN_DIR="${REMOTE_ROOT}/runs/cpp_runtime"
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

echo "Preparing RK3576 C/C++ runtime workspace..."
retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "mkdir -p '${REMOTE_SRC_DIR}/src' '${REMOTE_SRC_DIR}/include' '${REMOTE_RUN_DIR}'"

echo "Copying C/C++ runtime sources..."
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  Makefile \
  "${BOARD_HOST}:${REMOTE_SRC_DIR}/"
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  src/edgeav_runtime.cpp \
  src/camera_capture.c \
  src/pipeline.c \
  src/yuv.c \
  src/main.c \
  "${BOARD_HOST}:${REMOTE_SRC_DIR}/src/"
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  include/camera_capture.h \
  include/pipeline.h \
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

echo "Copying RK3576 C/C++ runtime report back to Mac..."
LOCAL_OUT_DIR="runs/rk3576_cpp_runtime"
mkdir -p "${LOCAL_OUT_DIR}"
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${BOARD_HOST}:${REMOTE_RUN_DIR}/edgeav_runtime_sim_report.json" \
  "${LOCAL_OUT_DIR}/edgeav_runtime_sim_report.json"
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${BOARD_HOST}:${REMOTE_RUN_DIR}/edgeav_runtime_sim_heartbeat.json" \
  "${LOCAL_OUT_DIR}/edgeav_runtime_sim_heartbeat.json"

echo "Wrote:"
echo "  ${LOCAL_OUT_DIR}/edgeav_runtime_sim_report.json"
echo "  ${LOCAL_OUT_DIR}/edgeav_runtime_sim_heartbeat.json"
