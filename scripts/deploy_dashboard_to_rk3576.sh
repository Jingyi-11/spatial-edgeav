#!/usr/bin/env bash
set -euo pipefail

BOARD_HOST="${BOARD_HOST:-rk3576}"
REMOTE_ROOT="${REMOTE_ROOT:-/home/kickpi/spatial-edgeav}"
STAGING_DIR="${REMOTE_ROOT}/deploy/dashboard_systemd"
SERVICE_NAME="${SERVICE_NAME:-spatial-edgeav-dashboard.service}"
ENABLE_SERVICE="${ENABLE_SERVICE:-0}"
START_SERVICE="${START_SERVICE:-0}"

echo "Copying dashboard server to RK3576..."
ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "mkdir -p '${REMOTE_ROOT}/bin' '${STAGING_DIR}'"
scp -o BatchMode=yes -o ConnectTimeout=8 \
  scripts/edgeav_dashboard_server.py \
  "${BOARD_HOST}:${REMOTE_ROOT}/bin/"
ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "chmod +x '${REMOTE_ROOT}/bin/edgeav_dashboard_server.py'"

echo "Staging dashboard service files..."
scp -o BatchMode=yes -o ConnectTimeout=8 \
  systemd/spatial-edgeav-dashboard.service \
  "${BOARD_HOST}:${STAGING_DIR}/${SERVICE_NAME}"
scp -o BatchMode=yes -o ConnectTimeout=8 \
  configs/spatial-edgeav-dashboard.env \
  "${BOARD_HOST}:${STAGING_DIR}/dashboard.env"

echo "Installing ${SERVICE_NAME}..."
ssh -tt "${BOARD_HOST}" \
  "sudo install -d -m 0755 /etc/spatial-edgeav && \
   sudo install -m 0644 '${STAGING_DIR}/dashboard.env' /etc/spatial-edgeav/dashboard.env && \
   sudo install -m 0644 '${STAGING_DIR}/${SERVICE_NAME}' '/etc/systemd/system/${SERVICE_NAME}' && \
   sudo systemctl daemon-reload && \
   if [ '${ENABLE_SERVICE}' = '1' ]; then sudo systemctl enable '${SERVICE_NAME}'; fi && \
   if [ '${START_SERVICE}' = '1' ]; then sudo systemctl restart '${SERVICE_NAME}'; fi"

echo "Installed ${SERVICE_NAME}"
echo
echo "Open from Mac through an SSH tunnel:"
echo "  ssh -N -L 8080:127.0.0.1:8080 ${BOARD_HOST}"
echo "  http://127.0.0.1:8080"
echo
echo "Open on a monitor attached to RK3576:"
echo "  http://127.0.0.1:8080"
echo
echo "Useful commands:"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
