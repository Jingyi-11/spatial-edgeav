#!/usr/bin/env bash
set -euo pipefail

REMOTE_ROOT="${REMOTE_ROOT:-/home/kickpi/spatial-edgeav}"
STAGING_DIR="${1:-${REMOTE_ROOT}/deploy/systemd}"
SERVICE_NAME="${SERVICE_NAME:-spatial-edgeav-rknn.service}"
HEALTH_SERVICE_NAME="${HEALTH_SERVICE_NAME:-spatial-edgeav-rknn-health.service}"
HEALTH_TIMER_NAME="${HEALTH_TIMER_NAME:-spatial-edgeav-rknn-health.timer}"
ENABLE_SERVICE="${ENABLE_SERVICE:-0}"
START_SERVICE="${START_SERVICE:-0}"
INSTALL_HEALTH_TIMER="${INSTALL_HEALTH_TIMER:-0}"
ENABLE_HEALTH_TIMER="${ENABLE_HEALTH_TIMER:-0}"
START_HEALTH_TIMER="${START_HEALTH_TIMER:-0}"

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
if [[ "${INSTALL_HEALTH_TIMER}" == "1" ]]; then
  if [[ ! -f "${STAGING_DIR}/${HEALTH_SERVICE_NAME}" ]]; then
    echo "Missing staged health service unit: ${STAGING_DIR}/${HEALTH_SERVICE_NAME}" >&2
    exit 2
  fi
  if [[ ! -f "${STAGING_DIR}/${HEALTH_TIMER_NAME}" ]]; then
    echo "Missing staged health timer unit: ${STAGING_DIR}/${HEALTH_TIMER_NAME}" >&2
    exit 2
  fi
  sudo install -m 0644 "${STAGING_DIR}/${HEALTH_SERVICE_NAME}" "/etc/systemd/system/${HEALTH_SERVICE_NAME}"
  sudo install -m 0644 "${STAGING_DIR}/${HEALTH_TIMER_NAME}" "/etc/systemd/system/${HEALTH_TIMER_NAME}"
fi
sudo systemctl daemon-reload

if [[ "${ENABLE_SERVICE}" == "1" ]]; then
  sudo systemctl enable "${SERVICE_NAME}"
fi

if [[ "${START_SERVICE}" == "1" ]]; then
  sudo systemctl restart "${SERVICE_NAME}"
fi

if [[ "${INSTALL_HEALTH_TIMER}" == "1" && "${ENABLE_HEALTH_TIMER}" == "1" ]]; then
  sudo systemctl enable "${HEALTH_TIMER_NAME}"
fi

if [[ "${INSTALL_HEALTH_TIMER}" == "1" && "${START_HEALTH_TIMER}" == "1" ]]; then
  sudo systemctl restart "${HEALTH_TIMER_NAME}"
fi

echo "Installed ${SERVICE_NAME}"
if [[ "${INSTALL_HEALTH_TIMER}" == "1" ]]; then
  echo "Installed ${HEALTH_SERVICE_NAME} and ${HEALTH_TIMER_NAME}"
fi
echo
echo "Useful commands:"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "  sudo systemctl status ${HEALTH_TIMER_NAME}"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
echo "  sudo journalctl -u ${HEALTH_SERVICE_NAME} -n 50"
echo "  cat ${REMOTE_ROOT}/runs/service/heartbeat.json"
echo "  cat ${REMOTE_ROOT}/runs/service_health/health.json"
echo "  sudo systemctl restart ${SERVICE_NAME}"
echo "  sudo systemctl stop ${SERVICE_NAME}"
