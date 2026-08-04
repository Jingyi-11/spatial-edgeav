#!/usr/bin/env bash
set -euo pipefail

RKNN_VERSION="${1:-2.3.2}"

echo "Installing RKNN-Toolkit2 ${RKNN_VERSION} conversion dependencies on RK3576..."
python3 -m pip install --user --break-system-packages --upgrade --force-reinstall \
  "numpy<=1.26.4" \
  "scipy==1.12.0" \
  "protobuf>=4.21.6,<=4.25.4" \
  "onnx==1.16.1" \
  "onnxruntime>=1.10.0" \
  "Pillow>=10.0.1" \
  "torch==2.2.0" \
  "ruamel.yaml>=0.17.21" \
  "tqdm>=4.64.1" \
  "fast-histogram>=0.11"

python3 -m pip install --user --break-system-packages --upgrade --no-deps \
  "rknn-toolkit2==${RKNN_VERSION}"

python3 - <<'PY'
import cv2
import numpy
import onnx
import scipy
import torch
from rknn.api import RKNN

print("cv2", cv2.__version__)
print("numpy", numpy.__version__)
print("onnx", onnx.__version__)
print("scipy", scipy.__version__)
print("torch", torch.__version__)
print("rknn toolkit import OK")
PY

echo "RK3576 conversion fallback setup complete."
