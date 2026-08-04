#!/usr/bin/env bash
set -euo pipefail

RKNN_LITE_VERSION="${1:-2.3.2}"

echo "Installing board-side RKNN runtime prerequisites..."
sudo apt-get update
sudo apt-get install -y \
  python3-pip \
  python3-numpy \
  python3-opencv \
  python3-venv \
  v4l-utils

echo "Installing RKNN-Toolkit-Lite2 ${RKNN_LITE_VERSION} for the current user..."
python3 -m pip install --user --break-system-packages \
  "numpy<=1.26.4" \
  "rknn-toolkit-lite2==${RKNN_LITE_VERSION}"

echo "Verifying board runtime imports..."
python3 - <<'PY'
import cv2
import numpy
from rknnlite.api import RKNNLite

print("cv2", cv2.__version__)
print("numpy", numpy.__version__)
print("rknnlite import OK")
PY

echo "Board RKNN runtime setup complete."
