#!/usr/bin/env bash
set -euo pipefail

WIN_HOST="${WIN_HOST:-winbox}"
WSL_HOST="${WSL_HOST:-wslbox}"
ONNX_PATH="${1:-/mnt/c/Users/HP/edgeav_data/exports/yolov8n/yolov8n.onnx}"
QUANT="${2:-fp}"
TARGET="${3:-rk3576}"
EXPORT_ROOT="${4:-/mnt/c/Users/HP/edgeav_data/exports/yolov8n}"
LOCAL_OUT="${5:-runs/model_exports/yolov8n}"
LOCAL_CALIB_DIR="${LOCAL_CALIB_DIR:-runs/model_exports/yolov8n/calib}"
SSH_RETRIES="${SSH_RETRIES:-3}"
SSH_RETRY_DELAY_SEC="${SSH_RETRY_DELAY_SEC:-3}"

RKNN_PATH="${EXPORT_ROOT}/yolov8n_${TARGET}_${QUANT}.rknn"
REPORT_PATH="${EXPORT_ROOT}/yolov8n_${TARGET}_${QUANT}.report.json"
DATASET_PATH="${EXPORT_ROOT}/calib/dataset.txt"
USE_DIRECT_WSL=0

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

detect_wsl_transport() {
  if retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WSL_HOST}" 'true'; then
    USE_DIRECT_WSL=1
  else
    USE_DIRECT_WSL=0
  fi
}

run_wsl() {
  local command="$1"
  if (( USE_DIRECT_WSL )); then
    retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WSL_HOST}" "${command}"
  else
    echo "Direct WSL SSH unavailable; using ${WIN_HOST} -> wsl.exe bridge." >&2
    retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WIN_HOST}" \
      "cmd /c wsl -d Ubuntu-22.04 --exec /bin/bash -lc \"${command}\""
  fi
}

copy_to_wsl() {
  local source="$1"
  local target="$2"
  if (( USE_DIRECT_WSL )); then
    retry_command scp -r -o BatchMode=yes -o ConnectTimeout=8 "${source}" "${WSL_HOST}:${target}"
  else
    local win_target="${target/#\/mnt\/c/C:}"
    retry_command scp -r -o BatchMode=yes -o ConnectTimeout=8 "${source}" "${WIN_HOST}:${win_target}"
  fi
}

mkdir -p "${LOCAL_OUT}"
detect_wsl_transport

echo "Copying RKNN conversion helper to WSL-visible export directory..."
run_wsl "mkdir -p '${EXPORT_ROOT}'"
copy_to_wsl \
  scripts/convert_yolov8_onnx_to_rknn.py \
  "${EXPORT_ROOT}/"

echo "Converting ${ONNX_PATH} to RKNN (${TARGET}, ${QUANT})..."
if [[ "${QUANT}" == "i8" ]]; then
  if [[ ! -d "${LOCAL_CALIB_DIR}/images" ]]; then
    echo "Missing calibration images: ${LOCAL_CALIB_DIR}/images" >&2
    echo "Run bash scripts/collect_rknn_calibration_frames.sh first." >&2
    exit 2
  fi
  echo "Copying calibration images to WSL-visible export directory..."
  run_wsl "mkdir -p '${EXPORT_ROOT}/calib'"
  copy_to_wsl \
    "${LOCAL_CALIB_DIR}/images" \
    "${EXPORT_ROOT}/calib/"
  run_wsl "set -e; \
    find '${EXPORT_ROOT}/calib/images' -type f | sort > '${DATASET_PATH}'; \
    test -s '${DATASET_PATH}'"
  DATASET_ARG="--dataset '${DATASET_PATH}'"
else
  DATASET_ARG=""
fi

run_wsl "set -e; \
  cd '${EXPORT_ROOT}'; \
  python3 convert_yolov8_onnx_to_rknn.py \
    --onnx '${ONNX_PATH}' \
    --out '${RKNN_PATH}' \
    --target '${TARGET}' \
    --quant '${QUANT}' \
    ${DATASET_ARG} \
    --report '${REPORT_PATH}'"

echo "Copying RKNN artifacts back to Mac..."
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${WIN_HOST}:C:/Users/HP/edgeav_data/exports/yolov8n/$(basename "${RKNN_PATH}")" \
  "${WIN_HOST}:C:/Users/HP/edgeav_data/exports/yolov8n/$(basename "${REPORT_PATH}")" \
  "${LOCAL_OUT}/"

echo "Wrote:"
echo "  ${LOCAL_OUT}/$(basename "${RKNN_PATH}")"
echo "  ${LOCAL_OUT}/$(basename "${REPORT_PATH}")"
