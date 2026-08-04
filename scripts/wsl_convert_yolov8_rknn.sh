#!/usr/bin/env bash
set -euo pipefail

WIN_HOST="${WIN_HOST:-winbox}"
WSL_HOST="${WSL_HOST:-wslbox}"
ONNX_PATH="${1:-/mnt/c/Users/HP/edgeav_data/exports/yolov8n/yolov8n.onnx}"
QUANT="${2:-fp}"
TARGET="${3:-rk3576}"
EXPORT_ROOT="${4:-/mnt/c/Users/HP/edgeav_data/exports/yolov8n}"
LOCAL_OUT="${5:-runs/model_exports/yolov8n}"
SSH_RETRIES="${SSH_RETRIES:-3}"
SSH_RETRY_DELAY_SEC="${SSH_RETRY_DELAY_SEC:-3}"

RKNN_PATH="${EXPORT_ROOT}/yolov8n_${TARGET}_${QUANT}.rknn"
REPORT_PATH="${EXPORT_ROOT}/yolov8n_${TARGET}_${QUANT}.report.json"
DATASET_PATH="${EXPORT_ROOT}/calib/dataset.txt"

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

run_wsl() {
  local command="$1"
  if retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WSL_HOST}" 'true'; then
    retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WSL_HOST}" "${command}"
  else
    echo "Direct WSL SSH unavailable; using ${WIN_HOST} -> wsl.exe bridge." >&2
    retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WIN_HOST}" \
      "cmd /c wsl -d Ubuntu-22.04 --exec /bin/bash -lc \"${command}\""
  fi
}

mkdir -p "${LOCAL_OUT}"

echo "Copying RKNN conversion helper to WSL-visible export directory..."
retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WIN_HOST}" \
  "if not exist \"C:/Users/HP/edgeav_data/exports/yolov8n\" mkdir \"C:/Users/HP/edgeav_data/exports/yolov8n\""
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  scripts/convert_yolov8_onnx_to_rknn.py \
  "${WIN_HOST}:C:/Users/HP/edgeav_data/exports/yolov8n/"

echo "Converting ${ONNX_PATH} to RKNN (${TARGET}, ${QUANT})..."
if [[ "${QUANT}" == "i8" ]]; then
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
