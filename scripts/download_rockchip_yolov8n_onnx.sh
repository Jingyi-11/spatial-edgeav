#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-runs/model_exports/rockchip_yolov8n}"
OUT_FILE="${OUT_DIR}/yolov8n_rockchip.onnx"
URL="${ROCKCHIP_YOLOV8N_ONNX_URL:-https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/yolov8/yolov8n.onnx}"

mkdir -p "${OUT_DIR}"

if [[ -s "${OUT_FILE}" ]]; then
  echo "Already exists: ${OUT_FILE}"
  exit 0
fi

echo "Downloading Rockchip optimized YOLOv8n ONNX..."
curl -L "${URL}" -o "${OUT_FILE}"
echo "Wrote: ${OUT_FILE}"
