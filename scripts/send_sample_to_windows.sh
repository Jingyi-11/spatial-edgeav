#!/usr/bin/env bash
set -euo pipefail

WINDOWS_HOST="${1:-winbox}"
LOCAL_IMAGE="${2:-runs/rk3576_stream_baseline/preview_20260725_231716.jpg}"
REMOTE_DIR="${3:-C:/Users/HP/edgeav_data}"
REMOTE_NAME="${4:-rk3576_preview.jpg}"

if [[ ! -f "${LOCAL_IMAGE}" ]]; then
  echo "Local image not found: ${LOCAL_IMAGE}" >&2
  exit 1
fi

echo "Ensuring ${REMOTE_DIR} exists on ${WINDOWS_HOST}..."
ssh -o BatchMode=yes -o ConnectTimeout=8 "${WINDOWS_HOST}" \
  "if not exist \"${REMOTE_DIR}\" mkdir \"${REMOTE_DIR}\""

echo "Copying sample image to Windows..."
scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${LOCAL_IMAGE}" \
  "${WINDOWS_HOST}:${REMOTE_DIR}/${REMOTE_NAME}"

echo "Verifying remote file..."
ssh -o BatchMode=yes -o ConnectTimeout=8 "${WINDOWS_HOST}" \
  "powershell -NoProfile -Command \"Get-Item '${REMOTE_DIR}/${REMOTE_NAME}' | Select-Object FullName,Length\""

echo "Windows path:"
echo "  ${REMOTE_DIR}/${REMOTE_NAME}"
echo "WSL path:"
echo "  /mnt/c/Users/HP/edgeav_data/${REMOTE_NAME}"

