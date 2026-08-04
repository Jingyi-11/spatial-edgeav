#!/usr/bin/env bash
set -euo pipefail

WIN_HOST="${WIN_HOST:-winbox}"
WSL_HOST="${WSL_HOST:-wslbox}"
MODEL="${1:-yolov8n.pt}"
IMGSZ="${2:-640}"
OPSET="${3:-12}"
EXPORT_ROOT="${4:-/mnt/c/Users/HP/edgeav_data/exports/yolov8n}"
LOCAL_OUT="${5:-runs/model_exports/yolov8n}"
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

run_wsl() {
  local command="$1"
  if retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WSL_HOST}" 'true'; then
    retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WSL_HOST}" "${command}"
  else
    echo "Direct WSL SSH unavailable; using ${WIN_HOST} -> wsl.exe bridge." >&2
    retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WIN_HOST}" \
      "cmd /c wsl -d Ubuntu-22.04 --exec /bin/bash -lc \"${command}\""
  fi
}

mkdir -p "${LOCAL_OUT}"
retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WIN_HOST}" \
  "if not exist \"C:/Users/HP/edgeav_data/exports/yolov8n\" mkdir \"C:/Users/HP/edgeav_data/exports/yolov8n\""
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  scripts/inspect_onnx_model.py \
  "${WIN_HOST}:C:/Users/HP/edgeav_data/exports/yolov8n/"

echo "Exporting ${MODEL} to ONNX in WSL..."
run_wsl "set -e; \
  export PATH=\"\$HOME/.local/bin:\$PATH\"; \
  mkdir -p '${EXPORT_ROOT}'; \
  cd '${EXPORT_ROOT}'; \
  python3 -m pip install --user --upgrade onnx onnxruntime >/dev/null; \
  yolo export model='${MODEL}' format=onnx imgsz='${IMGSZ}' opset='${OPSET}' simplify=False dynamic=False; \
  python3 inspect_onnx_model.py '${EXPORT_ROOT}/${MODEL%.pt}.onnx' '${EXPORT_ROOT}/onnx_export_report.json'"

echo "Copying ONNX export artifacts back to Mac..."
retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${WIN_HOST}:C:/Users/HP/edgeav_data/exports/yolov8n/${MODEL%.pt}.onnx" \
  "${WIN_HOST}:C:/Users/HP/edgeav_data/exports/yolov8n/onnx_export_report.json" \
  "${LOCAL_OUT}/"

echo "Wrote:"
echo "  ${LOCAL_OUT}/${MODEL%.pt}.onnx"
echo "  ${LOCAL_OUT}/onnx_export_report.json"
