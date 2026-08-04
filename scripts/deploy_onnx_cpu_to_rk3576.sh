#!/usr/bin/env bash
set -euo pipefail

BOARD_HOST="${BOARD_HOST:-rk3576}"
LOCAL_MODEL="${1:-runs/model_exports/yolov8n/yolov8n.onnx}"
LOCAL_IMAGE="${2:-}"
REMOTE_ROOT="${REMOTE_ROOT:-/home/kickpi/spatial-edgeav}"
REMOTE_MODEL_DIR="${REMOTE_ROOT}/models/yolov8n"
REMOTE_BIN_DIR="${REMOTE_ROOT}/bin"
REMOTE_RUN_DIR="${REMOTE_ROOT}/runs/onnx_cpu_smoke"
MODEL_BASENAME="$(basename "${LOCAL_MODEL}")"
REPORT_NAME="${MODEL_BASENAME%.onnx}_rk3576_cpu_report.json"
DETECTIONS_NAME="${MODEL_BASENAME%.onnx}_rk3576_cpu_detections.json"
ANNOTATED_NAME="${MODEL_BASENAME%.onnx}_rk3576_cpu_annotated.jpg"
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

latest_pipeline_image() {
  find runs/edgeav_remote_yolo -path "*/input.jpg" -type f -print 2>/dev/null | sort | tail -1
}

if [[ ! -f "${LOCAL_MODEL}" ]]; then
  echo "Missing local ONNX model: ${LOCAL_MODEL}" >&2
  echo "Run make export-onnx first." >&2
  exit 2
fi

if [[ -z "${LOCAL_IMAGE}" ]]; then
  LOCAL_IMAGE="$(latest_pipeline_image || true)"
fi

if [[ -n "${LOCAL_IMAGE}" && ! -f "${LOCAL_IMAGE}" ]]; then
  echo "Image was provided but does not exist: ${LOCAL_IMAGE}" >&2
  exit 2
fi

LOCAL_REPORT_DIR="runs/rk3576_board"
mkdir -p "${LOCAL_REPORT_DIR}"

echo "Preparing RK3576 ONNX CPU workspace at ${BOARD_HOST}:${REMOTE_ROOT}..."
retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "mkdir -p '${REMOTE_MODEL_DIR}' '${REMOTE_BIN_DIR}' '${REMOTE_RUN_DIR}'"

echo "Copying ONNX model and board CPU smoke-test helper..."
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${LOCAL_MODEL}" \
  "${BOARD_HOST}:${REMOTE_MODEL_DIR}/${MODEL_BASENAME}"
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  scripts/rk3576_onnx_cpu_smoke_test.py \
  "${BOARD_HOST}:${REMOTE_BIN_DIR}/"

REMOTE_IMAGE_ARG=""
if [[ -n "${LOCAL_IMAGE}" ]]; then
  echo "Copying test image: ${LOCAL_IMAGE}"
  retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
    "${LOCAL_IMAGE}" \
    "${BOARD_HOST}:${REMOTE_RUN_DIR}/input.jpg"
  REMOTE_IMAGE_ARG="--image '${REMOTE_RUN_DIR}/input.jpg'"
else
  echo "No local sample image found; runtime will use a zero dummy tensor."
fi

echo "Running board-side ONNX CPU smoke test..."
retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "python3 '${REMOTE_BIN_DIR}/rk3576_onnx_cpu_smoke_test.py' \
    --model '${REMOTE_MODEL_DIR}/${MODEL_BASENAME}' \
    ${REMOTE_IMAGE_ARG} \
    --report '${REMOTE_RUN_DIR}/${REPORT_NAME}' \
    --detections '${REMOTE_RUN_DIR}/${DETECTIONS_NAME}' \
    --annotated '${REMOTE_RUN_DIR}/${ANNOTATED_NAME}' \
    --runs 30"

echo "Copying board CPU report back to Mac..."
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${BOARD_HOST}:${REMOTE_RUN_DIR}/${REPORT_NAME}" \
  "${BOARD_HOST}:${REMOTE_RUN_DIR}/${DETECTIONS_NAME}" \
  "${BOARD_HOST}:${REMOTE_RUN_DIR}/${ANNOTATED_NAME}" \
  "${LOCAL_REPORT_DIR}/"

echo "Wrote:"
echo "  ${LOCAL_REPORT_DIR}/${REPORT_NAME}"
echo "  ${LOCAL_REPORT_DIR}/${DETECTIONS_NAME}"
echo "  ${LOCAL_REPORT_DIR}/${ANNOTATED_NAME}"
