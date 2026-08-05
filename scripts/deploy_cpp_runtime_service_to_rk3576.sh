#!/usr/bin/env bash
set -euo pipefail

BOARD_HOST="${BOARD_HOST:-rk3576}"
REMOTE_ROOT="${REMOTE_ROOT:-/home/kickpi/spatial-edgeav}"
STAGING_DIR="${REMOTE_ROOT}/deploy/cpp_systemd"
SERVICE_NAME="${SERVICE_NAME:-spatial-edgeav-cpp.service}"
ENABLE_SERVICE="${ENABLE_SERVICE:-0}"
START_SERVICE="${START_SERVICE:-0}"

echo "Staging C/C++ runtime service files on RK3576..."
ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "mkdir -p '${STAGING_DIR}' '${REMOTE_ROOT}/runs/cpp_service'"
scp -o BatchMode=yes -o ConnectTimeout=8 \
  systemd/spatial-edgeav-cpp.service \
  "${BOARD_HOST}:${STAGING_DIR}/${SERVICE_NAME}"
scp -o BatchMode=yes -o ConnectTimeout=8 \
  configs/spatial-edgeav-cpp.env \
  "${BOARD_HOST}:${STAGING_DIR}/cpp.env"

echo "Installing ${SERVICE_NAME}..."
ssh -tt "${BOARD_HOST}" \
  "sudo install -d -m 0755 /etc/spatial-edgeav && \
   sudo install -m 0644 '${STAGING_DIR}/cpp.env' /etc/spatial-edgeav/cpp.env && \
   sudo install -m 0644 '${STAGING_DIR}/${SERVICE_NAME}' '/etc/systemd/system/${SERVICE_NAME}' && \
   sudo systemctl daemon-reload && \
   if [ '${ENABLE_SERVICE}' = '1' ]; then sudo systemctl enable '${SERVICE_NAME}'; fi && \
   if [ '${START_SERVICE}' = '1' ]; then sudo systemctl restart '${SERVICE_NAME}'; fi"

echo "Installed ${SERVICE_NAME}"
echo
echo "Useful commands:"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
echo "  cat ${REMOTE_ROOT}/runs/cpp_service/heartbeat.json"
echo "  cat ${REMOTE_ROOT}/runs/cpp_service/events.jsonl"
