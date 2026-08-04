#!/usr/bin/env bash
set -euo pipefail

REMOTE_ROOT="${REMOTE_ROOT:-/home/kickpi/spatial-edgeav}"
STAGING_DIR="${1:-${REMOTE_ROOT}/deploy/systemd}"
SERVICE_NAME="${SERVICE_NAME:-spatial-edgeav-rknn.service}"
ENABLE_SERVICE="${ENABLE_SERVICE:-0}"
START_SERVICE="${START_SERVICE:-0}"

if [[ ! -f "${STAGING_DIR}/${SERVICE_NAME}" ]]; then
  echo "Missing staged service unit: ${STAGING_DIR}/${SERVICE_NAME}" >&2
  exit 2
fi
if [[ ! -f "${STAGING_DIR}/rknn.env" ]]; then
  echo "Missing staged env file: ${STAGING_DIR}/rknn.env" >&2
  exit 2
fi

sudo install -d -m 0755 /etc/spatial-edgeav
sudo install -m 0644 "${STAGING_DIR}/rknn.env" /etc/spatial-edgeav/rknn.env
sudo install -m 0644 "${STAGING_DIR}/${SERVICE_NAME}" "/etc/systemd/system/${SERVICE_NAME}"
sudo systemctl daemon-reload

if [[ "${ENABLE_SERVICE}" == "1" ]]; then
  sudo systemctl enable "${SERVICE_NAME}"
fi

if [[ "${START_SERVICE}" == "1" ]]; then
  sudo systemctl restart "${SERVICE_NAME}"
fi

echo "Installed ${SERVICE_NAME}"
echo
echo "Useful commands:"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
echo "  cat ${REMOTE_ROOT}/runs/service/heartbeat.json"
echo "  sudo systemctl restart ${SERVICE_NAME}"
echo "  sudo systemctl stop ${SERVICE_NAME}"
