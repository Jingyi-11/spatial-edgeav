#!/usr/bin/env bash
set -euo pipefail

BOARD_HOST="${BOARD_HOST:-rk3576}"
LOCAL_MODEL="${1:-runs/model_exports/rockchip_yolov8n/yolov8n_rockchip_rk3576_i8.rknn}"
REMOTE_ROOT="${REMOTE_ROOT:-/home/kickpi/spatial-edgeav}"
REMOTE_MODEL_DIR="${REMOTE_ROOT}/models/yolov8n"
REMOTE_BIN_DIR="${REMOTE_ROOT}/bin"
REMOTE_SERVICE_DIR="${REMOTE_ROOT}/deploy/systemd"
REMOTE_RUN_DIR="${REMOTE_ROOT}/runs/service"
MODEL_BASENAME="$(basename "${LOCAL_MODEL}")"
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

echo "Preparing RK3576 service workspace..."
retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "mkdir -p '${REMOTE_MODEL_DIR}' '${REMOTE_BIN_DIR}' '${REMOTE_SERVICE_DIR}' '${REMOTE_RUN_DIR}'"

echo "Copying model, runtime helpers, service unit, and env defaults..."
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${LOCAL_MODEL}" \
  "${BOARD_HOST}:${REMOTE_MODEL_DIR}/${MODEL_BASENAME}"
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  scripts/rk3576_rknn_smoke_test.py \
  scripts/rk3576_rknn_camera_loop.py \
  scripts/rk3576_service_health_local.py \
  "${BOARD_HOST}:${REMOTE_BIN_DIR}/"
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  systemd/spatial-edgeav-rknn.service \
  systemd/spatial-edgeav-rknn-health.service \
  systemd/spatial-edgeav-rknn-health.timer \
  "${BOARD_HOST}:${REMOTE_SERVICE_DIR}/"
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  configs/spatial-edgeav-rknn.env \
  "${BOARD_HOST}:${REMOTE_SERVICE_DIR}/rknn.env"
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  scripts/rk3576_install_rknn_service.sh \
  "${BOARD_HOST}:${REMOTE_BIN_DIR}/"

echo "Validating service-mode command without installing systemd unit..."
retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "cd '${REMOTE_BIN_DIR}' && \
   python3 rk3576_rknn_camera_loop.py \
     --model '${REMOTE_MODEL_DIR}/${MODEL_BASENAME}' \
     --device /dev/video73 \
     --frames 5 \
     --report '${REMOTE_RUN_DIR}/service_preflight_report.json' \
     --frames-json '${REMOTE_RUN_DIR}/service_preflight_frames.json' \
     --annotated '${REMOTE_RUN_DIR}/service_preflight_last.jpg' \
     --heartbeat-json '${REMOTE_RUN_DIR}/heartbeat.json' \
     --status-interval-sec 1"

echo
echo "Service files are staged on ${BOARD_HOST}."
echo "To install the systemd service on the board, run:"
echo "  ssh ${BOARD_HOST}"
echo "  ENABLE_SERVICE=1 START_SERVICE=1 bash ${REMOTE_BIN_DIR}/rk3576_install_rknn_service.sh"
echo "  INSTALL_HEALTH_TIMER=1 ENABLE_HEALTH_TIMER=1 START_HEALTH_TIMER=1 bash ${REMOTE_BIN_DIR}/rk3576_install_rknn_service.sh"
echo
echo "Then inspect:"
echo "  sudo systemctl status spatial-edgeav-rknn.service"
echo "  sudo systemctl status spatial-edgeav-rknn-health.timer"
echo "  sudo journalctl -u spatial-edgeav-rknn.service -f"
echo "  cat ${REMOTE_RUN_DIR}/heartbeat.json"
