#!/usr/bin/env bash
set -euo pipefail

BOARD_HOST="${BOARD_HOST:-rk3576}"
LOCAL_ONNX="${1:-runs/model_exports/yolov8n/yolov8n.onnx}"
QUANT="${2:-i8}"
TARGET="${3:-rk3576}"
LOCAL_OUT="${4:-runs/model_exports/yolov8n}"
LOCAL_CALIB_DIR="${LOCAL_CALIB_DIR:-runs/model_exports/yolov8n/calib}"
REMOTE_EXPORT_ROOT="${REMOTE_EXPORT_ROOT:-/home/kickpi/spatial-edgeav/exports/yolov8n}"
RKNN_QUANTIZED_DTYPE="${RKNN_QUANTIZED_DTYPE:-w8a8}"
RKNN_QUANTIZED_ALGORITHM="${RKNN_QUANTIZED_ALGORITHM:-normal}"
RKNN_QUANTIZED_METHOD="${RKNN_QUANTIZED_METHOD:-channel}"
RKNN_QUANTIZED_HYBRID_LEVEL="${RKNN_QUANTIZED_HYBRID_LEVEL:-0}"
RKNN_AUTO_HYBRID="${RKNN_AUTO_HYBRID:-0}"
PROFILE_SUFFIX="${PROFILE_SUFFIX:-}"
SSH_RETRIES="${SSH_RETRIES:-3}"
SSH_RETRY_DELAY_SEC="${SSH_RETRY_DELAY_SEC:-3}"

MODEL_STEM="$(basename "${LOCAL_ONNX}" .onnx)"
REMOTE_RKNN="${REMOTE_EXPORT_ROOT}/${MODEL_STEM}_${TARGET}_${QUANT}${PROFILE_SUFFIX}.rknn"
REMOTE_REPORT="${REMOTE_EXPORT_ROOT}/${MODEL_STEM}_${TARGET}_${QUANT}${PROFILE_SUFFIX}.report.json"
REMOTE_DATASET="${REMOTE_EXPORT_ROOT}/calib/dataset.txt"

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

if [[ ! -f "${LOCAL_ONNX}" ]]; then
  echo "Missing ONNX model: ${LOCAL_ONNX}" >&2
  echo "Run make export-onnx first." >&2
  exit 2
fi

if [[ "${QUANT}" == "i8" && ! -d "${LOCAL_CALIB_DIR}/images" ]]; then
  echo "Missing calibration images: ${LOCAL_CALIB_DIR}/images" >&2
  echo "Run make collect-rknn-calib-board first." >&2
  exit 2
fi

mkdir -p "${LOCAL_OUT}"

echo "Preparing board conversion workspace..."
retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "mkdir -p '${REMOTE_EXPORT_ROOT}/calib'"

echo "Copying ONNX model and conversion helper to RK3576..."
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${LOCAL_ONNX}" \
  scripts/convert_yolov8_onnx_to_rknn.py \
  "${BOARD_HOST}:${REMOTE_EXPORT_ROOT}/"

DATASET_ARG=""
AUTO_HYBRID_ARG=""
if [[ "${RKNN_AUTO_HYBRID}" == "1" ]]; then
  AUTO_HYBRID_ARG="--auto-hybrid"
fi

if [[ "${QUANT}" == "i8" ]]; then
  echo "Copying calibration images to RK3576..."
  retry_command scp -r -o BatchMode=yes -o ConnectTimeout=8 \
    "${LOCAL_CALIB_DIR}/images" \
    "${BOARD_HOST}:${REMOTE_EXPORT_ROOT}/calib/"
  retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
    "find '${REMOTE_EXPORT_ROOT}/calib/images' -type f | sort > '${REMOTE_DATASET}' && test -s '${REMOTE_DATASET}'"
  DATASET_ARG="--dataset '${REMOTE_DATASET}'"
fi

echo "Converting ${LOCAL_ONNX} to RKNN on RK3576 (${TARGET}, ${QUANT})..."
retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "cd '${REMOTE_EXPORT_ROOT}' && \
   python3 convert_yolov8_onnx_to_rknn.py \
     --onnx '${REMOTE_EXPORT_ROOT}/$(basename "${LOCAL_ONNX}")' \
     --out '${REMOTE_RKNN}' \
     --target '${TARGET}' \
     --quant '${QUANT}' \
     --quantized-dtype '${RKNN_QUANTIZED_DTYPE}' \
     --quantized-algorithm '${RKNN_QUANTIZED_ALGORITHM}' \
     --quantized-method '${RKNN_QUANTIZED_METHOD}' \
     --quantized-hybrid-level '${RKNN_QUANTIZED_HYBRID_LEVEL}' \
     ${DATASET_ARG} \
     ${AUTO_HYBRID_ARG} \
     --report '${REMOTE_REPORT}'"

echo "Copying RKNN artifacts back to Mac..."
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${BOARD_HOST}:${REMOTE_RKNN}" \
  "${BOARD_HOST}:${REMOTE_REPORT}" \
  "${LOCAL_OUT}/"

echo "Wrote:"
echo "  ${LOCAL_OUT}/$(basename "${REMOTE_RKNN}")"
echo "  ${LOCAL_OUT}/$(basename "${REMOTE_REPORT}")"
