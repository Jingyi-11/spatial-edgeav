#!/usr/bin/env bash
set -euo pipefail

WSL_HOST="${1:-wslbox}"
WSL_IMAGE="${2:-/mnt/c/Users/HP/edgeav_data/rk3576_preview.jpg}"
LOCAL_OUTPUT="${3:-runs/wsl_yolo_rk3576_preview.jpg}"
PROJECT_DIR="${4:-/mnt/c/Users/HP/edgeav_data/yolo_runs}"
RUN_NAME="${5:-smoke}"

LOCAL_DIR="$(dirname "${LOCAL_OUTPUT}")"
REMOTE_OUTPUT="${PROJECT_DIR}/${RUN_NAME}/$(basename "${WSL_IMAGE}")"

mkdir -p "${LOCAL_DIR}"

echo "Checking WSL sample image..."
ssh -o BatchMode=yes -o ConnectTimeout=8 "${WSL_HOST}" \
  "test -f '${WSL_IMAGE}' && ls -lh '${WSL_IMAGE}'"

echo "Ensuring WSL Python inference dependencies..."
ssh -o BatchMode=yes -o ConnectTimeout=8 "${WSL_HOST}" 'set -e
if ! python3 -m pip --version >/dev/null 2>&1; then
  mkdir -p "$HOME/edgeav_setup"
  cd "$HOME/edgeav_setup"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSLO https://bootstrap.pypa.io/get-pip.py
  else
    wget -q https://bootstrap.pypa.io/get-pip.py
  fi
  python3 get-pip.py --user
fi
python3 - <<'"'"'PY'"'"' >/dev/null 2>&1 || python3 -m pip install --user --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cpu
import torch, torchvision
PY
python3 - <<'"'"'PY'"'"' >/dev/null 2>&1 || python3 -m pip install --user --upgrade ultralytics opencv-python-headless
import ultralytics, cv2
PY
'

echo "Running YOLO smoke test on WSL..."
ssh -o BatchMode=yes -o ConnectTimeout=8 "${WSL_HOST}" \
  "set -e; \
   export PATH=\"\$HOME/.local/bin:\$PATH\"; \
   export YOLO_CONFIG_DIR=/mnt/c/Users/HP/edgeav_data/ultralytics_config; \
   mkdir -p \"\$YOLO_CONFIG_DIR\" '${PROJECT_DIR}'; \
   yolo predict model=yolov8n.pt source='${WSL_IMAGE}' project='${PROJECT_DIR}' name='${RUN_NAME}' exist_ok=True imgsz=640 device=cpu; \
   ls -lh '${PROJECT_DIR}/${RUN_NAME}'"

echo "Copying result back to Mac..."
scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${WSL_HOST}:${REMOTE_OUTPUT}" \
  "${LOCAL_OUTPUT}"

echo "Wrote:"
echo "  ${LOCAL_OUTPUT}"
